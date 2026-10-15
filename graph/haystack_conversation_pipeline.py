"""Source-native facade for the readable conversation pipeline.

The reconstructed implementation is imported normally. The small compatibility
overrides preserve established callers, patch points, and reload behavior.
"""
import re as _re

from graph import haystack_conversation_pipeline_source as _source
from graph.haystack_conversation_pipeline_source import *  # noqa: F403

# Keep stable originals across development reloads. The facade bridges below
# intentionally make existing patch points affect functions defined in the
# imported module, whose globals otherwise live in a separate namespace.
_original_search_company_knowledge = getattr(
    _source,
    "_facade_original_search_company_knowledge",
    _source.search_company_knowledge,
)
_original_get_live_project_names = getattr(
    _source,
    "_facade_original_get_live_project_names",
    _source.get_live_project_names,
)
_original_build_deterministic_conversation_answer = getattr(
    _source,
    "_facade_original_build_deterministic_conversation_answer",
    _source.build_deterministic_conversation_answer,
)
_original_is_small_talk_message = getattr(
    _source,
    "_facade_original_is_small_talk_message",
    _source.is_small_talk_message,
)
_original_resolve_contextual_support_issue = getattr(
    _source,
    "_facade_original_resolve_contextual_support_issue",
    _source.resolve_contextual_support_issue,
)
_original_validate_support_node = getattr(
    _source,
    "_facade_original_validate_support_node",
    _source.validate_support_node,
)
_source._facade_original_search_company_knowledge = _original_search_company_knowledge
_source._facade_original_get_live_project_names = _original_get_live_project_names
_source._facade_original_build_deterministic_conversation_answer = (
    _original_build_deterministic_conversation_answer
)
_source._facade_original_is_small_talk_message = _original_is_small_talk_message
_source._facade_original_resolve_contextual_support_issue = _original_resolve_contextual_support_issue
_source._facade_original_validate_support_node = _original_validate_support_node
search_company_knowledge = _original_search_company_knowledge
get_live_project_names = _original_get_live_project_names
build_deterministic_conversation_answer = _original_build_deterministic_conversation_answer
is_small_talk_message = _original_is_small_talk_message
resolve_contextual_support_issue = _original_resolve_contextual_support_issue
validate_support_node = _original_validate_support_node
_conversation_project_name = _source._conversation_project_name

_legacy_build_deterministic_conversation_answer = build_deterministic_conversation_answer
_legacy_is_small_talk_message = is_small_talk_message
_legacy_resolve_contextual_support_issue = resolve_contextual_support_issue
_legacy_validate_support_node = validate_support_node


def _is_capability_question(issue):
    cleaned = normalize_text(issue).lower()
    return any(phrase in cleaned for phrase in (
        "what can you do",
        "what can you help me with",
        "what can you help with",
        "how can you help",
        "what do you support",
    ))


def _deterministic_social_answer(issue):
    """Return natural answers for short social turns that do not need a model."""
    cleaned = _re.sub(r"[^a-z0-9' ]+", " ", normalize_text(issue).lower())
    cleaned = " ".join(cleaned.split())

    day_questions = ("how are you", "how is your day", "how's your day", "how are things")
    if any(question in cleaned for question in day_questions):
        greetings = ("hi", "hello", "hey", "good morning", "good afternoon", "good evening")
        if any(greeting in cleaned for greeting in greetings):
            return "Hi! I'm doing well and ready to help. How is your day going?"
        return "I'm doing well and ready to help. How is your day going?"

    positive_replies = {
        "fine", "i'm fine", "im fine", "i am fine", "doing fine", "i'm doing fine",
        "good", "i'm good", "im good", "i am good", "doing good", "i'm doing good",
        "great", "i'm great", "im great", "i am great", "doing great",
        "well", "i'm well", "im well", "i am well", "doing well", "pretty good",
        "very good", "all good", "not bad", "awesome", "amazing", "wonderful",
        "fantastic", "nice", "okay", "ok",
    }
    if cleaned in positive_replies:
        return "Glad to hear it! What can I help you with today?"

    neutral_replies = {"so so", "could be better", "same as usual", "as usual"}
    if cleaned in neutral_replies:
        return "I understand. If there is anything I can help with, just tell me what you need."

    negative_replies = {
        "bad", "not good", "not fine", "terrible", "awful", "stressed", "tired",
        "i'm not good", "im not good", "i am not good", "couldn't be worse",
    }
    if cleaned in negative_replies:
        return "I'm sorry to hear that. If there is something I can help you with, tell me what happened."

    cleaned = _re.sub(r"\s+", " ", cleaned).strip()

    if _re.search(r"\b(how are you|how is your day|how's your day|how are things)\b", cleaned):
        if _re.search(r"\b(hi|hello|hey|good morning|good afternoon|good evening)\b", cleaned):
            return "Hi! I'm doing well and ready to help. How is your day going?"
        return "I'm doing well and ready to help. How is your day going?"

    if cleaned in {"great", "good", "nice", "awesome", "amazing", "wonderful", "fantastic", "not bad"}:
        return "Glad to hear it! What can I help you with today?"

    if cleaned in {"cool", "sounds good", "got it", "understood", "all right", "alright"}:
        return "Great. What would you like help with next?"

    return ""


def build_social_conversation_answer(issue):
    """Return a stable answer for greetings and other short social turns."""
    return _deterministic_social_answer(issue)


def is_small_talk_message(issue):
    return bool(_deterministic_social_answer(issue)) or _is_capability_question(issue) or _legacy_is_small_talk_message(issue)


def build_deterministic_conversation_answer(issue):
    social_answer = _deterministic_social_answer(issue)
    if social_answer:
        return social_answer
    if _is_capability_question(issue):
        return (
            "I can answer general questions and help with verified Acrobuild information. "
            "For properties, I can check projects, locations, wings, floors, configurations, "
            "live availability, and API-listed pricing. I can also help with site-visit "
            "requests, callback requests, and support tickets."
        )
    return _legacy_build_deterministic_conversation_answer(issue)


_SHORT_FLAT_COST_QUESTIONS = frozenset({
    "what will be the total cost", "how much will it cost", "what would this cost",
    "what is the total", "how much is it", "what will it cost", "how much would it cost",
})


def is_short_flat_cost_question(issue):
    cleaned = normalize_text(issue).lower().strip(" .!?")
    if cleaned.startswith("so "):
        cleaned = cleaned[3:]
    return cleaned in _SHORT_FLAT_COST_QUESTIONS


def _recent_selected_flat_for_cost(issue, conversation_messages):
    """Use only the immediately preceding live, single-flat selection answer."""
    if not is_short_flat_cost_question(issue):
        return ""

    messages = list(conversation_messages or [])
    if messages and str(messages[-1].get("sender") or "").lower() == "customer":
        messages.pop()  # prepare_turn appends the current customer question.
    if (len(messages) < 2 or str(messages[-1].get("sender") or "").lower() != "bot"
            or str(messages[-2].get("sender") or "").lower() != "customer"):
        return ""

    from services.conversation_store_service import get_current_project_context

    stored_answer = str(messages[-1].get("text") or "")
    project = (get_current_project_context(stored_answer) or {}).get("project") or ""
    visible_answer = stored_answer.split("\u2063", 1)[0]
    header = visible_answer.split("\n", 1)[0].strip()
    if not project or not header.lower().startswith(f"live available homes in {project}, ".lower()):
        return ""

    flat_lines = [line for line in visible_answer.splitlines()
                  if _re.match(r"^\s*-\s*Flat\s+", line, _re.I)]
    if len(flat_lines) != 1:
        return ""
    flat_match = _re.match(r"^\s*-\s*Flat\s+([a-z0-9-]+)\s*;", flat_lines[0], _re.I)
    if not flat_match:
        return ""
    flat_number = flat_match[1]
    selection = normalize_text(messages[-2].get("text", "")).lower().strip(" .!?")
    if not _re.fullmatch(rf"(?:select\s+)?(?:flat\s*)?{_re.escape(flat_number.lower())}", selection):
        return ""

    area = _re.search(r"\bsaleable\s+area:\s*([\d,.]+)\s*sq\.?\s*ft\.?\b", flat_lines[0], _re.I)
    rate = _re.search(
        r"\bbase\s+rate:\s*INR\s*([\d,.]+)\s+to\s+INR\s*([\d,.]+)"
        r"\s*\(\s*Rate\s+Per\s+Sq\.?\s*Ft\.?\s*\)", flat_lines[0], _re.I,
    )
    if not area or not rate:
        return ""
    try:
        area_value, low_rate, high_rate = (float(value.replace(",", ""))
                                           for value in (area[1], rate[1], rate[2]))
    except ValueError:
        return ""
    return flat_number if area_value > 0 and 0 < low_rate <= high_rate else ""


def resolve_contextual_support_issue(issue, conversation_messages):
    # "s?" -- a plural mention ("3bhks") names the type as specifically as
    # the singular form and must not be dropped here either.
    issue = _re.sub(r"\b([1-6])\s*b(?:h)?ks?\b", r"\1BHK", str(issue), flags=_re.I)
    cleaned = normalize_text(issue).lower()
    if _re.search(r"\b[1-6]\s*bhk\b", cleaned):
        from services.acrobuild_company_service import resolve_project_candidates_from_text
        projects = [{"projectName": name} for name in get_live_project_names()]
        if resolve_project_candidates_from_text(projects, issue):
            return normalize_text(issue)
        # A portfolio search starts a new scope; a short type follow-up keeps it.
        if not _re.search(r"\b(?:other|another|across|any|which|all|different)\s+projects?\b", cleaned):
            project = _conversation_project_name(conversation_messages)
            if project:
                return f"{normalize_text(issue)}\nRequested project: {project}"
    selected_flat = _recent_selected_flat_for_cost(issue, conversation_messages)
    if selected_flat:
        return f"What is the total cost of the selected Flat {selected_flat}?"
    budget_follow_up_phrases = (
        "is it sufficient", "is this sufficient", "is that sufficient",
        "can i buy it", "can i afford it", "is it enough", "will it be enough",
    )
    has_explicit_budget = bool(_re.search(
        r"\b\d[\d,.]*\s*(?:lakh|lac|crore|rupees?|inr|rs\.?)\b",
        cleaned,
    ))
    if has_explicit_budget and any(phrase in cleaned for phrase in budget_follow_up_phrases):
        return normalize_text(issue)
    catalogue_phrases = (
        "your projects",
        "existing projects",
        "list projects",
        "show projects",
        "projects do you have",
        "tell me about the projects",
        "tell me about projects",
    )
    asks_to_fetch_catalogue = bool(_re.search(
        r"\b(?:fetch|get|give|load|list|show)\b.*\bprojects?\b",
        cleaned,
    ))
    asks_which_projects_exist = bool(_re.search(
        r"\bprojects?\s+(?:(?:do|does)\s+)?(?:you|u|acrobuild)\s+have\b",
        cleaned,
    ))
    if (
        any(phrase in cleaned for phrase in catalogue_phrases)
        or asks_to_fetch_catalogue
        or asks_which_projects_exist
    ):
        return normalize_text(issue)
    # The legacy resolver turns any "possession"/"status" follow-up into a
    # construction-status request; a documents or payments question is not one.
    if _re.search(r"\b(?:documents?|paperwork|papers|payments?|loan|registration|agreement)\b", cleaned):
        return normalize_text(issue)
    return _legacy_resolve_contextual_support_issue(issue, conversation_messages)


def validate_support_node(state):
    """Keep grounded calculations for a flat explicitly recovered from chat history."""
    issue = normalize_text((state or {}).get("issue", "")).lower()
    response = (state or {}).get("response", {}) or {}
    answer = normalize_text(response.get("answer", ""))
    bare_cost_reference = bool(_re.fullmatch(
        r"(?:so\s+)?how much(?:\s+(?:is|does|will|would))?\s+(?:this|that|it)(?:\s+cost)?\??",
        issue.strip(),
    ))
    contextual_flat_cost = (
        (bool(_re.search(r"\b(?:this|that|the|selected|above)\s+(?:flat|unit|home)\b", issue)) or bare_cost_reference)
        and any(phrase in issue for phrase in ("total cost", "total price", "cost of", "price of", "how much"))
        and bool(_re.match(r"^For Flat\s+[A-Za-z0-9-]+, the estimated base cost is INR ", answer))
        and "sq. ft." in answer
        and "per sq. ft." in answer
        and "base-price estimate" in answer
    )
    if contextual_flat_cost:
        return state
    return _legacy_validate_support_node(state)


# The imported implementation resolves these names from its own module globals.
# Install the compatibility overrides there before rebuilding its native
# pipeline adapter so direct calls and pipeline execution follow the same path.
def _facade_search_company_knowledge(*args, **kwargs):
    return search_company_knowledge(*args, **kwargs)


def _facade_get_live_project_names():
    return get_live_project_names()


_source.search_company_knowledge = _facade_search_company_knowledge
_source.get_live_project_names = _facade_get_live_project_names
_source.build_deterministic_conversation_answer = build_deterministic_conversation_answer
_source.is_small_talk_message = is_small_talk_message
_source.resolve_contextual_support_issue = resolve_contextual_support_issue
_source.validate_support_node = validate_support_node
_source.CONVERSATION_PIPELINE = _source.build_conversation_pipeline()

CONVERSATION_PIPELINE = _source.CONVERSATION_PIPELINE
run_conversation_pipeline = _source.run_conversation_pipeline
