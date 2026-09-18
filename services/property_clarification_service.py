"""Shared live-option and durable-intent contract for all property clarifications.

New handlers should set clarification_entity (project/wing/floor/flat/home_type).
The text detector also covers legacy and generated clarification answers. Always
run this contract before localization and before storing a response.
"""
import re

from services.acrobuild_company_service import (
    customer_facing_projects, get_company_projects, get_project_wings,
    get_wing_inventory, get_wing_typologies, resolve_project_candidates_from_text,
)


# -----------------------------------
# SHARED DISAMBIGUATION COPY
# -----------------------------------
# Every place that asks the customer "which project did you mean?" renders it
# through build_project_choice_answer() so the wording is identical wherever
# the ambiguity is detected (router grounded shortcuts in api_context.py and
# the clarification contract below). Customers who type a family name like
# "vishwajeet" usually do not know the exact project names, so the copy says
# so and offers ways to narrow down that do not require knowing a name.

_LOOKUP_PHRASES = {
    "amenities": "the amenities",
    "pricing": "the pricing",
    "location": "the location",
    "documents": "the site-visit documents",
}


def _shared_name_prefix(names):
    """Longest leading word sequence common to every candidate name, e.g.
    "Vishwajeet" across the Vishwajeet family. Empty when they share nothing,
    so the copy never invents a family that is not in the live names."""
    word_lists = [str(name or "").split() for name in names if str(name or "").strip()]
    if len(word_lists) < 2:
        return ""
    shared = []
    for index in range(min(len(words) for words in word_lists)):
        word = word_lists[0][index]
        if any(words[index].lower() != word.lower() for words in word_lists):
            break
        shared.append(word)
    # All names identical would make the whole name the "family"; that is not
    # a disambiguation case, so drop it.
    if len(shared) >= min(len(words) for words in word_lists):
        return ""
    return " ".join(shared)


def build_project_choice_answer(names, lookup_label=""):
    """Customer-facing "which project?" message. ``names`` are live project
    names only (never generated), so the list is always real."""
    names = [str(name).strip() for name in names if str(name or "").strip()]
    family = _shared_name_prefix(names)
    subject = _LOOKUP_PHRASES.get(str(lookup_label or "").strip().lower(), "")
    opening = (
        f"We have a few {family} projects"
        if family else "A few of our projects could match that"
    )
    purpose = f", so I want to be sure I check {subject} for the right one" if subject else \
        ", so I want to be sure I check the right one"
    lines = [
        f"{opening}{purpose}. You don't need to know the exact name — here they are:",
        "",
        *[f"- {name}" for name in names],
        "",
        # Only alternatives the bot can actually act on are offered. Budget is
        # deliberately NOT one of them: the live API publishes per-sq-ft rate
        # bands, not total prices, so "shortlist what fits 50 lakhs" could only
        # be answered by inventing totals.
        "If one of those is the one you mean, just tell me which. Not sure? I can narrow it "
        "down for you instead — tell me the area you're looking in, or an amenity that "
        "matters to you (a gym or a swimming pool, say), and I'll shortlist the ones that fit.",
    ]
    return "\n".join(lines)


def build_entity_choice_answer(label, options, context=""):
    """The same voice for the within-project selections (wing/floor/flat/home
    type), where the customer is picking from live inventory rather than from
    project names, so the narrowing offers above do not apply."""
    options = [str(option).strip() for option in options if str(option or "").strip()]
    where = f" in {context}" if context else ""
    return "\n".join([
        f"Just so I pull the right details, here are the {label} options available{where}:",
        "",
        *[f"- {option}" for option in options],
        "",
        f"Which {label} should I check? If you're not sure, tell me what you're looking for "
        "and I'll suggest one.",
    ])


def _project_locality_values(project):
    return {str(project.get(key, "") or "").strip()
            for key in ("city", "locality") if str(project.get(key, "") or "").strip()}


def narrow_project_choice_by_locality(pending, text):
    """Answer to "tell me the area you're looking in" -- the other narrowing
    path the disambiguation copy offers.

    Returns a payload shortlisting the pending options that live in the named
    area, or None when the reply names no live city/locality. Place names come
    only from live project records, so an unknown area never matches."""
    if not isinstance(pending, dict) or pending.get("entity") != "project":
        return None
    options = [str(name).strip() for name in (pending.get("options") or []) if str(name).strip()]
    if not options:
        return None
    projects = [project for project in customer_facing_projects(get_company_projects())
                if str(project.get("projectName", "")).strip() in options]
    localities = set()
    for project in projects:
        localities |= _project_locality_values(project)
    normalized = f" {re.sub(r'[^a-z0-9]+', ' ', str(text or '').lower()).strip()} "
    matched = next(
        (locality for locality in sorted(localities, key=len, reverse=True)
         if f" {re.sub(r'[^a-z0-9]+', ' ', locality.lower()).strip()} " in normalized),
        None,
    )
    if not matched:
        return None
    names = [str(project["projectName"]).strip() for project in projects
             if matched in _project_locality_values(project)]
    if not names:
        return None
    answer = "\n".join([
        f"Of those, {'this one is' if len(names) == 1 else 'these are'} in {matched}:",
        "",
        *[f"- {name}" for name in names],
        "",
        "Shall I go ahead with " + (f"{names[0]}?" if len(names) == 1
                                    else "one of these? Just tell me which."),
    ])
    return {
        "agent_mode": "knowledge_retrieval",
        "answer": answer,
        "articles": [],
        "assist_error": "",
        "confidence_label": "high",
        "handoff_recommended": False,
        "knowledge_documents": [],
        "matched_chunks": [{"record_kind": "company_api", "source_key": f"live-projects-in-{matched}",
                            "body_text": "\n".join(names),
                            "title": f"Projects in {matched}"}],
        "model": "",
        "retrieval_mode": "live_project_records",
        "route": "property",
        "source_label": "Retrieved AcroBuild project data",
        "source_status": "live_api",
        "used_llm": False,
        # Keep the customer's original request pending on the shorter list.
        "pending_project_lookup": {**pending, "options": names},
    }


def clarification_entity(payload):
    explicit = payload.get("clarification_entity")
    if explicit in {"project", "wing", "floor", "flat", "home_type"}:
        return explicit
    if payload.get("pending_project_lookup"):
        return "project"
    answer = str(payload.get("answer") or "")
    # Only interrogative/selection clauses, not factual mentions of entities.
    match = re.search(
        r"(?:which|choose|select|pick|specify|share|provide|mention|tell me|would you like me to check another|please ask again as)"
        r"[^.?!\n]{0,95}?\b(home type|configuration|project|property name|wing|tower|floor|flat|unit)\b",
        answer, re.I,
    )
    if not match:
        return None
    return {"property name": "project", "tower": "wing", "unit": "flat",
            "home type": "home_type", "configuration": "home_type"}.get(match[1].lower(), match[1].lower())


def _scope(projects, issue, history):
    for text in [issue, *[m.get("text", "") for m in reversed(history or [])
                           if m.get("sender") == "customer"]]:
        candidates = resolve_project_candidates_from_text(projects, text)
        if candidates:
            return candidates
    return []


def _wing_matches(wings, issue):
    # Explicit full names and labelled short codes only: avoid treating "a"
    # in ordinary English as a selection of wing A.
    result = []
    for wing in wings:
        name = str(wing.get("name") or wing.get("code") or "").strip()
        if name and (re.search(r"\b" + re.escape(name) + r"\s+wing\b", issue, re.I)
                     or re.search(r"\bwing\s*:?\s*" + re.escape(name) + r"\b", issue, re.I)
                     or (len(name) > 1 and re.search(r"\b" + re.escape(name) + r"\b", issue, re.I))):
            result.append(wing)
    return result


def live_options(entity, issue, history):
    projects = customer_facing_projects(get_company_projects())
    candidates = _scope(projects, issue, history)
    if entity == "project" or len(candidates) != 1:
        return "project", [str(p["projectName"]) for p in (candidates or projects)], {}
    project = candidates[0]
    scope = {"project": project["projectName"]}
    wings = get_project_wings(project["id"])
    if entity == "wing":
        return entity, [str(w.get("name") or w.get("code")) for w in wings if w.get("name") or w.get("code")], scope
    selected = _wing_matches(wings, issue)
    if not selected and len(wings) == 1:
        selected = wings
    if len(selected) != 1:
        return "wing", [str(w.get("name") or w.get("code")) for w in wings if w.get("name") or w.get("code")], scope
    wing = selected[0]
    scope["wing"] = str(wing.get("name") or wing.get("code"))
    inventory = get_wing_inventory(wing["id"])
    floor = re.search(r"\bfloor\s*:?\s*(-?\d+)\b|\b(-?\d+)(?:st|nd|rd|th)?\s+floor\b", issue, re.I)
    if floor and entity != "floor":
        number = floor[1] or floor[2]
        inventory = [u for u in inventory if str(u.get("floorNumber")) == number]
        scope["floor"] = number
    if entity == "flat":
        home_types = re.findall(r"\b[1-9]\s*bhk\b", issue, re.I)
        if len(set(t.lower().replace(" ", "") for t in home_types)) == 1:
            home_type = home_types[-1].lower().replace(" ", "")
            inventory = [u for u in inventory if home_type in str(u.get("typologyName", "")).lower().replace(" ", "")]
    key = {"floor": "floorNumber", "flat": "unitNumber", "home_type": "typologyName"}[entity]
    options = list(dict.fromkeys(str(u[key]) for u in inventory if u.get(key) is not None))
    return entity, options, scope


def apply_clarification_contract(payload, issue, history=None):
    if payload.get("route") in {"general", "call_booking", "human_contact"}:
        return payload
    if isinstance(payload.get("pending_project_lookup"), dict):
        return payload
    entity = clarification_entity(payload)
    if not entity:
        return payload
    try:
        entity, options, scope = live_options(entity, issue, history)
    except (RuntimeError, TimeoutError):
        return {**payload, "route": "property", "source_status": "failed",
                "answer": "I could not fetch the live selection options right now. Please retry; I have kept your request.",
                "pending_project_lookup": {"kind": "selection", "original_issue": issue,
                                           "entity": entity, "options": [], "scope": {}}}
    state = {"kind": "selection", "original_issue": issue, "entity": entity,
             "options": options, "scope": scope}
    label = {"home_type": "home type"}.get(entity, entity)
    if options and entity == "project":
        answer = build_project_choice_answer(options, payload.get("pending_project_lookup") or "")
    elif options:
        context = ", ".join(str(value) for value in scope.values())
        answer = build_entity_choice_answer(label, options, context)
    else:
        answer = "The live data currently lists no matching " + label + " options for this request. Please try again later."
    result = dict(payload)
    result.update(answer=answer, pending_project_lookup=state, clarification_entity=entity,
                  route="property", source_status="live_api", used_llm=False,
                  agent_mode="knowledge_retrieval", retrieval_mode="live_project_records", confidence_label="high")
    result["matched_chunks"] = [{"record_kind": "company_api", "source_key": "live-selection-options",
                                 "body_text": "\n".join(options), "title": "Live " + label + " options"}]
    return result


def resume_selection(state, reply):
    """Restore the entire request, not just a category or translated bot text."""
    if reply.strip().lower() in {"retry", "try again", "again", "yes", "yes please"}:
        return state.get("effective_issue") or state["original_issue"]
    options = state.get("options", [])
    if not options:
        # An outage may have prevented the first option list. Keep the supplied
        # selector in the request; the next live lookup still resolves it.
        effective = state["original_issue"] + f". Requested {state['entity']}: {reply}"
        state["effective_issue"] = effective
        return effective
    normalized = re.sub(r"[^a-z0-9]+", " ", reply.lower()).strip()
    normalized = re.sub(r"^(?:let s |lets |let us )?(?:go with|go for|choose|select|pick|take)\s+", "", normalized)
    label = state.get("entity", "").replace("_", " ")
    if label:
        normalized = re.sub(r"^(?:the )?" + re.escape(label) + r"\s+|\s+" + re.escape(label) + r"$", "", normalized).strip()
    matches = [name for name in options if normalized == re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()]
    if not matches and state.get("entity") == "project":
        candidates = resolve_project_candidates_from_text([{"projectName": name} for name in options], reply)
        if len(candidates) == 1:
            matches = [candidates[0]["projectName"]]
    if not matches and normalized:
        matches = [name for name in options if re.search(r"\b" + re.escape(normalized) + r"\b", name, re.I)]
    if len(matches) != 1:
        # Keep the original intent for an invalid or still-ambiguous answer.
        return state["original_issue"]
    scope = dict(state.get("scope") or {})
    scope[state["entity"]] = matches[0]
    context = ". ".join(
        f"{key.replace('_', ' ')}{' ' if key in {'floor', 'flat'} else ': '}{value}"
        for key, value in scope.items()
    )
    effective = state["original_issue"] + ". Selected " + context
    if re.search(r"\b(?:show|list|which|what)\b.{0,30}\bwings\b", state["original_issue"], re.I):
        if "floor" in scope:
            effective = f"Show available homes on floor {scope['floor']} in {scope.get('wing', '')} wing in {scope.get('project', '')}"
        elif "wing" in scope:
            effective = f"Show verified details for {scope['wing']} wing in {scope.get('project', '')}"
    state["effective_issue"] = effective
    state["scope"] = scope
    return effective


def continues_selection(state, reply):
    """New questions/actions replace pending selection; short selectors keep it."""
    text = reply.strip().lower()
    if text in {"cancel", "never mind", "nevermind", "stop", "forget it"}:
        return False
    if text in {"retry", "try again", "again", "yes", "yes please"}:
        return True
    if re.search(r"\b(?:what|where|when|why|how|weather|instead|call|callback|human|agent|representative|cancel)\b", text):
        return False
    return len(text.split()) <= 8


def build_inventory_selection_answer(issue, pending):
    """Resolve staged inventory selections without asking the LLM to infer scope."""
    if not pending or pending.get("kind") != "selection" or not pending.get("effective_issue"):
        return None
    if pending.get("entity") not in {"wing", "floor", "flat", "home_type"}:
        return None
    scope = pending.get("scope") or {}
    projects = customer_facing_projects(get_company_projects())
    matches = resolve_project_candidates_from_text(projects, scope.get("project", ""))
    if len(matches) != 1:
        return apply_clarification_contract({"clarification_entity": "project"}, issue)
    project = matches[0]
    wings = get_project_wings(project["id"])
    wings = [w for w in wings if str(w.get("name") or w.get("code")) == scope.get("wing")]
    if len(wings) != 1:
        return apply_clarification_contract({"clarification_entity": "wing"}, issue)
    wing = wings[0]
    if pending["entity"] == "wing" and re.search(r"\b(?:construction|possession|handover|completion)\b", pending["original_issue"], re.I):
        fields = [("constructionStatus", "Construction status"), ("expectedPossesionDate", "Expected possession"), ("totalFloors", "Total floors")]
        lines = [f"{project['projectName']}, {scope['wing']} wing:"]
        for key, label in fields:
            value = wing.get(key)
            if value is not None:
                if key == "expectedPossesionDate" and isinstance(value, (int, float)):
                    from datetime import datetime, timezone
                    value = datetime.fromtimestamp(value / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                lines.append(f"- {label}: {value}")
        if len(lines) == 1:
            lines.append("The live wing record does not list construction or possession details.")
        return {"answer": "\n".join(lines), "route": "property", "source_status": "live_api",
                "agent_mode": "knowledge_retrieval", "used_llm": False,
                "matched_chunks": [{"record_kind": "company_api", "source_key": f"wing-{wing['id']}", "wing": wing, "body_text": "\n".join(lines)}]}
    if pending["entity"] == "wing":
        return apply_clarification_contract({"clarification_entity": "floor"}, issue)
    units = get_wing_inventory(wing["id"])
    if "floor" in scope:
        units = [u for u in units if str(u.get("floorNumber")) == scope["floor"]]
    if "home_type" in scope:
        units = [u for u in units if str(u.get("typologyName")) == scope["home_type"]]
    if "flat" in scope:
        units = [u for u in units if str(u.get("unitNumber")) == scope["flat"]]
    if pending["entity"] in {"floor", "home_type"} and not any(
        word in pending["original_issue"].lower() for word in ("cost", "price", "pricing", "rate")
    ):
        return apply_clarification_contract({"clarification_entity": "flat"}, issue)
    typologies = {str(t.get("id")): t for t in get_wing_typologies(wing["id"])}
    lines = [f"Live available homes in {project['projectName']}, {scope['wing']} wing:", ""]
    for unit in units:
        detail = [f"Flat {unit.get('unitNumber')}", f"floor {unit.get('floorNumber')}"]
        for key, label in (("typologyName", "configuration"), ("carpetArea", "carpet area"), ("saleableArea", "saleable area")):
            if unit.get(key) is not None:
                detail.append(f"{label}: {unit[key]}" + (" sq. ft." if key in {"carpetArea", "saleableArea"} else ""))
        typology = typologies.get(str(unit.get("typologyId")), {})
        if typology.get("minBasePrice") is not None:
            detail.append(f"base rate: INR {typology['minBasePrice']} to INR {typology.get('maxBasePrice', typology['minBasePrice'])} ({typology.get('rateType') or 'rate basis not specified'})")
        lines.append("- " + "; ".join(detail))
    if not units:
        lines.append("No matching units are currently listed as available. Please retry for updated inventory.")
    payload = {"answer": "\n".join(lines), "route": "property", "source_status": "live_api",
               "retrieval_mode": "live_project_records", "agent_mode": "knowledge_retrieval", "used_llm": False, "confidence_label": "high",
               "matched_chunks": [{"record_kind": "company_api", "source_key": f"wing-{wing['id']}-inventory",
                                    "units": units, "typologies": list(typologies.values()), "body_text": "\n".join(lines)}]}
    if not units:
        payload["pending_project_lookup"] = pending
    return payload
