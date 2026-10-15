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

# Wildcard quick-reply labels. Both parse back through the normal text path
# (_ANY_AREA_RE / _ANY_BUDGET_RE), so a tap is indistinguishable from typing.
# They are offered as buttons only; neither is ever a real live option.
ANY_AREA_LABEL = "Any area"
ANY_BUDGET_LABEL = "Any budget"

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
_COMPOUND_LOCALITY_BUDGET_RE = re.compile(
    r"^\s*(?P<locality>(?:in\s+)?[a-z][a-z .'-]{0,39}?)\s*(?:[,;]\s*|\s+)"
    r"(?=(?:under|below|within|upto|up\s+to|max(?:imum)?|around|budget|any\s+budget|"
    r"no\s+(?:budget|limit)|flexible\s+budget|open\s+budget|₹|inr\b|rs\.?\s*|\d))",
    re.IGNORECASE,
)
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


_COUNT_WORDS = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")


def _plural(count, noun):
    """"1 project" reads as mechanical output; "one project" reads as an answer.
    Small counts are spelled out, larger ones stay numeric."""
    word = _COUNT_WORDS[count] if count < len(_COUNT_WORDS) else str(count)
    return f"{word} {noun}" if count == 1 else f"{word} {noun}s"


def _where(locality):
    """" in Wakad" for a real area; nothing for "any" or no area chosen yet."""
    return f" in {locality}" if locality and locality != ANY else ""


# The catalogue/inventory distinction is a grounding contract, not a polite
# disclaimer: discovery has verified catalogue typologies at this point, never
# available units, and it must not trigger an inventory read to find out. Each
# lead below carries its own short qualifier, so the distinction survives even
# when the locality question is skipped (exactly one eligible area) and the
# customer never sees the locality turn that would otherwise state it.
_LISTINGS_NOTE = "These are catalogue listings; I haven't checked current unit availability yet."
_LISTING_NOTE = "That's a catalogue listing; I haven't checked current unit availability yet."

# The leads are deliberately freshness-neutral: no "as of now", no "currently
# live". api_context._enforce_live_property_data() can prepend a snapshot
# banner ("Live property data is unavailable. This answer uses saved data from
# ...") after these drafts are built, and a present-tense freshness claim would
# then sit underneath it contradicting it. The honest-coverage qualifier for a
# partial read is a separate concern and is still applied below.


def _coverage_prefix(search):
    """Qualifies a count when some project reads were skipped, so a partial
    catalogue is never presented as complete coverage."""
    return "Among the projects I could check, we" if search.get("skipped") else "We"


def _locality_lead(slots, items, search):
    """Answer-first lead for the locality question: the real eligible areas,
    named inline, before anything is asked of the customer."""
    config = slots.get("config") or []
    places = _display_localities(items)
    where = f" in {_natural_list(places)}" if places else ""
    return (f"{_coverage_prefix(search)} have {_plural(len(items), 'project')} listing "
            f"{_config_phrase(config)} homes{where}.\n{_LISTINGS_NOTE}")


def _scoped_lead(slots, items, search):
    """Answer-first lead for the budget question: how many projects match the
    configuration and area the customer has settled on."""
    config = slots.get("config") or []
    count = len(items)
    return (f"{_coverage_prefix(search)} have {_plural(count, 'project')} listed with "
            f"{_config_phrase(config)} configurations{_where(slots.get('locality'))}.\n"
            f"{_LISTING_NOTE if count == 1 else _LISTINGS_NOTE}")


def _results_lead(slots, matches, unpriced, over, search):
    """Answer-first lead for the shortlist.

    Counts what the customer can actually act on -- the priced projects within
    budget, plus those whose pricing is not listed. Counting every retrieved
    project instead would claim "one matching project" immediately above "No
    current 3BHK projects ... have an estimated base amount within ...".
    """
    count = len(matches) + len(unpriced)
    where = _where(slots.get("locality"))
    if not count:
        if over:
            return (f"{_coverage_prefix(search)} found {_plural(len(over), 'project')}{where}, "
                    "but none have an estimated base amount within your budget.")
        return f"{_coverage_prefix(search)} couldn't find a matching project{where} in the catalogue data."
    return f"{_coverage_prefix(search)}'ve got {_plural(count, 'matching project')}{where}."


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
        return _locality_reply_candidate(cleaned)
    return None


def _reply_place(reply):
    """The place a short slot reply names ("in Wakad", "Wakad side"), or None."""
    text = _clean(reply, _MAX_REPLY_CHARS).rstrip(" .!")
    text = _REPLY_SUFFIX_RE.sub("", _REPLY_PREFIX_RE.sub("", text)).strip()
    if (not text or text.lower() in _NOT_A_PLACE or not _PLACE_LIKE_RE.fullmatch(text)
            or len(text.split()) > 4):
        return None
    return text


def _compound_locality_candidate(reply):
    """A locality prefix followed by an already-supported budget expression.

    This helper separates the fields but never interprets money: the existing
    budget parser remains the sole authority for whether the trailing text is a
    supported amount or the established no-filter value.
    """
    text = _clean(reply, _MAX_REPLY_CHARS)
    if parse_budget_inr(text) is None:
        return None
    match = _COMPOUND_LOCALITY_BUDGET_RE.match(text)
    return _reply_place(match.group("locality")) if match else None


def _locality_reply_candidate(reply):
    return _reply_place(reply) or _compound_locality_candidate(reply)


def _is_locality_reply(text):
    """"Any area", or a short place-like reply that is not a question."""
    lowered = _clean(text, _MAX_REPLY_CHARS).lower()
    if _ANY_AREA_RE.search(lowered):
        return True
    return ("?" not in lowered and not _QUESTION_WORD_RE.search(lowered)
            and _locality_reply_candidate(text) is not None)


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
_NUMBER_WORD_RE = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|"
    r"ninety|hundred|thousand)\b"
)
_BUDGET_REPLY_CUE_RE = re.compile(
    r"\bbudget\b|\b(?:crores?|cr|lakhs?|lacs?|lac|rupees?|inr|rs)\b|"
    r"^(?:around|under|below|within|upto|up\s+to|max(?:imum)?)\b"
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
        supported = parse_budget_inr(text) is not None
        ambiguous = _is_ambiguous_budget_reply(text)
        return (supported or ambiguous) and not _QUESTION_WORD_RE.search(lowered)
    return _is_locality_reply(text)


def _is_ambiguous_budget_reply(text):
    """True for an explicit budget-shaped answer the existing parser rejects.

    It is only used after the state says the customer is answering the budget
    question. Number words are detected, never converted, so a phrase such as
    "around one fifty" stays ambiguous instead of acquiring a guessed unit.
    """
    cleaned = _clean(text, _MAX_REPLY_CHARS).lower()
    if not cleaned or parse_budget_inr(cleaned) is not None:
        return False
    return bool(_BUDGET_REPLY_CUE_RE.search(cleaned)
                and (re.search(r"\d", cleaned) or _NUMBER_WORD_RE.search(cleaned)))


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
    return (f"\n\nNote: {_plural(count, 'project')} could not be checked right now because live data "
            "was temporarily unavailable; this list may be incomplete.")


def _selection(entity, options, original_issue, purpose):
    return {"kind": "selection", "entity": entity, "options": list(options), "scope": {},
            "original_issue": original_issue, "purpose": purpose}


def _unavailable_draft(slots, entity, original_issue, purpose):
    answer = "I couldn't check live property data right now. Please try again; I've kept your request."
    return _draft("unavailable", answer, dict(slots), None,
                  pending_project_lookup=_selection(entity, [], original_issue, purpose),
                  clarification_entity=entity)


def _locality_question(slots, search, items, origin, prefix=""):
    options = _display_localities(items)
    slots = {**slots, "awaiting": "locality"}
    slots.pop("locality", None)
    budget_note = _active_budget_note(slots)
    # The question must precede the bullet list. The browser shows only the text
    # before the first bullet when the bullets merely restate the quick replies
    # (src/lib/customerChatContract.ts visibleMessageText), so a question placed
    # after them is never seen. The bullets stay as the plain-text fallback for
    # clients that ignore quick_replies, and those clients also need the
    # wildcard in prose because they cannot see the "Any area" button.
    lines = ([prefix] if prefix else []) + [
        _locality_lead(slots, items, search),
        *([budget_note] if budget_note else []),
        f'Which location would you like to explore? You can also say "any area".',
        *[f"- {option}" for option in options],
    ]
    answer = "\n".join(lines) + _skipped_note(search)
    # "Any area" is offered as a button but is never a real option: it must stay
    # out of `options` and the pending selection (AGENTS.md), and out of the
    # bullets, which must keep matching `options` exactly so the frontend's
    # bullet suppression stays correct.
    quick_replies = [{"label": option, "value": option} for option in options]
    quick_replies.append({"label": ANY_AREA_LABEL, "value": ANY_AREA_LABEL})
    return _draft("locality_question", answer, slots, search, search["evidence"],
                  options=options, quick_replies=quick_replies, clarification_entity="locality",
                  pending_project_lookup=_selection("locality", options, origin, "discovery"))


def _no_config_draft(slots, search):
    config = slots.get("config") or []
    slots = {**slots, "awaiting": None}
    slots.pop("locality", None)
    coverage = "projects I could check" if search.get("skipped") else "projects in the catalogue data"
    answer = (f"None of the {coverage} list {_config_phrase(config)}."
              if config else "The catalogue data has no projects to show.") + _skipped_note(search)
    return _draft("no_config", answer, slots, search, search["evidence"])


def _budget_question(slots, search, items):
    answer = (
        _scoped_lead(slots, items, search) + "\n"
        "Do you have a budget limit, or should I include all prices?\n"
        "Feel free to type your budget in the chat (for example, INR 1.5 crore)."
    ) + _skipped_note(search)
    evidence = [chunk for chunk in search["evidence"]
                if any(chunk.get("project") is item["project"] for item in items)]
    # One convenience button, and deliberately no clarification_entity or
    # pending selection: this step is free text, not a selection, so a typed
    # budget on the next turn must not be read as picking an option.
    return _draft("budget_question", answer, {**slots, "awaiting": "budget"}, search, evidence,
                  quick_replies=[{"label": ANY_BUDGET_LABEL, "value": "any budget"}],
                  discovery_prompt="budget")


def _budget_clarification(slots, search, items):
    answer = (
        "I couldn't safely interpret that budget. Please include an explicit unit, such as crore, lakh, or INR, "
        'or say "any budget" to browse without a budget filter.'
    ) + _skipped_note(search)
    evidence = [chunk for chunk in search["evidence"]
                if any(chunk.get("project") is item["project"] for item in items)]
    return _draft("budget_clarification", answer, {**slots, "awaiting": "budget"}, search, evidence,
                  quick_replies=[{"label": ANY_BUDGET_LABEL, "value": "any budget"}],
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
    lines = [_results_lead(slots, matches, unpriced, over, search), ""]
    if matches:
        lines += [f"{phrase} projects{where}{within} (estimated base amount):", *map(line, matches[:_MAX_OPTIONS])]
    elif budget is not None:
        lines.append(f"No listed {phrase} projects{where} have an estimated base amount{within}.")
    else:
        lines.append(f"Listed {phrase} projects{where}:")
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
    ambiguous_budget = bool(slots.get("awaiting") == "budget" and _is_ambiguous_budget_reply(text))
    working = dict(slots)
    if stated.get("config"):
        working["config"] = stated["config"]
    if "budget_max_inr" in stated:
        working["budget_max_inr"] = stated["budget_max_inr"]
        working["budget_label"] = stated["budget_label"]
    origin = (pending_state or {}).get("original_issue") or (text if new_request else slots.get("origin_issue")) or text
    working["origin_issue"] = origin
    config = working.get("config") or []

    # A locality reply must check the selected area against the current live
    # catalogue, but typology failures in other areas cannot invalidate the
    # selected area's evidence. The tool filters live projects by city/locality
    # before reading typologies. If the area has no current matching records,
    # use the full search so the existing clarification path can offer current
    # eligible alternatives.
    selected_locality = None
    if (pending_state or (reply and slots.get("awaiting") == "locality")) and not _ANY_AREA_RE.search(text.lower()):
        selected_locality = _place_candidate(text, reply_mode=True)
    elif reply and slots.get("awaiting") == "budget" and slots.get("locality") not in (None, "", ANY):
        selected_locality = slots["locality"]
    search = tools.search_projects(config, selected_locality or ANY)
    if (selected_locality and search["status"] in {"ok", "empty"}
            and not (search.get("data") or {}).get("items")):
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
        prefix = f"I couldn't find any listed {_config_phrase(config)} projects in {quoted}."
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
            prefix = f"No {_config_phrase(config)} projects are listed in {locality}."
            draft = _locality_question(working, search, items, origin, prefix)
        elif "budget_max_inr" not in working:
            draft = (_budget_clarification(working, search, scoped)
                     if ambiguous_budget else _budget_question(working, search, scoped))
        else:
            draft = _results_draft(working, search, scoped)
    _log(draft["discovery_kind"], started, draft["discovery_slots"], search, len(draft.get("options") or []))
    return draft
