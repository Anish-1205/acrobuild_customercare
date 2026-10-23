"""Early handoff gate: runs before any answer is generated.

An explicit request for a person, an angry message, or a second frustrated message
in the same conversation goes to the team instead of getting another AI answer.
"""
import re

_HUMAN_RE = re.compile(
    r"\b(human|real person|talk to (?:an? )?(?:agent|person|someone|executive)|speak (?:to|with) (?:an? )?"
    r"(?:agent|person|someone|executive)|customer care executive)\b",
    re.IGNORECASE,
)

HANDOFF_ANSWER = (
    "I'm sorry about this. Let me get someone from our team to help you directly. "
    "Tap Need more help and share your contact details, and they'll pick it up from here."
)


def check(message, analysis, state):
    """Returns (handoff_reason or None, state). state carries the frustration count."""
    state = dict(state or {})
    sentiment = getattr(analysis, "sentiment", "calm")
    if _HUMAN_RE.search(str(message or "")):
        return "human_requested", state
    if sentiment == "angry":
        return "angry", state
    if sentiment == "frustrated":
        state["frustrated"] = state.get("frustrated", 0) + 1
        if state["frustrated"] >= 2:
            state["frustrated"] = 0
            return "frustrated", state
    return None, state
