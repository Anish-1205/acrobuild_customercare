"""Per-turn intent + reply-language analysis.

Keyword lists can't route or language-tag messages written in every Indian language
(often romanized), so one small LLM call decides both. Heuristics are only the
fallback when that call fails.
"""
import json
import re
from dataclasses import dataclass

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

_ANALYZER_SYSTEM_PROMPT = """You label one turn of Acrobuild's customer-support chat. Acrobuild (GBK Group) is a real-estate developer with residential projects in Thane and Pune.

Read the recent conversation and the customer's latest message. Output ONLY a JSON object, no other text:
{"intent": "property" or "general", "reply_language": "<language name>", "script": "latin" or "native", "english": "<English version of the latest message>"}

intent (judge what the LATEST message asks; earlier topics do not carry over to a new question)
- "property": the latest message is about Acrobuild/GBK: its projects, flats, homes, shops, prices or rates, availability, project locations, amenities, site visits, bookings, payments, documents, possession or handover, construction updates, maintenance, complaints, support tickets, or asking for a human agent. A short follow-up that continues a property discussion (a number, a project or wing name, "yes", "this one", "how much") is also "property".
- "general": anything else: greetings, small talk, questions about the assistant itself (its name, what it can do, which languages it speaks), requests to change the reply language, general knowledge, maths, coding, news, or advice not about Acrobuild properties, even if the conversation was about properties before.

reply_language (the language the assistant must reply in)
- Decide from the words of the LATEST message alone. The conversation's earlier language does not matter when the latest message has words of its own: a customer can switch language at any time.
- Customers often type Indian languages in English letters, e.g. Hindi "aapke paas kya hai", Telugu "meeku emi kavali", Tamil "nee enna panra" / "yenna pandre", Kannada "neevu hegiddira", Malayalam "ningalude peru enthanu", Marathi "tumhi kase aahat", Bengali "tumi kemon acho", Gujarati "tame kem cho", Punjabi "tusi kiddan ho". Name the actual language, never "English", for such messages. A message written in normal English sentences is "English".
- If the customer asks for a specific language ("telugu lo cheppu", "marathi madhe bol", "reply in tamil", "english please"), use the requested language.
- Only if the latest message has no language of its own ("ok", "3", a project name, an emoji) keep the language of the recent conversation.

script: "native" only if the customer writes that language in its own script (Devanagari, Telugu script, Tamil script, ...) or explicitly asks for that script; otherwise "latin".

english: the latest message translated into plain English, keeping project names, place names and numbers exactly. If it is already English, or is only a number, "yes"/"no", or a name, copy it unchanged."""


@dataclass(frozen=True)
class TurnAnalysis:
    intent: str
    reply_language: str
    script: str
    source: str
    english: str = ""

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


def _parse_analysis(raw):
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
    if intent not in {"property", "general"} or not language:
        return None
    return intent, language, script if script in {"latin", "native"} else "latin", english


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
        parsed = _parse_analysis(raw)
    except Exception as error:
        logger.warning("turn analysis failed %s", kv(error=error, issue=preview(issue, 80)))
        parsed = None
    if parsed is None:
        analysis = heuristic_turn_analysis(issue, conversation_messages, language_hint)
    else:
        intent, language, script, english = parsed
        if has_no_language_of_its_own(issue):
            language = _previous_language(conversation_messages) or language
        else:
            # Mixed messages ("possession ki documents em kavali") sometimes get
            # labelled English because of the English nouns; distinctive words win.
            language = strong_reply_language(issue) or (
                guess_romanized_language(issue) if language == ENGLISH else ""
            ) or language
        script = _resolve_script(issue, conversation_messages, language, script, language_hint)
        analysis = TurnAnalysis(intent=intent, reply_language=language, script=script, source="llm", english=english)
    logger.info(
        "turn analysis %s",
        kv(source=analysis.source, intent=analysis.intent, language=analysis.reply_language,
           script=analysis.script, issue=preview(issue, 80)),
    )
    return analysis
