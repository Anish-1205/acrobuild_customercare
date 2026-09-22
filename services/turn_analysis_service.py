"""Per-turn intent + reply-language analysis.

Keyword lists can't route or language-tag messages written in every Indian language
(often romanized), so one small LLM call decides both. Heuristics are only the
fallback when that call fails.
"""
import json
import re
from dataclasses import dataclass, replace
from services.freechat_policy import FREECHAT_TYPO_POLICY

from services.observability import get_logger, kv, preview
from services.reply_language import (
    ENGLISH,
    canonical_language,
    detect_script_language,
    guess_romanized_language,
    has_no_language_of_its_own,
    heuristic_reply_language,
    strong_reply_language,
)

logger = get_logger("turn_analysis")

_ANALYSIS_HISTORY_MESSAGES = 6

# Deterministic, not LLM-judged: an explicit callback ask is a distinct intent
# from a general "connect me to an agent" (property) or "how do I reach you"
# (contact-info) request, and it drives a real booking action, so it should not
# depend on the analyzer model's fuzzy judgement. Deliberately narrow — matches
# explicit booking phrasing only, not every message containing the word "call".
#
# Covers English word order ("arrange a call") plus romanized Hindi/Marathi
# word order, where the verb follows the object ("call arrange karo", "call
# back kara", "mujhe callback chahiye"/"mala callback pahije"). Native
# Devanagari script is out of scope by design (Latin/romanized script only).
_CALL_WORD = r"call\s*[- ]?back|call"
_EN_BOOKING_VERB = r"arrange|schedule|book|request|set\s*up|organi[sz]e"
# Hindi/Marathi imperative "do (it)" — karo/kar do/kariye/kijiye (Hindi),
# kara/karaa (Marathi).
_HI_MR_DO_VERB = r"kar(?:o|ein|en|iye|ijiye)|kar\s*do|kara|karaa"
# Hindi "chahiye" / Marathi "pahije" = "(I) want/need".
_HI_MR_WANT = r"chahiye|pahije"

_CALL_BOOKING_RE = re.compile(
    rf"\b(?:{_EN_BOOKING_VERB})\s+(?:a|an)\s+(?:{_CALL_WORD})\b"          # "arrange a call/callback"
    rf"|\b(?:{_CALL_WORD})\s+(?:{_EN_BOOKING_VERB})\b"                    # "call/callback arrange" (HI/MR order)
    rf"|\b(?:{_CALL_WORD})\s+(?:{_HI_MR_DO_VERB})\b"                      # "call karo" / "callback kara"
    rf"|\b(?:{_CALL_WORD})\s+(?:{_HI_MR_WANT})\b"                         # "call chahiye" / "callback pahije"
    rf"|\bwapas\s+(?:{_CALL_WORD})\b|\bparat\s+(?:{_CALL_WORD})\b"        # "wapas call" (HI) / "parat call" (MR)
    r"|\bcall\s+me\s+back\b",
    re.IGNORECASE,
)

def _is_call_booking_phrase(text):
    return bool(_CALL_BOOKING_RE.search(str(text or "")))


# Deterministic, same reasoning as call_booking above: "I want a human to
# reach out to me" is a distinct, actionable intent from the generic
# support-contact detector (which just explains how to reach support) and
# from call_booking (which is specifically about scheduling a callback at a
# time). Two-part check, both required, so common unrelated words like
# "talk"/"team"/"connect" alone never misfire:
#   1. a contact-role noun (representative/agent/team/... or the Hindi/
#      Marathi native equivalents, which glue postpositions directly onto
#      the word, hence the loose trailing match on those only), and
#   2. a talk/speak/connect verb, English or romanized Hindi/Marathi/Telugu.
# A separate "someone" fallback covers "talk to someone at your company"
# style phrasing that names no specific role.
_HUMAN_CONTACT_ROLE_NOUN_RE = re.compile(
    r"\b(?:representative|agent|executive|human|person|staff|team)\b"
    r"|\bpratinidhi\w*\b"   # Hindi/Marathi: representative
    r"|\binsaan\w*\b"       # Hindi: human/person
    r"|\bvyakti\w*\b",      # Hindi/Marathi: person
    re.IGNORECASE,
)
_HUMAN_CONTACT_VERB_RE = re.compile(
    r"\b(?:talk|speak|connect|put\s+me\s+through)\b"  # English
    r"|\bbaat\b|\bmiln[aei]\b"                         # Hindi (baat karni/karo, milna)
    r"|\bbol\w*\b"                                     # Marathi (bolaycha, boloo, bolel)
    r"|\bmatlad\w*\b",                                 # Telugu (matladali, matladoccha)
    re.IGNORECASE,
)
_HUMAN_CONTACT_SOMEONE_RE = re.compile(
    r"\bsomeone\b.*\b(?:your|company|acrobuild|gbk)\b"
    r"|\b(?:your|company|acrobuild|gbk)\b.*\bsomeone\b",
    re.IGNORECASE,
)


def _is_human_contact_phrase(text):
    text = str(text or "")
    if _HUMAN_CONTACT_ROLE_NOUN_RE.search(text) and _HUMAN_CONTACT_VERB_RE.search(text):
        return True
    return bool(_HUMAN_CONTACT_SOMEONE_RE.search(text))


def is_human_contact_continuation(conversation_messages):
    """Same mechanism as is_call_booking_continuation() below, for the
    "still need name/phone" human_contact clarification."""
    from services.conversation_store_service import has_pending_human_contact_marker

    messages = list(conversation_messages or [])
    if not messages:
        return False
    last = messages[-1]
    return (
        str(last.get("sender", "")).lower() == "bot"
        and has_pending_human_contact_marker(last.get("text", ""))
    )


def is_call_booking_continuation(conversation_messages):
    """True when the bot's last message was the "still need phone/time"
    call-booking clarification — checked via an invisible, language-independent
    marker (conversation_store_service.PENDING_CALL_BOOKING_MARKER) appended to
    the *stored* copy of that answer, never via the localized visible text:
    that text is in the customer's own language and a fixed English/Hindi/
    Marathi substring would never reliably match it turn to turn."""
    from services.conversation_store_service import has_pending_call_booking_marker

    messages = list(conversation_messages or [])
    if not messages:
        return False
    last = messages[-1]
    return (
        str(last.get("sender", "")).lower() == "bot"
        and has_pending_call_booking_marker(last.get("text", ""))
    )

_ANALYZER_SYSTEM_PROMPT = """You label one turn of Acrobuild's customer-support chat. Acrobuild (GBK Group) is a real-estate developer with residential projects in Thane and Pune.

Read the recent conversation and the customer's latest message. Output ONLY a JSON object, no other text:
{"intent": "property" or "general", "reply_language": "<language name>", "script": "latin" or "native", "english": "<English version of the latest message>", "unsure": true or false}

intent (judge what the LATEST message asks; earlier topics do not carry over to a new question)
- "property": the latest message is about Acrobuild/GBK: its projects, flats, homes, shops, prices or rates, availability, project locations, amenities, site visits, bookings, payments, documents, possession or handover, construction updates, maintenance, complaints, support tickets, or asking for a human agent. Asking what is available or what there is in a named area or locality ("what is there in Kompally?") is also "property". A short follow-up that continues a property discussion (a number, a project or wing name, "yes", "this one", "how much") is also "property".
- "general": anything else: greetings, small talk, questions about the assistant itself (its name, what it can do, which languages it speaks), requests to change the reply language, general knowledge, maths, coding, news, or advice not about Acrobuild properties, even if the conversation was about properties before.

unsure (does the customer sound unclear about what kind of help they actually want, rather than asking something specific)
- true only if the latest message is genuinely vague about what help is needed ("I need help", "not sure what to do", "can someone assist me", "I don't know what's wrong") or asks generically to be connected to a person/ticket/call with no topic and no actionable detail.
- false if the message asks a specific, answerable question, or gives enough detail to act on directly (a property question, a site-visit request with a project/date, a specific complaint, greetings, small talk, etc.) even if it separately mentions wanting a ticket or an agent.
- Judge only the latest message; do not mark unsure just because an earlier turn was unclear.

reply_language (the language the assistant must reply in)
- Decide from the words of the LATEST message alone. The conversation's earlier language does not matter when the latest message has words of its own: a customer can switch language at any time.
- Customers often type Indian languages in English letters, e.g. Hindi "aapke paas kya hai", Telugu "meeku emi kavali", Tamil "nee enna panra" / "yenna pandre", Kannada "neevu hegiddira", Malayalam "ningalude peru enthanu", Marathi "tumhi kase aahat", Bengali "tumi kemon acho", Gujarati "tame kem cho", Punjabi "tusi kiddan ho". Name the actual language, never "English", for such messages. A message written in normal English sentences is "English".
- If the customer asks for a specific language ("telugu lo cheppu", "marathi madhe bol", "reply in tamil", "english please"), use the requested language.
- Only if the latest message has no language of its own ("ok", "3", a project name, an emoji) keep the language of the recent conversation.

script: "native" only if the customer writes that language in its own script (Devanagari, Telugu script, Tamil script, ...) or explicitly asks for that script; otherwise "latin".

english: the latest message translated into plain English, keeping project names, place names and numbers exactly. If it is already English, or is only a number, "yes"/"no", or a name, copy it unchanged."""


_ANALYZER_SYSTEM_PROMPT += (
    "\n\n" + FREECHAT_TYPO_POLICY
    + "During labeling, preserve unresolved ambiguity in the English version; do not invent "
    "a referent or resolve an uncertain word. The answer-writing assistant will ask the clarification. "
    "This tolerance policy applies only to general messages, not property entity matching."
)


@dataclass(frozen=True)
class TurnAnalysis:
    intent: str
    reply_language: str
    script: str
    source: str
    english: str = ""
    unsure: bool = False

    @property
    def is_property(self):
        return self.intent == "property"


def _history_text(conversation_messages):
    lines = []
    for message in list(conversation_messages or [])[-_ANALYSIS_HISTORY_MESSAGES:]:
        text = " ".join(str(message.get("text", "")).split())
        if not text:
            continue
        speaker = "Assistant" if str(message.get("sender", "")).lower() == "bot" else "Customer"
        lines.append(f"{speaker}: {text[:300]}")
    return "\n".join(lines)


def _previous_language(conversation_messages):
    for message in reversed(list(conversation_messages or [])):
        if str(message.get("sender", "")).lower() == "bot":
            continue
        language, _ = heuristic_reply_language(message.get("text", ""))
        if language:
            return language
    return ""


def _resolve_script(issue, conversation_messages, language, llm_script, language_hint):
    """The characters typed are more reliable than the model's script label."""
    if language == ENGLISH:
        return "latin"
    if detect_script_language(issue):
        return "native"
    if canonical_language(language_hint) not in {"", ENGLISH}:
        return "native"
    if re.search(r"[A-Za-z]{2,}", str(issue or "")):
        return llm_script if "script" in str(issue).lower() else "latin"
    for message in reversed(list(conversation_messages or [])):
        if str(message.get("sender", "")).lower() != "bot" and str(message.get("text", "")).strip():
            return "native" if detect_script_language(message.get("text", "")) else "latin"
    return "latin"


def _parse_analysis(raw, issue=""):
    match = re.search(r"\{.*\}", str(raw or ""), flags=re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except (TypeError, ValueError):
        return None
    intent = str(data.get("intent", "")).strip().lower()
    language = canonical_language(data.get("reply_language"))
    script = str(data.get("script", "")).strip().lower()
    english = " ".join(str(data.get("english") or "").split())
    unsure = bool(data.get("unsure", False))
    # The analyzer model itself only ever claims "property" or "general" (its
    # prompt does not mention call_booking/human_contact); the deterministic
    # phrase checks below are what actually promote a turn to one of those.
    if intent not in {"property", "general"} or not language:
        return None
    if _is_call_booking_phrase(issue):
        intent = "call_booking"
    elif _is_human_contact_phrase(issue):
        intent = "human_contact"
    return intent, language, script if script in {"latin", "native"} else "latin", english, unsure


def heuristic_turn_analysis(issue, conversation_messages=None, language_hint=""):
    from graph.haystack_conversation_pipeline import is_property_support_message, matches_live_company_context

    hint = canonical_language(language_hint)
    language, script = heuristic_reply_language(issue, _previous_language(conversation_messages))
    if hint and hint != ENGLISH and language in {"", ENGLISH}:
        language, script = hint, "native"
    is_property = is_property_support_message(issue) or matches_live_company_context(issue)
    return TurnAnalysis(
        intent="property" if is_property else "general",
        reply_language=language,
        script=script or "latin",
        source="heuristic",
    )


def analyze_turn(issue, conversation_messages=None, language_hint=""):
    from qwen import generate_qwen_chat_response

    parts = []
    history = _history_text(conversation_messages)
    if history:
        parts.append(f"Recent conversation:\n{history}")
    hint = canonical_language(language_hint)
    if hint and hint != ENGLISH:
        parts.append(f"The customer is using voice input with {hint} selected; prefer native script.")
    parts.append(f"Latest customer message:\n{issue}")
    try:
        raw = generate_qwen_chat_response(
            system_prompt=_ANALYZER_SYSTEM_PROMPT,
            user_prompt="\n\n".join(parts),
            conversation_messages=[],
            temperature=0,
        )
        parsed = _parse_analysis(raw, issue)
    except Exception as error:
        logger.warning("turn analysis failed %s", kv(error=error, issue=preview(issue, 80)))
        parsed = None
    if parsed is None:
        analysis = heuristic_turn_analysis(issue, conversation_messages, language_hint)
    else:
        intent, language, script, english, unsure = parsed
        if has_no_language_of_its_own(issue):
            language = _previous_language(conversation_messages) or language
        else:
            # Mixed messages ("possession ki documents em kavali") sometimes get
            # labelled English because of the English nouns; distinctive words win.
            language = strong_reply_language(issue) or (
                guess_romanized_language(issue) if language == ENGLISH else ""
            ) or language
        script = _resolve_script(issue, conversation_messages, language, script, language_hint)
        analysis = TurnAnalysis(intent=intent, reply_language=language, script=script, source="llm", english=english, unsure=unsure)
    # Covers the heuristic-fallback path (never ran _parse_analysis) and
    # continuation turns (e.g. a bare phone number replying to the bot's own
    # "what's a good time to call you back?" has no booking phrase of its own).
    if analysis.intent != "call_booking" and (
        _is_call_booking_phrase(issue) or is_call_booking_continuation(conversation_messages)
    ):
        analysis = replace(analysis, intent="call_booking")
    # Same pattern for human_contact; checked after call_booking so an
    # explicit scheduling ask (e.g. "arrange a call with a representative")
    # keeps going to the more specific call_booking flow.
    if analysis.intent not in {"call_booking", "human_contact"} and (
        _is_human_contact_phrase(issue) or is_human_contact_continuation(conversation_messages)
    ):
        analysis = replace(analysis, intent="human_contact")
    logger.info(
        "turn analysis %s",
        kv(source=analysis.source, intent=analysis.intent, language=analysis.reply_language,
           script=analysis.script, issue=preview(issue, 80)),
    )
    return analysis
