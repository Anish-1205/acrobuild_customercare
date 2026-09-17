"""Compatibility loader for the recovered Haystack conversation runtime."""
from pathlib import Path as _Path
import marshal as _marshal
import re as _re

# The original module is bytecode-only. A hand-reconstruction —
# `haystack_conversation_pipeline_source.py`, verified against the bytecode by
# scripts/verify_pipeline_reconstruction.py — is exec'd in preference when
# present. It is exec'd (not imported) so the wrapper overrides below still apply
# to the pipeline it builds. See docs/RECONSTRUCTION_STATUS.md.
_runtime_path = _Path(__file__).with_name("haystack_conversation_pipeline_runtime.pyc")
_source_path = _Path(__file__).with_name("haystack_conversation_pipeline_source.py")
if _source_path.exists():
    _runtime_code = compile(_source_path.read_text(encoding="utf-8"), str(_source_path), "exec")
else:
    with _runtime_path.open("rb") as _runtime_file:
        from services.runtime_compatibility_service import validate_runtime_header
        validate_runtime_header(_runtime_file.read(16))
        _runtime_code = _marshal.load(_runtime_file)
exec(_runtime_code, globals(), globals())
build_deterministic_conversation_answer = globals()["build_deterministic_conversation_answer"]
is_small_talk_message = globals()["is_small_talk_message"]
normalize_text = globals()["normalize_text"]
resolve_contextual_support_issue = globals()["resolve_contextual_support_issue"]
validate_support_node = globals()["validate_support_node"]

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
            "live availability, API-listed pricing, and site visits. I can also guide you on "
            "documents, payments, construction updates, handover, maintenance, and support tickets."
        )
    return _legacy_build_deterministic_conversation_answer(issue)

def resolve_contextual_support_issue(issue, conversation_messages):
    cleaned = normalize_text(issue).lower()
    bare_cost_reference = bool(_re.fullmatch(
        r"(?:so\s+)?how much(?:\s+(?:is|does|will|would))?\s+(?:this|that|it)(?:\s+cost)?\??",
        cleaned.strip(),
    ))
    if bare_cost_reference:
        for message in reversed(conversation_messages or []):
            text = normalize_text(message.get("text", ""))
            flat_match = _re.search(r"\bflat\s*[:#-]?\s*(\d+[a-z0-9-]*)\b", text, flags=_re.IGNORECASE)
            if flat_match and "saleable area" in text.lower():
                return f"How much does the selected Flat {flat_match.group(1)} cost?"
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
