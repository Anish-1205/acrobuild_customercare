"""Discovery slot flow: configuration -> locality -> budget -> matching projects.

Inquiry to Sales §28 (the customer should not have to repeat "3 BHK", "Wakad",
"1.5 crore"), §32 (dynamic facts only from the live API, never guessed) and
§14 (cost figures are estimates; this flow never presents a cost sheet).

``build_discovery_answer()`` returns a payload-shaped *draft*. The router
(Phase 1 Step 5) passes it through the clarification contract, the live-data
guard and localization like every other property answer. This module is
stateless and pure apart from its reads through services/property_tools_service.py.

Locality values come only from live project records (a project's ``locality``
or ``city``), or the literal "any". The customer's own text is never stored as
a locality; an unknown place is quoted back once, sanitised, and never searched.

Slot and pending state are untrusted input (they can come from client-supplied
history): both are re-validated here and the locality is re-checked against
live data on every use.
"""
import os
import re
from time import monotonic
from typing import Any, Callable, Iterable, Literal

from services import property_tools_service as tools
from services.conversation_store_service import build_discovery_slots_marker, get_discovery_slots
from services.observability import get_logger, kv
from services.project_home_type_service import is_catalogue_home_type_query, requested_home_types

logger = get_logger("discovery")

ANY = "any"

_MAX_ISSUE_CHARS = 500
_MAX_REPLY_CHARS = 120
_MAX_BUDGET_TEXT_CHARS = 300
_MAX_PROJECT_NAMES = 500
_MAX_OPTIONS = 50
_MAX_ECHO_CHARS = 40
_MAX_INR = 10**10

_MARKER_CHAR = "⁣"
_CONTROL_CHARS_RE = re.compile("[\\x00-\\x1f\\x7f-\\x9f]")

DISCLAIMER = (
    "Estimated base amount = minimum listed rate x saleable area. It is a base estimate only and "
    "excludes taxes, registration, floor rise and parking; rates can change."
)


# -----------------------------------
# FEATURE FLAG
# -----------------------------------

def discovery_enabled() -> bool:
    """ACROBUILD_DISCOVERY_SLOTS, read on every call. Default on after live acceptance."""
    return os.getenv("ACROBUILD_DISCOVERY_SLOTS", "true").strip().lower() in {"1", "true", "yes", "on"}


# -----------------------------------
# TEXT HELPERS
# -----------------------------------

def _clean(text, limit=_MAX_ISSUE_CHARS):
    """Single-line text without marker or control characters, bounded."""
    value = str(text or "")[: limit * 4].replace(_MARKER_CHAR, "")
    return " ".join(_CONTROL_CHARS_RE.sub(" ", value).split())[:limit]


def _norm(text):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).split())


def _contains_phrase(text_norm, phrase):
    phrase_norm = _norm(phrase)
    return bool(phrase_norm) and f" {phrase_norm} " in f" {text_norm} "


def _config_phrase(config):
    return " and ".join(f"{number}BHK" for number in config) if config else "home"


def _format_inr(value):
    if value >= 10**7:
        return f"INR {value / 10**7:.2f} crore"
    return f"INR {value / 10**5:.2f} lakh"


# -----------------------------------
# BUDGET PARSER
# -----------------------------------
# Linear-time patterns only: bounded quantifiers, no nested repetition, and the
# input is truncated before matching.

_NUM = r"(?<![\w.])(\d{1,6}(?:\.\d{1,4})?)"
_UNIT = r"(crores?|cr|lakhs?|lacs?|lac|l)(?![a-z])\.?"
_COMPOUND_RE = re.compile(_NUM + r"\s*(?:crores?|cr)(?![a-z])\.?\s*(?:and\s+)?" + _NUM + r"\s*(?:lakhs?|lacs?|lac|l)(?![a-z])")
_RANGE_RE = re.compile(_NUM + r"\s*(?:" + _UNIT + r")?\s*(?:to|-|–|and)\s*" + _NUM + r"\s*" + _UNIT)
_SINGLE_RE = re.compile(_NUM + r"\s*" + _UNIT)
_RUPEES_RE = re.compile(r"(?:inr|rs\.?)\s*(\d{5,11})(?!\d)|(?<![\d.])(\d{5,11})\s*(?:rupees?|inr|rs)(?![a-z])")
_NEGATIVE_RE = re.compile(r"(?:^|[^\w.])-\s*\d")
_ANY_BUDGET_RE = re.compile(
    r"\b(?:any|no)\s+(?:budget|limit|amount)\b|\bno\s+(?:budget\s+)?limit\b"
    r"|\bbudget\s+(?:is\s+)?(?:flexible|open|not\s+fixed)\b|\bflexible\s+budget\b"
)
_ANY_BUDGET_WHOLE = frozenset({"any", "anything", "flexible", "open", "not fixed"})


def _unit_multiplier(unit):
    return 10**7 if str(unit).startswith("cr") else 10**5


def _amount(number, unit):
    try:
        value = round(float(number) * _unit_multiplier(unit))
    except (TypeError, ValueError, OverflowError):
        return None
    return value if 1 <= value <= _MAX_INR else None


def _parse_budget(text):
    """(value, label) where value is an int in [1, 10**10] or ANY; None if no budget."""
    t = str(text or "")[:_MAX_BUDGET_TEXT_CHARS].lower().replace("₹", " inr ")
    t = re.sub(r"(?<=\d),(?=\d)", "", t)
    t = re.sub(r"\b(inr|rs\.?)(?=\d)", r"\1 ", t)
    match = _COMPOUND_RE.search(t)
    if match:
        crore, lakh = _amount(match.group(1), "crore"), _amount(match.group(2), "lakh")
        value = (crore or 0) + (lakh or 0)
        return (value, match.group(0).strip()) if crore and lakh and value <= _MAX_INR else None
    match = _RANGE_RE.search(t)
    if match:
        upper_unit = match.group(4)
        lower = _amount(match.group(1), match.group(2) or upper_unit)
        upper = _amount(match.group(3), upper_unit)
        if lower is None or upper is None:
            return None
        return max(lower, upper), match.group(0).strip()
    if _NEGATIVE_RE.search(t):
        return None
    match = _SINGLE_RE.search(t)
    if match:
        value = _amount(match.group(1), match.group(2))
        return (value, match.group(0).strip()) if value else None
    match = _RUPEES_RE.search(t)
    if match:
        value = int(match.group(1) or match.group(2))
        return (value, _format_inr(value)) if 1 <= value <= _MAX_INR else None
    if _ANY_BUDGET_RE.search(t) or " ".join(re.sub(r"[.!]+", " ", t).split()) in _ANY_BUDGET_WHOLE:
        return ANY, "any budget"
    return None


def parse_budget_inr(text) -> int | Literal["any"] | None:
    """Maximum budget in INR (1 to 10**10), ANY for "any budget"/"no limit"/
    "flexible", or None when the text states no budget. Never raises.

    A range ("1 to 1.5 crore") yields its upper bound; a bare number ("1.5",
    "15000000") is not a budget without a unit or currency."""
    parsed = _parse_budget(text)
    return parsed[0] if parsed else None


# -----------------------------------
# LOCALITY MATCHING (live values only)
# -----------------------------------

_ANY_AREA_RE = re.compile(
    r"\b(?:any\s*where|any\s+(?:area|locality|location|place|city)|all\s+areas|no\s+preference"
    r"|(?:doesn'?t|does\s+not)\s+matter)\b"
)
_PLACE_PHRASE_RE = re.compile(
    r"\b(?:in|at|near|around)\s+([a-z][a-z .'-]{0,39}?)"
    r"(?=\s+(?:under|below|within|upto|up|for|with|budget|around|max|maximum|less|and|or|area|locality)\b"
    r"|\s+\d|[,.?!]|$)",
    re.IGNORECASE,
)
_SELECTED_PLACE_RE = re.compile(r"\b(?:selected|requested)\s+locality:\s*([^.\n]{1,80})", re.IGNORECASE)
_REPLY_PREFIX_RE = re.compile(r"^(?:(?:in|at|near|around|the|my|preferred|area|locality|is)\s+)+", re.IGNORECASE)
_REPLY_SUFFIX_RE = re.compile(r"(?:\s+(?:area|locality|side|please|only|lo|mein))+$", re.IGNORECASE)
_PLACE_LIKE_RE = re.compile(r"[a-z][a-z .'-]{0,39}", re.IGNORECASE)
_NOT_A_PLACE = frozenset({
    "hi", "hello", "hey", "thanks", "thank you", "ok", "okay", "yes", "no", "yeah", "yep", "nope", "sure",
    "cancel", "stop", "bye", "help", "retry", "again", "try again", "never mind", "nevermind", "start over",
    "reset", "good morning", "good evening", "good afternoon", "fine", "great", "cool", "home", "homes",
    "flat", "flats", "project", "projects", "budget", "my budget", "the budget", "any", "all", "total",
    "total budget", "range", "my range", "the area", "this area", "that area", "same", "same area",
})


def _place_index(items):
    """{normalised live value: canonical live value} for the given search items."""
    index = {}
    for item in items:
        for value in tools.project_localities(item["project"]):
            index.setdefault(_norm(value), value)
    return index


def _display_localities(items):
    places = {_clean(item["project"].get("locality")) or _clean(item["project"].get("city")) for item in items}
    return sorted((place for place in places if place), key=str.lower)[:_MAX_OPTIONS]


def _natural_list(values):
    values = list(values)
    if len(values) < 2:
        return "".join(values)
    if len(values) == 2:
        return " and ".join(values)
    return ", ".join(values[:-1]) + ", and " + values[-1]


def _catalogue_summary(slots, items, search):
    """Grounded answer-first summary from this search's already-loaded records.

    Discovery has verified catalogue typologies at this point, not available
    units. Keep that distinction explicit and do not trigger any inventory read.
    When a project read was skipped, qualify the count rather than presenting it
    as complete coverage.
    """
    config = slots.get("config") or []
    count = len(items)
    places = _display_localities(items)
    noun = "project" if count == 1 else "projects"
    coverage = "Among the projects successfully checked, the" if search.get("skipped") else "The"
    if len(places) == 1:
        location = f" in {places[0]}"
    elif places:
        location = f" across {_natural_list(places)}"
    else:
        location = ""
    return (
        f"{coverage} current catalogue lists {_config_phrase(config)} configurations in {count} {noun}{location}.\n"
        "This confirms catalogue listings only; current unit availability has not been checked yet."
    )


def _active_budget_note(slots):
    if "budget_max_inr" not in slots:
        return ""
    budget = slots.get("budget_max_inr")
    if isinstance(budget, int):
        return f"I've kept your budget of up to {_format_inr(budget)}."
    return "I've kept your preference to browse without a budget limit."


def _match_places(text, index):
    """Canonical live values named in ``text``: longest first, nested names
    dropped. More than one distinct place means the text is ambiguous."""
    text_norm = _norm(text)
    found = [key for key in sorted(index, key=len, reverse=True) if _contains_phrase(text_norm, key)]
    distinct = [key for key in found if not any(other != key and f" {key} " in f" {other} " for other in found)]
    return [index[key] for key in distinct]


def _place_candidate(text, reply_mode):
    """A place-like phrase the customer typed (for an honest "not found"), or None.
    Case is kept so the quote-back matches what the customer wrote."""
    cleaned = _clean(text)
    selected = _SELECTED_PLACE_RE.search(cleaned)
    if selected:
        return selected.group(1).strip()
    match = _PLACE_PHRASE_RE.search(cleaned)
    if match and "budget" not in match.group(1).lower():
        candidate = match.group(1).strip(" .'-")
        return candidate if candidate and candidate.lower() not in _NOT_A_PLACE else None
    if reply_mode:
        return _reply_place(cleaned)
    return None


def _reply_place(reply):
    """The place a short slot reply names ("in Wakad", "Wakad side"), or None."""
    text = _clean(reply, _MAX_REPLY_CHARS).rstrip(" .!")
    text = _REPLY_SUFFIX_RE.sub("", _REPLY_PREFIX_RE.sub("", text)).strip()
    if (not text or text.lower() in _NOT_A_PLACE or not _PLACE_LIKE_RE.fullmatch(text)
            or len(text.split()) > 4):
        return None
    return text


def _is_locality_reply(text):
    """"Any area", or a short place-like reply that is not a question."""
    lowered = _clean(text, _MAX_REPLY_CHARS).lower()
    if _ANY_AREA_RE.search(lowered):
        return True
    return "?" not in lowered and not _QUESTION_WORD_RE.search(lowered) and _reply_place(text) is not None


def _echo(candidate):
    """Customer text safe to quote back: letters only, bounded, no markers."""
    text = _clean(candidate, _MAX_ECHO_CHARS)
    return text if re.fullmatch(r"[A-Za-z][A-Za-z .'-]{0,39}", text) else ""


# -----------------------------------
# REQUEST / REPLY DETECTION
# -----------------------------------

_SPECIFIC_REQUEST_RE = re.compile(
    r"\b(?:wings?|towers?|floors?|flat\s*(?:no\.?|number|#)?\s*\d+|unit\s*(?:no\.?|number|#)?\s*\d+|amenit\w*|"
    r"facilit\w*|location|located|address|where|documents?|brochure|possession|construction|site\s+visits?|"
    r"prices?|pricing|cost\w*|rates?|compare|comparison)\b"
)
_RECOMMENDATION_RE = re.compile(
    r"\b(?:recommend\w*|suggest\w*|best|cheapest|cheaper|affordable|lowest|budget[- ]friendly|low[- ]cost|"
    r"value\s+for\s+money)\b"
)
_QUANTITY_RE = re.compile(
    r"\b(?:one|two|three|four|both|2|3|4)\s+(?:of\s+)?(?:the\s+)?(?:[1-6]\s*b(?:h)?ks?\s+)?"
    r"(?:flats|homes|apartments|units)\b"
    r"|\b(?:one|two|three|four|both)\s+(?:of\s+)?(?:the\s+)?[1-6]\s*b(?:h)?ks?\b"
    r"|\bflats\s+of\s+[1-6]\s*b(?:h)?k"
)
_SUFFICIENCY_RE = re.compile(
    r"\b(?:is|will)\s+(?:it|this|that)\s+(?:be\s+)?(?:sufficient|enough)\b|\bcan\s+i\s+(?:afford|buy)\s+it\b"
)
_REQUESTED_PROJECT_RE = re.compile(r"\brequested\s+project\s*:", re.IGNORECASE)
_QUESTION_WORD_RE = re.compile(
    r"\b(?:what|which|where|when|why|who|how|show|list|tell|amenit\w*|facilit\w*|visit|document\w*|"
    r"ticket|call|contact|price|pricing|cost|brochure)\b"
)
_RESET_RE = re.compile(
    r"^\s*(?:please\s+)?(?:start\s+over|reset|new\s+search|clear\s+(?:my\s+)?(?:preferences|filters|search))\b"
)
_RESET_ONLY_RE = re.compile(
    r"\s*(?:please\s+)?(?:start\s+over|reset|new\s+search|clear\s+(?:my\s+)?(?:preferences|filters|search))"
    r"(?:\s+(?:please|now|again))*[\s.!]*"
)
# The resolver's own trailing line (graph/haystack_conversation_pipeline.py).
_INJECTED_PROJECT_RE = re.compile(r"\n[ \t]*Requested project:[^\n]*\Z", re.IGNORECASE)
_THIS_PROJECT_RE = re.compile(r"\b(?:this|that|the\s+same|current)\s+project\b")

RESET_ANSWER = (
    "Done, I've cleared your search preferences. What would you like to look for now? "
    "You can tell me the home size, area or budget you have in mind, or browse all projects."
)


def _names_project(text, project_names):
    text_norm = _norm(text)
    return any(_contains_phrase(text_norm, name) for name in list(project_names or ())[:_MAX_PROJECT_NAMES])


def is_discovery_request(issue, project_names: Iterable[str] = ()) -> bool:
    """A configuration search with no project in scope (IS §28).

    False for anything an existing builder owns: a named project or an
    injected "Requested project:", wing/floor/flat/amenity/location/document
    and cost questions, catalogue filters ("which projects have 3BHK"),
    recommendations, quantity requests ("two 2BHK flats") and affordability
    follow-ups -- the last three belong to the budget recommenders in
    services/ai_agent_service.py."""
    text = _clean(issue)
    lowered = text.lower()
    if not requested_home_types(text):
        return False
    if _REQUESTED_PROJECT_RE.search(text) or _names_project(text, project_names):
        return False
    if _SELECTED_PLACE_RE.search(lowered):
        # A resumed discovery question ("... Selected locality: X").
        return True
    if (_SPECIFIC_REQUEST_RE.search(lowered) or _RECOMMENDATION_RE.search(lowered)
            or _QUANTITY_RE.search(lowered) or _SUFFICIENCY_RE.search(lowered)):
        return False
    return not is_catalogue_home_type_query(text)


def is_reset_request(text) -> bool:
    """"start over" / "reset" / "new search" / "clear my preferences"."""
    return bool(_RESET_RE.search(_clean(text, _MAX_REPLY_CHARS).lower()))


def is_reset_only(text) -> bool:
    """A reset and nothing else: "start over", "reset please". Not "reset my
    password" or "start over, show me 2 BHK", which carry a request of their own."""
    return bool(_RESET_ONLY_RE.fullmatch(_clean(text, _MAX_REPLY_CHARS).lower()))


def build_reset_answer() -> dict:
    """Fixed acknowledgement for a bare reset. Deterministic: no LLM, no live
    read, and no place, configuration or figure -- those would have to come from
    history. Route "general" keeps it out of the live-data guard, which downgrades
    a "property" answer that made no live read."""
    return {
        "agent_mode": "knowledge_retrieval",
        "answer": RESET_ANSWER,
        "articles": [],
        "assist_error": "",
        "confidence_label": "medium",
        "handoff_recommended": False,
        "knowledge_documents": [],
        "matched_chunks": [],
        "model": "",
        "quick_replies": [{"label": "Browse all projects", "value": "Show me all projects",
                           "action": "browse_projects"}],
        "retrieval_mode": "none",
        "route": "general",
        "source_label": "Acrobuild Support",
        "source_status": "workspace",
        "used_llm": False,
    }


def explicit_locality_search_text(issue, live_places: Callable[[], Iterable[str]],
                                  project_names: Iterable[str] = ()) -> str | None:
    """The customer's own words when they ask for a configuration in a live area
    while the contextual resolver has pinned a project to the turn; else None.

    The resolver appends "Requested project: X" to a configuration question when a
    project is in context, and a discovery request never carries one. A live
    locality or city in the customer's own text, with a BHK type and no project
    named, is a catalogue search: the caller answers this text instead, and the
    project in context does not decide it. A bare follow-up ("2 BHK?"), a place that
    is not live ("Kharadi") and a reference to "this project" all return None, so
    today's routing applies. ``live_places`` is a callable so the live read only
    happens once the cheap checks have passed."""
    if not discovery_enabled():
        return None
    raw = str(issue or "")
    own = _INJECTED_PROJECT_RE.sub("", raw)
    if own == raw:
        return None                       # nothing injected: the normal path already decides
    own = _clean(own)
    if _THIS_PROJECT_RE.search(own.lower()) or not is_discovery_request(own, project_names):
        return None
    index = {_norm(place): place for place in list(live_places())[:_MAX_OPTIONS * 10] if _norm(place)}
    return own if _match_places(own, index) else None


def _trusted_slots(slots):
    """Slots re-validated through the marker schema (drops forged values)."""
    if not isinstance(slots, dict) or not slots:
        return {}
    return get_discovery_slots(build_discovery_slots_marker(slots)) or {}


def is_slot_reply(slots, reply) -> bool:
    """True only when a slot is awaited AND the reply parses as that slot.

    Greetings, new questions, a new configuration and unrelated numbers are
    not slot replies; they route through the normal pipeline."""
    awaiting = _trusted_slots(slots).get("awaiting")
    text = _clean(reply, _MAX_REPLY_CHARS * 2)
    if awaiting not in {"locality", "budget"} or not text or len(text) > _MAX_REPLY_CHARS:
        return False
    lowered = text.lower()
    if requested_home_types(text) or is_reset_request(text):
        return False
    if awaiting == "budget":
        return parse_budget_inr(text) is not None and not _QUESTION_WORD_RE.search(lowered)
    return _is_locality_reply(text)


def extract_discovery_slots(text, live_places: Iterable[str] = ()) -> dict:
    """Slots stated in ``text`` (English rendering). Pure: no API calls.

    ``locality`` is set only to a value from ``live_places`` (case- and
    whitespace-insensitive, longest match, never fuzzy) or to ANY."""
    cleaned = _clean(text)
    slots: dict[str, Any] = {}
    config = requested_home_types(cleaned)
    if config:
        slots["config"] = config
    parsed = _parse_budget(cleaned)
    if parsed:
        value, label = parsed
        slots["budget_max_inr"] = None if value == ANY else value
        slots["budget_label"] = label
    if _ANY_AREA_RE.search(cleaned.lower()):
        slots["locality"] = ANY
    else:
        index = {_norm(place): place for place in list(live_places)[:_MAX_OPTIONS * 10] if _norm(place)}
        matches = _match_places(cleaned, index)
        if len(matches) == 1:
            slots["locality"] = matches[0]
    return slots


# -----------------------------------
# DRAFTS
# -----------------------------------

def _draft(kind, answer, slots, search, evidence=None, **fields):
    source_status = search["source_status"] if search else "failed"
    draft = {
        "discovery_kind": kind,
        "answer": answer,
        "route": "property",
        "source_status": source_status,
        "agent_mode": "knowledge_retrieval",
        "retrieval_mode": "live_project_records",
        "used_llm": False,
        "confidence_label": "high" if source_status == "live_api" else "low",
        "matched_chunks": list(evidence or []),
        "options": [],
        "quick_replies": [],
        "clarification_entity": None,
        "discovery_slots": _trusted_slots(slots),
        "skipped": list(search.get("skipped") or []) if search else [],
    }
    draft.update(fields)
    return draft


def _skipped_note(search):
    count = len(search.get("skipped") or [])
    if not count:
        return ""
    return (f"\n\nNote: {count} project(s) could not be checked right now because live data was "
            "temporarily unavailable; this list may be incomplete.")


def _selection(entity, options, original_issue, purpose):
    return {"kind": "selection", "entity": entity, "options": list(options), "scope": {},
            "original_issue": original_issue, "purpose": purpose}


def _unavailable_draft(slots, entity, original_issue, purpose):
    answer = "I couldn't check live property data right now. Please try again; I've kept your request."
    return _draft("unavailable", answer, dict(slots), None,
                  pending_project_lookup=_selection(entity, [], original_issue, purpose),
                  clarification_entity=entity)


def _locality_question(slots, search, items, origin, prefix=""):
    config = slots.get("config") or []
    options = _display_localities(items)
    slots = {**slots, "awaiting": "locality"}
    slots.pop("locality", None)
    budget_note = _active_budget_note(slots)
    lines = ([prefix] if prefix else []) + [
        _catalogue_summary(slots, items, search),
        *([budget_note] if budget_note else []),
        f"Matching {_config_phrase(config)} catalogue listings are in these areas:",
        *[f"- {option}" for option in options],
        "Which area would you like to explore?",
    ]
    answer = "\n".join(lines) + _skipped_note(search)
    quick_replies = [{"label": option, "value": option} for option in options]
    return _draft("locality_question", answer, slots, search, search["evidence"],
                  options=options, quick_replies=quick_replies, clarification_entity="locality",
                  pending_project_lookup=_selection("locality", options, origin, "discovery"))


def _no_config_draft(slots, search):
    config = slots.get("config") or []
    slots = {**slots, "awaiting": None}
    slots.pop("locality", None)
    answer = (f"None of the projects in the latest catalogue list {_config_phrase(config)} right now."
              if config else "The live catalogue has no projects to show right now.") + _skipped_note(search)
    return _draft("no_config", answer, slots, search, search["evidence"])


def _budget_question(slots, search, items):
    config = slots.get("config") or []
    locality = slots.get("locality")
    where = f" in {locality}" if locality and locality != ANY else ""
    answer = (
        _catalogue_summary(slots, items, search) + "\n"
        f"What's your approximate budget for a {_config_phrase(config)}{where}? "
        "Type an approximate budget (for example, INR 1.5 crore), or say 'any budget'."
    ) + _skipped_note(search)
    evidence = [chunk for chunk in search["evidence"]
                if any(chunk.get("project") is item["project"] for item in items)]
    return _draft("budget_question", answer, {**slots, "awaiting": "budget"}, search, evidence,
                  discovery_prompt="budget")


def _composed_query(slots):
    config = slots.get("config") or []
    locality = slots.get("locality")
    query = f"Show me {_config_phrase(config)} in {'any area' if locality in (None, ANY) else locality}"
    budget = slots.get("budget_max_inr")
    return f"{query} within about {_format_inr(budget)}" if isinstance(budget, int) else query


def _results_draft(slots, search, items):
    config = slots.get("config") or []
    locality = slots.get("locality")
    budget = slots.get("budget_max_inr")
    where = f" in {locality}" if locality and locality != ANY else ""
    phrase = _config_phrase(config)
    matches = [i for i in items if i["estimated_base_min_inr"] is not None
               and (budget is None or i["estimated_base_min_inr"] <= budget)]
    over = [i for i in items if i["estimated_base_min_inr"] is not None and budget is not None
            and i["estimated_base_min_inr"] > budget]
    unpriced = [i for i in items if i["estimated_base_min_inr"] is None]

    def name(item):
        return str(item["project"].get("projectName") or "").strip()

    def line(item):
        return f"- {name(item)}: estimated base amount from {_format_inr(item['estimated_base_min_inr'])}"

    within = f" within about {_format_inr(budget)}" if budget is not None else ""
    lines = [_catalogue_summary(slots, items, search), ""]
    if matches:
        lines += [f"{phrase} projects{where}{within} (estimated base amount):", *map(line, matches[:_MAX_OPTIONS])]
    elif budget is not None:
        lines.append(f"No current {phrase} projects{where} have an estimated base amount{within}.")
    else:
        lines.append(f"Current {phrase} projects{where}:")
    if over:
        lines += ["", "Above your budget:", *map(line, over[:_MAX_OPTIONS])]
    if unpriced:
        lines += ["", "Pricing not listed:", *[f"- {name(i)}" for i in unpriced[:_MAX_OPTIONS]]]
    lines += ["", DISCLAIMER]
    options = [name(i) for i in (matches + unpriced or over)][:_MAX_OPTIONS]
    lines += ["", "Select a project and I'll check its current details and availability."]
    evidence = [chunk for chunk in search["evidence"]
                if any(chunk.get("project") is item["project"] for item in items)]
    slots = {**slots, "awaiting": None}
    return _draft("results", "\n".join(lines) + _skipped_note(search), slots, search, evidence,
                  options=options, quick_replies=[{"label": o, "value": o} for o in options],
                  clarification_entity="project",
                  pending_project_lookup=_selection("project", options, _composed_query(slots), "home_type_search"))


def _discovery_pending(pending):
    """(locality, original_issue) from a discovery locality selection; untrusted."""
    if not (isinstance(pending, dict) and pending.get("kind") == "selection"
            and pending.get("entity") == "locality" and pending.get("purpose") == "discovery"):
        return None
    scope = pending.get("scope") if isinstance(pending.get("scope"), dict) else {}
    locality = scope.get("locality")
    original = pending.get("original_issue")
    return {
        "locality": _clean(locality, 80) if isinstance(locality, str) else "",
        "original_issue": _clean(original) if isinstance(original, str) else "",
    }


def _log(kind, started, slots, search, options=0):
    """Event name, slot names, counts and duration only -- never customer text."""
    search = search or {}
    data = search.get("data") if isinstance(search.get("data"), dict) else {}
    logger.info("discovery draft %s", kv(
        kind=kind,
        slots=",".join(sorted(key for key, value in slots.items() if value not in (None, "", []))) or "-",
        options=options,
        items=len(data.get("items") or []),
        skipped=len(search.get("skipped") or []),
        tool_status=search.get("status", "not_called"),
        source_status=search.get("source_status", "failed"),
        duration_ms=round((monotonic() - started) * 1000, 1),
    ))


def build_discovery_answer(issue, slots=None, pending=None, project_names: Iterable[str] = ()) -> dict | None:
    """Draft for a discovery turn, or None when this turn is not one or the
    ACROBUILD_DISCOVERY_SLOTS flag is off (IS §28).

    ``issue`` is the English rendering. ``slots`` are the stored discovery
    slots, ``pending`` the stored pending selection, ``project_names`` the live
    project names (a named project is never a discovery request). Every draft
    reads live data through property_tools_service.search_projects()."""
    if not discovery_enabled():
        return None
    started = monotonic()
    text = _clean(issue)
    slots = _trusted_slots(slots)
    pending_state = _discovery_pending(pending)
    new_request = is_discovery_request(text, project_names)
    reply = is_slot_reply(slots, text)
    locality_reply = bool(pending_state) and _is_locality_reply(text)
    if not (new_request or reply or locality_reply):
        return None

    stated = extract_discovery_slots(text)          # config and budget only; locality needs live data
    stated.pop("locality", None)
    working = dict(slots)
    if stated.get("config"):
        working["config"] = stated["config"]
    if "budget_max_inr" in stated:
        working["budget_max_inr"] = stated["budget_max_inr"]
        working["budget_label"] = stated["budget_label"]
    origin = (pending_state or {}).get("original_issue") or (text if new_request else slots.get("origin_issue")) or text
    working["origin_issue"] = origin
    config = working.get("config") or []

    search = tools.search_projects(config, ANY)
    awaiting_locality_step = working.get("locality") in (None, "")
    if search["status"] not in {"ok", "empty", "partial"} or search["source_status"] not in {"live_api", "snapshot", "failed"}:
        entity, purpose, query = (("locality", "discovery", origin) if awaiting_locality_step
                                  else ("project", "home_type_search", _composed_query(working)))
        draft = _unavailable_draft(working, entity, query, purpose)
        _log("unavailable", started, working, search)
        return draft
    items = list((search.get("data") or {}).get("items") or [])
    index = _place_index(items)

    # Locality: an explicit statement this turn wins over the stored slot. A
    # budget reply never names a place, so it is not searched for one.
    locality_turn = new_request or locality_reply or slots.get("awaiting") == "locality"
    any_area = locality_turn and bool(_ANY_AREA_RE.search(text.lower()))
    matches = _match_places(text, index) if locality_turn and not any_area else []
    candidate = None
    if any_area:
        working["locality"] = ANY
    elif len(matches) == 1:
        working["locality"] = matches[0]
    elif len(matches) > 1:
        working.pop("locality", None)
    else:
        if locality_turn:
            candidate = _place_candidate(text, reply_mode=not new_request)
        if pending_state and pending_state["locality"] and not candidate:
            candidate = pending_state["locality"]
        if candidate:
            working.pop("locality", None)
        elif working.get("locality") not in (None, "", ANY) and _norm(working["locality"]) not in index:
            # A stored locality that is no longer (or never was) live is unset.
            working.pop("locality", None)
        elif working.get("locality") not in (None, "", ANY):
            working["locality"] = index[_norm(working["locality"])]

    if not items:
        draft = _no_config_draft(working, search)
    elif candidate:
        echo = _echo(candidate)
        quoted = f"'{echo}'" if echo else "that area"
        prefix = f"I couldn't find any current {_config_phrase(config)} projects in {quoted}."
        draft = _locality_question(working, search, items, origin, prefix)
        draft["discovery_kind"] = "locality_not_found"
    elif working.get("locality") in (None, ""):
        places = _display_localities(items)
        if len(places) <= 1:
            # One live area: select it; no area listed at all: search every area.
            working["locality"] = places[0] if places else ANY
            scoped = [i for i in items if not places or tools.project_in_locality(i["project"], places[0])]
            draft = (_budget_question(working, search, scoped)
                     if "budget_max_inr" not in working else _results_draft(working, search, scoped))
        else:
            draft = _locality_question(working, search, items, origin)
    else:
        locality = working["locality"]
        scoped = items if locality == ANY else [i for i in items if tools.project_in_locality(i["project"], locality)]
        if not scoped:
            prefix = f"No current {_config_phrase(config)} projects are listed in {locality}."
            draft = _locality_question(working, search, items, origin, prefix)
        elif "budget_max_inr" not in working:
            draft = _budget_question(working, search, scoped)
        else:
            draft = _results_draft(working, search, scoped)
    _log(draft["discovery_kind"], started, draft["discovery_slots"], search, len(draft.get("options") or []))
    return draft
