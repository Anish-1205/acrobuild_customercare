"""Early handoff gate: runs before any answer is generated.

Only an explicit request for a person replaces the answer with a handoff. An angry or
frustrated customer still gets their answer, opened with an apology and with the team
offered alongside (acknowledge, help, offer escalation): withholding the answer from an
upset customer who asked a real question makes things worse.
"""
import os
import re

_HUMAN_RE = re.compile(
    r"\b(human|real person|talk to (?:an? )?(?:agent|person|someone|executive)|speak (?:to|with) (?:an? )?"
    r"(?:agent|person|someone|executive)|customer care executive)\b",
    re.IGNORECASE,
)

HANDOFF_ANSWER = (
    "I'm sorry about this. Let me get someone from our team to help you directly. "
    "Tap Need more help and share your contact details, and our team usually calls back within one "
    "working day."
)

EMPATHY_PREFIX = "I'm sorry for the trouble. Here's what I can tell you, and our team is a tap away if you'd prefer.\n\n"


def check(message, analysis, state):
    """Returns (handoff_reason or None, state)."""
    if _HUMAN_RE.search(str(message or "")):
        return "human_requested", dict(state or {})
    return None, dict(state or {})


def is_upset(analysis):
    return getattr(analysis, "sentiment", "calm") in {"angry", "frustrated"}


# Output filtering (OWASP LLM01/LLM02): whatever an injected prompt talks the model into, these never leave.
_SECRET_ENV = ("ACROBUILD_CS_API_KEY", "RUNPOD_API_KEY", "SARVAM_API_KEY", "AUTH_SECRET_KEY", "HF_TOKEN",
               "SMTP_APP_PASSWORD", "OTP_SECRET")
# Phrases only our own system prompts contain: an answer quoting them is leaking its instructions.
_PROMPT_LEAK_RE = re.compile(r"\[(?:Reply language|Meaning):|You are Acrobuild Support, the virtual assistant|"
                             r"Never mention these notes|CONCISE_REPLY_RULES", re.IGNORECASE)
LEAK_ANSWER = "I can help with Acrobuild projects, prices, site visits and support. What would you like to know?"


def scrub_output(answer):
    text = str(answer or "")
    if _PROMPT_LEAK_RE.search(text):
        return LEAK_ANSWER
    for name in _SECRET_ENV:
        secret = os.getenv(name, "")
        if len(secret) >= 8 and secret in text:
            text = text.replace(secret, "[removed]")
    return text
