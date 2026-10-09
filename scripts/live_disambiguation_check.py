"""Real application requests: no mocked model, API, or conversation storage.

Default run: the original disambiguation scenarios (stream endpoint).

``--discovery``: live acceptance of discovery slot memory (Inquiry to Sales
§28, §32) on both assist endpoints. Uses the configured discovery flag (default
on after Step 8); explicit false stops the run. Adds a "discovery" key to
docs/evidence/live/disambiguation.json and leaves the other transcripts as they
are. Never prints or stores keys, tokens, headers or .env contents.
"""
import json
import os
import re
import statistics
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from app import api

RESULTS_PATH = Path("docs/evidence/live/disambiguation.json")


# -----------------------------------
# DISCOVERY ACCEPTANCE (--discovery)
# -----------------------------------

ENDPOINTS = {"json": "/api/support/assist", "stream": "/api/support/assist/stream"}
FIXED_BUTTONS = {"Any area", "Any budget", "Browse all projects", "Book a site visit", "Raise a support ticket"}
SLOW_TURN_MS = 8000
_BHK_RE = re.compile(r"\b([1-6])\s*b(?:h)?ks?\b", re.IGNORECASE)
_CS_ERROR_RE = re.compile(r"Could not reach the CS API|CS API request timed out|HTTP Error \d{3}|errorMessage|"
                          r"CS API returned invalid|Traceback|apiKey\s*[=:]", re.IGNORECASE)
_URL_WITH_CREDENTIALS_RE = re.compile(r"[a-z][a-z0-9+.-]*://[^/\s\"@]+@", re.IGNORECASE)
_KEY_SHAPED_RE = re.compile(r"\b(?:sk|pk|rk)_[A-Za-z0-9]{16,}\b|\b[A-Za-z0-9_-]{40,}\b")
# Response fields that legitimately hold long random identifiers.
_ID_FIELDS = {"id", "trace_id", "request_id", "chunk_id", "dedupe_key", "source_key", "created_at", "retrieved_at"}


def _safe_error(error):
    """Error class and message with URLs reduced to scheme://host/path (no query, no userinfo)."""
    message = re.sub(r"[a-z][a-z0-9+.-]*://\S+", lambda m: _strip_url(m.group(0)), str(error), flags=re.I)
    return f"{type(error).__name__}: {message[:300]}"


def _strip_url(url):
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def _format_inr(value):
    return f"INR {value / 10**7:.2f} crore" if value >= 10**7 else f"INR {value / 10**5:.2f} lakh"


def _numbers(record):
    return set(_BHK_RE.findall(f"{record.get('typologyName') or ''} {record.get('typologyType') or ''}"))


def _preflight():
    """Configuration and reachability, as booleans and error classes only."""
    from services.acrobuild_company_service import get_company_projects, is_cs_api_configured
    from services.llm_service import is_llm_available
    from qwen import generate_qwen_chat_response
    status = {"cs_api_configured": is_cs_api_configured(), "llm_configured": is_llm_available()}
    try:
        status["cs_api_projects"] = len(get_company_projects())
    except Exception as error:  # report and stop; never retry in a loop
        status["cs_api_error"] = _safe_error(error)
    try:
        status["llm_reply_chars"] = len(generate_qwen_chat_response(
            system_prompt="Reply with the single word OK.", user_prompt="OK?", conversation_messages=[],
            temperature=0) or "")
    except Exception as error:
        status["llm_error"] = _safe_error(error)
    return status


def _data_checks():
    """Items 1-4: business data only, read through the existing service functions."""
    from services.acrobuild_company_service import customer_facing_projects, get_company_projects, get_project_typologies
    from services.property_tools_service import clean_place_text
    projects = customer_facing_projects(get_company_projects())
    typologies = {}
    typology_errors = {}
    for project in projects:
        try:
            typologies[project["id"]] = get_project_typologies(project["id"])
        except Exception as error:
            typology_errors[str(project.get("projectName"))] = type(error).__name__
    localities = Counter(str(p.get("locality") or "").strip() for p in projects)
    cities = Counter(str(p.get("city") or "").strip() for p in projects)
    rate_types: dict = {}
    images = []
    for project in projects:
        for record in typologies.get(project["id"], []):
            rate = str(record.get("rateType"))
            entry = rate_types.setdefault(rate, {"typologies": 0, "example": None,
                                                 "treated_as_priced_by_budget_maths": "sq" in rate.lower()})
            entry["typologies"] += 1
            if entry["example"] is None:
                entry["example"] = {"project": project.get("projectName"), "typology": record.get("typologyName"),
                                    "minBasePrice": record.get("minBasePrice"),
                                    "saleableArea": record.get("saleableArea")}
            if record.get("imageUrl"):
                images.append(_strip_url(str(record["imageUrl"])))
    raw_places = [str(p.get(key) or "") for p in projects for key in ("locality", "city") if p.get(key)]
    dirty = sorted({value for value in raw_places if clean_place_text(value) != value.strip()})
    total_typologies = sum(len(records) for records in typologies.values())
    return {
        "projects": len(projects),
        "project_names": sorted(str(p.get("projectName")) for p in projects),
        "localities": dict(sorted((k or "(empty)", v) for k, v in localities.items())),
        "cities": dict(sorted((k or "(empty)", v) for k, v in cities.items())),
        "projects_with_empty_locality": sorted(str(p.get("projectName")) for p in projects
                                               if not str(p.get("locality") or "").strip()),
        "typology_fetch_errors": typology_errors,
        "typologies": total_typologies,
        "rate_types": rate_types,
        "image_url": {"typologies_with_imageUrl": len(images), "of_total": total_typologies,
                      "examples_query_stripped": images[:3], "description": "imageUrl (content unverified)"},
        "places_with_invisible_or_control_characters": {
            "count": len(dirty), "cleaned": [clean_place_text(value) for value in dirty]},
        "_typologies_by_project": {str(p.get("projectName")): typologies.get(p["id"], []) for p in projects},
        "_projects": projects,
    }


def _expected_estimate(data, project_name, config):
    """Independent recomputation: min over matching per-sq-ft typologies of minBasePrice x saleableArea."""
    values = []
    for record in data["_typologies_by_project"].get(project_name, []):
        if config and not set(config) & _numbers(record):
            continue
        rate, area = record.get("minBasePrice"), record.get("saleableArea")
        if "sq" in str(record.get("rateType") or "").lower() and isinstance(rate, (int, float)) \
                and isinstance(area, (int, float)) and rate > 0 and area > 0:
            values.append(float(rate) * float(area))
    return min(values) if values else None


def _leaks(payload, secrets):
    """Raw CS error text, credential URLs, key-shaped strings or configured secrets in a response."""
    def scrub(value):
        if isinstance(value, dict):
            return {k: scrub(v) for k, v in value.items() if k not in _ID_FIELDS}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        return value
    text = json.dumps(scrub(payload), ensure_ascii=False)
    found = []
    if _CS_ERROR_RE.search(text):
        found.append("raw_cs_error_text")
    if _URL_WITH_CREDENTIALS_RE.search(text):
        found.append("url_with_credentials")
    if _KEY_SHAPED_RE.search(text):
        found.append("key_shaped_string")
    if any(secret and secret in json.dumps(payload) for secret in secrets):
        found.append("configured_secret")   # checked in memory only; never printed
    discovery_fields = {k: payload.get(k) for k in ("skipped", "discovery_slots", "options", "pending_project_lookup")}
    discovery_errors = [c.get("error") for c in payload.get("data_api_calls") or [] if c.get("error")] \
        if payload.get("discovery_kind") else []
    if _CS_ERROR_RE.search(json.dumps(discovery_fields)) or any(
            not str(error).startswith("Live data request failed") for error in discovery_errors):
        found.append("discovery_field_raw_error")
    return found


class _Conversation:
    def __init__(self, client, endpoint_key, secrets):
        self.client = client
        self.endpoint_key = endpoint_key
        self.conversation_id = "live-discovery-" + str(uuid.uuid4())
        self.turns = []
        self.secrets = secrets

    def ask(self, text):
        endpoint = ENDPOINTS[self.endpoint_key]
        started = time.perf_counter()
        response = self.client.post(endpoint, json={"issue": text, "conversation_id": self.conversation_id})
        if response.status_code == 429:
            time.sleep(61)   # request_security_service budget; one wait, one retry
            started = time.perf_counter()
            response = self.client.post(endpoint, json={"issue": text, "conversation_id": self.conversation_id})
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        response.raise_for_status()
        if self.endpoint_key == "stream":
            events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
            payload = next(event["response"] for event in events if event.get("type") in {"done", "error"})
        else:
            payload = response.json()
        turn = {
            "user": text,
            "answer": payload.get("answer"),
            "quick_replies": [reply.get("label") for reply in payload.get("quick_replies") or []],
            "clarification_entity": payload.get("clarification_entity"),
            "source_status": payload.get("source_status"),
            "discovery_kind": payload.get("discovery_kind"),
            "options": payload.get("options"),
            "pending_options": (payload.get("pending_project_lookup") or {}).get("options")
            if isinstance(payload.get("pending_project_lookup"), dict) else None,
            "discovery_slots": payload.get("discovery_slots"),
            "route": payload.get("route"),
            "used_llm": payload.get("used_llm"),
            "catalogue_home_type_search": payload.get("catalogue_home_type_search"),
            "duration_ms": duration_ms,
            "leaks": _leaks(payload, self.secrets),
        }
        self.turns.append(turn)
        print(f"  [{self.endpoint_key}] USER: {text}", flush=True)
        print(f"  [{self.endpoint_key}] BOT ({duration_ms} ms, {turn['discovery_kind'] or turn['route']}): "
              f"{str(turn['answer'])[:300]}", flush=True)
        return turn


def _first_option(turn):
    return next((label for label in turn["quick_replies"] if label not in FIXED_BUTTONS), None)


def _name_checks(turn, data):
    """Every shown locality/project name is live; every INR figure is recomputable."""
    places = {str(p.get(k)).strip() for p in data["_projects"] for k in ("locality", "city") if p.get(k)}
    from services.property_tools_service import clean_place_text
    places |= {clean_place_text(value) for value in places}
    names = set(data["project_names"])
    problems = []
    if turn["discovery_kind"]:
        for label in turn["quick_replies"]:
            if label not in places | names | FIXED_BUTTONS:
                problems.append(f"quick reply not live: {label}")
        for option in turn["options"] or []:
            if option not in places | names:
                problems.append(f"option not live: {option}")
        config = (turn["discovery_slots"] or {}).get("config") or []
        allowed_figures = set()
        budget = (turn["discovery_slots"] or {}).get("budget_max_inr")
        if isinstance(budget, int):
            allowed_figures.add(_format_inr(budget))
        for line in str(turn["answer"] or "").splitlines():
            match = re.match(r"- (.+?): estimated base amount from (INR [\d.]+ (?:crore|lakh))$", line)
            if match:
                expected = _expected_estimate(data, match.group(1), config)
                if match.group(1) not in names:
                    problems.append(f"project not live: {match.group(1)}")
                elif expected is None or _format_inr(expected) != match.group(2):
                    problems.append(f"figure mismatch for {match.group(1)}: shown {match.group(2)}, "
                                    f"recomputed {_format_inr(expected) if expected else 'unpriced'}")
                allowed_figures.add(match.group(2))
            elif line.startswith("- ") and turn["discovery_kind"] in {"locality_question", "locality_not_found"}:
                if line[2:] not in places:
                    problems.append(f"area bullet not live: {line[2:]}")
        # A budget question may contain a fixed input-format example. It is not
        # a property price; only result figures must be backed by live rates.
        if turn["discovery_kind"] == "results":
            for figure in re.findall(r"INR [\d.]+ (?:crore|lakh)", str(turn["answer"] or "")):
                if figure not in allowed_figures:
                    problems.append(f"unexplained figure: {figure}")
    return problems


def _honesty(turn):
    answer = str(turn["answer"] or "")
    problems = []
    if turn["discovery_kind"] == "results":
        if "estimated base amount" not in answer:
            problems.append("missing 'estimated base amount'")
        if "It is a base estimate only" not in answer:
            problems.append("missing disclaimer")
    if turn["discovery_kind"] and re.search(r"\bprices?\b", answer, re.IGNORECASE):
        problems.append("says 'price'")
    if turn["discovery_kind"] and "floor plan" in answer.lower():
        problems.append("says 'floor plan'")
    return problems


_AREA_QUESTION_RE = re.compile(r"\b(?:which|what)\s+(?:area|locality|place|city)\b|\barea\s+in\b|"
                               r"\b(?:looking|searching)\s+(?:at|in|for)\b", re.IGNORECASE)


def _reset_problems(turn, data):
    """A bare reset is a fixed reply: no place, project or configuration (from any earlier turn),
    no INR figure, no LLM-style area question, no LLM."""
    answer = str(turn["answer"] or "")
    places = {str(p.get(k)).strip() for p in data["_projects"] for k in ("locality", "city") if p.get(k)}
    named = sorted(name for name in places | set(data["project_names"])
                   if re.search(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", answer, re.IGNORECASE))
    problems = []
    if named:
        problems.append(f"reset reply names {named}")
    if re.search(r"\d\s*b(?:h)?ks?\b|\bINR\b|\d", answer, re.IGNORECASE):
        problems.append("reset reply has a configuration, figure or digit")
    if _AREA_QUESTION_RE.search(answer):
        problems.append("reset reply asks an LLM-style area question")
    if turn["discovery_kind"] or turn["used_llm"] or turn["route"] != "general":
        problems.append(f"reset reply is not the fixed reply (kind={turn['discovery_kind']}, "
                        f"used_llm={turn['used_llm']}, route={turn['route']})")
    return problems


def _run_transcript(name, client, endpoint_key, secrets, data, live):
    conversation = _Conversation(client, endpoint_key, secrets)
    ask = conversation.ask
    evidence = []
    ok = True

    def expect(condition, line):
        nonlocal ok
        evidence.append(("PASS " if condition else "FAIL ") + line)
        ok = ok and bool(condition)

    loc, other_loc = live["loc"], live["other_loc"]
    if name == "T1":
        first = ask("Show me 3 BHK")
        expect(first["quick_replies"] == (first["options"] or []) and "Any area" not in first["quick_replies"],
               f"locality buttons are live options only: {first['quick_replies']}")
        tap = _first_option(first) if first["discovery_kind"] == "locality_question" else None
        second = ask(tap) if tap else first
        expect(second["discovery_kind"] == "budget_question", f"area step -> {second['discovery_kind']} (tap={tap})")
        expect(not second["quick_replies"] and "any budget" in str(second["answer"]).lower(),
               f"budget is guided free text: buttons={second['quick_replies']}")
        shortlist = ask("1.5 crore")
        expect(shortlist["discovery_kind"] == "results", f"budget -> {shortlist['discovery_kind']}")
        project = _first_option(shortlist)
        if project:
            answer = ask(project)
            expect(f"Home types in {project}" in str(answer["answer"]), f"tap '{project}' -> {str(answer['answer'])[:80]}")
        else:
            expect(False, "shortlist offered no project to tap")
    elif name == "T2":
        turn = ask(f"3 BHK in {loc} under 1.5 crore")
        expect(turn["discovery_kind"] == "results", f"one-shot -> {turn['discovery_kind']}")
        expect((turn["discovery_slots"] or {}).get("locality") == loc, f"locality slot {(turn['discovery_slots'] or {}).get('locality')}")
    elif name == "T3":
        ask("Show me 3 BHK")
        budget = ask("Any area")
        expect(budget["discovery_kind"] == "budget_question" and (budget["discovery_slots"] or {}).get("locality") == "any",
               f"'Any area' -> {budget['discovery_kind']} {(budget['discovery_slots'] or {}).get('locality')}")
        expect(not budget["quick_replies"], f"typed wildcard reaches button-free budget prompt: {budget['quick_replies']}")
        results = ask("any budget")
        expect(results["discovery_kind"] == "results", f"'any budget' -> {results['discovery_kind']}")
    elif name == "T4":
        ask("Show me 3 BHK")
        budget = ask("anywhere")
        expect((budget["discovery_slots"] or {}).get("locality") == "any", f"'anywhere' -> {budget['discovery_kind']}")
        results = ask("80 lakh")
        expect(results["discovery_kind"] == "results" and (results["discovery_slots"] or {}).get("budget_max_inr") == 8_000_000,
               f"'80 lakh' -> {results['discovery_kind']} budget={(results['discovery_slots'] or {}).get('budget_max_inr')}")
    elif name == "T5":
        ask("Show me 3 BHK")
        unknown = ask(live["unknown_place"])
        expect(unknown["discovery_kind"] == "locality_not_found"
               and unknown["quick_replies"] == (unknown["options"] or [])
               and "Any area" not in unknown["quick_replies"],
               f"unknown place -> {unknown['discovery_kind']}, buttons={unknown['quick_replies']}")
        expect(live["unknown_place"] not in json.dumps(unknown["discovery_slots"]), "unknown place not stored")
        after = ask("Any area")
        expect(after["discovery_kind"] == "budget_question", f"'Any area' after not-found -> {after['discovery_kind']}")
    elif name == "T6":
        first = ask("Show me 3 BHK")
        city = live["city_not_option"]
        if city and first["discovery_kind"] == "locality_question" and city not in (first["options"] or []):
            typed = ask(city)
            expect(typed["discovery_kind"] == "budget_question" and (typed["discovery_slots"] or {}).get("locality") == city,
                   f"typed city '{city}' -> {typed['discovery_kind']}")
        else:
            expect(True, f"N/A typed-city case (city={city}, first={first['discovery_kind']})")
        if live["no_3bhk_place"]:
            fresh = _Conversation(client, endpoint_key, secrets)
            fresh.ask("Show me 3 BHK")
            none = fresh.ask(live["no_3bhk_place"])
            conversation.turns.extend(fresh.turns)
            expect(none["discovery_kind"] == "locality_not_found",
                   f"place without 3BHK '{live['no_3bhk_place']}' -> {none['discovery_kind']}")
        else:
            expect(True, "N/A: every live place lists 3BHK")
    elif name == "T7":
        first = ask("Show me 3 BHK")
        tap = _first_option(first) if first["discovery_kind"] == "locality_question" else None
        if tap:
            ask(tap)
        shortlist = ask("1.5 crore")
        project = _first_option(shortlist) or live["any_project"]
        amenities = ask(f"What amenities does {project} have?")
        expect(not amenities["discovery_kind"], f"amenities digression -> {str(amenities['answer'])[:80]}")
        two = ask("2 BHK?")
        # Either is acceptable: the current project answers a bare follow-up, or the saved slots are reused.
        for_project = f"Home types in {project}" in str(two["answer"])
        reused = (two["discovery_kind"] in {"results", "budget_question"}
                  and (two["discovery_slots"] or {}).get("config") == ["2"])
        expect(for_project or reused,
               f"'2 BHK?' -> {'current project ' + project if for_project else two['discovery_kind']} "
               f"slots={two['discovery_slots']}")
        evidence.append(f"NOTE '2 BHK?' answered for: {'current project' if for_project else 'saved slots'}")
        # A different live city named in the customer's own words is a catalogue search, never the project.
        city = next((p for p in (other_loc, loc) if p and p != tap), "")
        if city:
            override = ask(f"3 BHK in {city}")
            expect(override["discovery_kind"] in {"locality_question", "budget_question", "results"}
                   and "Home types in" not in str(override["answer"])
                   and override["catalogue_home_type_search"] is True,
                   f"'3 BHK in {city}' after a project turn -> {override['discovery_kind']} "
                   f"catalogue={override['catalogue_home_type_search']} slots={override['discovery_slots']} "
                   f"answer={str(override['answer'])[:80]}")
        else:
            expect(True, "N/A: only one live 3BHK area")
    elif name == "T8":
        first = ask("Show me 3 BHK")
        tap = _first_option(first) if first["discovery_kind"] == "locality_question" else None
        if tap:
            ask(tap)
        reset = ask("start over")
        problems = _reset_problems(reset, data)
        expect(not problems, f"bare 'start over' -> fixed reply: {str(reset['answer'])[:120]}"
               + (f" PROBLEMS {problems}" if problems else ""))
        again = ask("Show me 3 BHK")
        expect(again["discovery_kind"] in {"locality_question", "budget_question"} and
               (again["discovery_kind"] != "budget_question" or live["single_3bhk_area"]),
               f"after 'start over', 'Show me 3 BHK' -> {again['discovery_kind']}")
        combined = ask("start over, show me 2 BHK")
        slots = combined["discovery_slots"] or {}
        expect(slots.get("config") == ["2"] and slots.get("budget_max_inr") is None and "budget_label" not in slots,
               f"'start over, show me 2 BHK' -> {combined['discovery_kind']} slots={slots}")
    elif name == "T9":
        ask("Show me 3 BHK")
        night = ask("good night")
        expect(night["discovery_kind"] in {"locality_not_found", None},
               f"'good night' -> {night['discovery_kind'] or night['route']} (Phase 2 item e)")
        rera = ask("what is RERA?")
        expect(not rera["discovery_kind"], f"'what is RERA?' -> {rera['route']}: {str(rera['answer'])[:80]}")
    elif name == "T10":
        first = ask("mujhe 3 BHK flat dikhao")
        options = first["options"] or []
        expect(all(f"- {option}" in str(first["answer"]) for option in options),
               f"localized area bullets verbatim: {options}")
        tap = _first_option(first) if first["discovery_kind"] == "locality_question" else None
        if tap:
            ask(tap)
        shortlist = ask("1.5 crore")
        names = shortlist["options"] or []
        expect(shortlist["discovery_kind"] == "results" and all(n in str(shortlist["answer"]) for n in names),
               f"localized shortlist keeps names: {names}")
    elif name == "T11":
        previous = os.environ.get("ACROBUILD_DISCOVERY_SLOTS")
        os.environ["ACROBUILD_DISCOVERY_SLOTS"] = "false"   # this process only
        try:
            turn = ask("Show me 3 BHK")
        finally:
            if previous is None:
                os.environ.pop("ACROBUILD_DISCOVERY_SLOTS", None)
            else:
                os.environ["ACROBUILD_DISCOVERY_SLOTS"] = previous
        expect(not turn["discovery_kind"] and turn["clarification_entity"] == "project"
               and (turn["pending_options"] or []) and set(turn["pending_options"]) <= set(data["project_names"]),
               f"flag off -> entity={turn['clarification_entity']}, options={turn['pending_options']}")
    elif name == "T12":
        turn = ask("3 BHK in any area, any budget")
        expect(turn["discovery_kind"] == "results", f"-> {turn['discovery_kind']}")
        unpriced = [n for n in data["project_names"]
                    if _expected_estimate(data, n, ["3"]) is None
                    and any("3" in _numbers(r) for r in data["_typologies_by_project"].get(n, []))]
        if unpriced:
            expect("Pricing not listed:" in str(turn["answer"]), f"unpriced 3BHK projects {unpriced} listed as 'Pricing not listed'")
        else:
            expect(True, "N/A: every 3BHK project has a per-sq-ft rate")
    for turn in conversation.turns:
        if turn["discovery_kind"]:
            expect(turn["source_status"] == "live_api",
                   f"turn '{turn['user']}': discovery source={turn['source_status']}")
        for problem in _name_checks(turn, data) + _honesty(turn):
            expect(False, f"turn '{turn['user']}': {problem}")
        if turn["leaks"]:
            expect(False, f"turn '{turn['user']}': leak {turn['leaks']}")
        if turn["duration_ms"] > SLOW_TURN_MS:
            evidence.append(f"SLOW turn '{turn['user']}': {turn['duration_ms']} ms")
    return {"result": "PASS" if ok else "FAIL", "evidence": evidence, "turns": conversation.turns}


def _run_discovery_acceptance():
    from services.acrobuild_company_service import _cs_api_config
    from services.discovery_slot_service import discovery_enabled
    if not discovery_enabled():
        raise SystemExit("Discovery is disabled. Set ACROBUILD_DISCOVERY_SLOTS=true for this acceptance run.")
    preflight = _preflight()
    print("PREFLIGHT:", json.dumps(preflight), flush=True)
    if ("cs_api_error" in preflight or "llm_error" in preflight
            or not preflight["cs_api_configured"] or not preflight["llm_configured"]
            or not preflight.get("cs_api_projects") or not preflight.get("llm_reply_chars")):
        raise SystemExit("Live dependency unavailable; stopping without transcripts.")
    data = _data_checks()
    public = {k: v for k, v in data.items() if not k.startswith("_")}
    print("DATA CHECKS:", json.dumps(public, ensure_ascii=False, indent=2), flush=True)
    if data["typology_fetch_errors"] or not data["projects"] or not data["typologies"]:
        raise SystemExit("Incomplete live discovery catalogue; stopping without acceptance.")

    # Secrets are held in memory only, to detect echoes; never printed or stored.
    secrets = [_cs_api_config().get("api_key") or "", os.environ.get("RUNPOD_API_KEY", "")]
    three = [n for n in data["project_names"]
             if any("3" in _numbers(r) for r in data["_typologies_by_project"].get(n, []))]
    by_name = {str(p.get("projectName")): p for p in data["_projects"]}
    three_places = sorted({str(by_name[n].get("locality") or by_name[n].get("city") or "").strip() for n in three} - {""})
    all_places = {str(p.get(k)).strip() for p in data["_projects"] for k in ("locality", "city") if p.get(k)}
    three_all_places = {str(by_name[n].get(k)).strip() for n in three for k in ("locality", "city") if by_name[n].get(k)}
    cities_3 = sorted({str(by_name[n].get("city") or "").strip() for n in three} - {""} - set(three_places))
    live = {
        "loc": three_places[0] if three_places else "",
        "other_loc": three_places[1] if len(three_places) > 1 else (three_places[0] if three_places else ""),
        "unknown_place": next(p for p in ("Kharadi", "Atlantis Nagar", "Zzyzx") if p.lower() not in
                              {x.lower() for x in all_places}),
        "city_not_option": cities_3[0] if cities_3 else "",
        "no_3bhk_place": next(iter(sorted(all_places - three_all_places)), ""),
        "single_3bhk_area": len(three_places) == 1,
        "any_project": three[0] if three else "",
    }
    print("TRANSCRIPT INPUTS:", json.dumps(live, ensure_ascii=False), flush=True)

    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8")) if RESULTS_PATH.exists() else {}
    discovery = {"flag": ("ACROBUILD_DISCOVERY_SLOTS=true (explicit configuration)"
                          if "ACROBUILD_DISCOVERY_SLOTS" in os.environ else "default-on (flag unset)"),
                 "started_at": datetime.now(timezone.utc).isoformat(),
                 "preflight": preflight, "data_checks": public, "inputs": live, "transcripts": {}}
    with TestClient(api) as client:
        for name in [f"T{i}" for i in range(1, 13)]:
            discovery["transcripts"][name] = {}
            for endpoint_key in ENDPOINTS:
                print(f"== {name} [{endpoint_key}]", flush=True)
                try:
                    outcome = _run_transcript(name, client, endpoint_key, secrets, data, live)
                except Exception as error:
                    outcome = {"result": "FAIL", "evidence": [f"FAIL exception {_safe_error(error)}"], "turns": []}
                discovery["transcripts"][name][endpoint_key] = outcome
                print(f"   -> {outcome['result']}", flush=True)
                results["discovery"] = discovery
                RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    latency = {}
    for endpoint_key in ENDPOINTS:
        durations = [turn["duration_ms"] for t in discovery["transcripts"].values()
                     for turn in t[endpoint_key]["turns"]]
        latency[endpoint_key] = {"turns": len(durations),
                                 "median_ms": round(statistics.median(durations), 1) if durations else None,
                                 "max_ms": max(durations) if durations else None,
                                 "over_8s": sum(1 for d in durations if d > SLOW_TURN_MS)}
    discovery["latency"] = latency
    discovery["summary"] = {name: {k: v["result"] for k, v in t.items()} for name, t in discovery["transcripts"].items()}
    discovery["completed_at"] = datetime.now(timezone.utc).isoformat()
    discovery["passed"] = all(result == "PASS" for endpoints in discovery["summary"].values()
                              for result in endpoints.values())
    results["discovery"] = discovery
    RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("LATENCY:", json.dumps(latency), flush=True)
    print("SUMMARY:", json.dumps(discovery["summary"]), flush=True)
    return discovery["passed"]


if __name__ == "__main__" and "--discovery" in sys.argv[1:]:
    raise SystemExit(0 if _run_discovery_acceptance() else 1)

scenarios = {
    # The live catalogue has split the former single "Vishwajeet Precious"
    # project into two named variants, "Vishwajeet Precious(Pearl)" and
    # "Vishwajeet Precious (Emerald)" (project ids 52 and 89). Per AGENTS.md's
    # clarification contract, a full suffixed name takes precedence over its
    # contained base name, so an answer of plain "Vishwajeet Precious" now
    # correctly triggers a second clarification between the two variants
    # instead of resolving straight through. These scenarios name the
    # intended variant explicitly to exercise the direct-resolution path.
    "precious": ["vishwajeet lo amenities em em vunnai?", "Vishwajeet Precious(Pearl)"],
    "cost": ["What is the cost in Vishwajeet?", "Vishwajeet Precious(Pearl)"],
    "location": ["Where is the project located?", "Vishwajeet Precious(Pearl)"],
    "wing": ["Show me wings in Vishwajeet Myspace", "Venus A", "1", "__first_flat__"],
}
results = {}
with TestClient(api) as client:
    for name, questions in scenarios.items():
        turns: list = []
        results[name] = turns
        conversation_id = "live-audit-" + str(uuid.uuid4())
        for question in questions:
            if question == "__first_flat__":
                question = turns[-1]["response"]["pending_project_lookup"]["options"][0]
            print("USER:", question, flush=True)
            response = client.post("/api/support/assist/stream", json={"issue": question, "conversation_id": conversation_id})
            response.raise_for_status()
            events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
            payload = next(event["response"] for event in events if event.get("type") == "done")
            turns.append({"user": question, "response": payload})
            print("ASSISTANT:", payload.get("answer"), flush=True)
            RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

for name, turns in results.items():
    assert all(t["response"].get("source_status") == "live_api" for t in turns), name
    assert all("could not verify one live answer" not in t["response"]["answer"] for t in turns), name
assert results["precious"][1]["response"]["answer"].count("\n- ") == 14
assert any(c.get("endpoint") == "/api/cs/projects/52/amenities" and c.get("status") == "completed"
           for c in results["precious"][1]["response"]["data_api_calls"])
assert "base pricing" in results["cost"][1]["response"]["answer"]
assert "Venus A" in results["wing"][1]["response"]["answer"]
assert "flat" in results["wing"][2]["response"]["answer"].lower()
assert "Flat " + results["wing"][3]["user"] in results["wing"][3]["response"]["answer"]
print("ALL LIVE CONVERSATION ASSERTIONS PASSED", flush=True)
