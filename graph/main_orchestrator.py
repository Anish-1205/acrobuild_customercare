from graph.haystack_conversation_pipeline import (
    build_social_conversation_answer,
    get_live_project_names,
    resolve_contextual_support_issue,
    run_conversation_pipeline,
    validate_support_node,
)
import os
from threading import Lock
from time import monotonic
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re
from dataclasses import dataclass, replace
from qwen import (
    generate_qwen_chat_response,
    stream_qwen_chat_response,
    get_llm_agent_mode,
    get_llm_source_label,
    get_qwen_model_name,
)
from services.observability import get_logger, kv, normalize_agent_mode, preview
from services.reply_language import (
    ENGLISH,
    build_reply_language_directive,
    detect_script_language,
    guess_romanized_language,
    heuristic_reply_language,
)
from services.turn_analysis_service import TurnAnalysis, analyze_turn

logger = get_logger("orchestrator")

_CONVERSATION_MEMORY = {}
_MEMORY_LOCK = Lock()
_MEMORY_TTL_SECONDS = 7200
_MEMORY_MAX_MESSAGES = 60
_DEFAULT_LLM_HISTORY_TURNS = 10


def _generation_issue(issue, analysis):
    """Issue text for the answer-writing model with the analyzed reply language
    appended. Routing and retrieval keep the clean issue."""
    return f"{issue}{build_reply_language_directive(analysis.reply_language, analysis.script)}"


def _general_generation_issue(issue, analysis):
    """General chat also gets the English meaning: the model sometimes misreads
    romanized Indian languages (e.g. Tamil "yenna pandre" read as a question about age)."""
    meaning = analysis.english.strip()
    if meaning and analysis.reply_language != ENGLISH and meaning.lower() != str(issue or "").strip().lower():
        return f"{issue}\n\n[Meaning: {meaning}]{build_reply_language_directive(analysis.reply_language, analysis.script)}"
    return _generation_issue(issue, analysis)


def _recent_history(conversation_messages):
    """Cap the conversation handed to an LLM (latency + hallucination surface). The
    explicit per-turn reply-language directive, not history filtering, keeps the
    model from mirroring a stale language."""
    try:
        turns = max(int(os.getenv("LLM_HISTORY_TURNS", _DEFAULT_LLM_HISTORY_TURNS)), 1)
    except (TypeError, ValueError):
        turns = _DEFAULT_LLM_HISTORY_TURNS
    return list(conversation_messages or [])[-(turns * 2):]


def _prior_messages(conversation_messages, issue):
    messages = list(conversation_messages or [])
    if messages and str(messages[-1].get("sender", "")).lower() != "bot" and \
            str(messages[-1].get("text", "")).strip() == str(issue or "").strip():
        return messages[:-1]
    return messages


_HARD_PROPERTY_SIGNAL_RE = re.compile(
    r"\b[1-6]\s*bhk\b|\b\d{3,5}\s*sq|\brera\b|\bsite\s+visits?\b|\bacrobuild\b", re.IGNORECASE,
)


def _has_hard_property_signal(issue, resolved_issue):
    if resolved_issue != issue or _HARD_PROPERTY_SIGNAL_RE.search(resolved_issue or ""):
        return True
    cleaned = str(resolved_issue or "").lower()
    return any(name and name.lower() in cleaned for name in get_live_project_names())


@dataclass(frozen=True)
class TurnContext:
    conversation_messages: list
    resolved_issue: str
    analysis: TurnAnalysis
    property_issue: str


def prepare_turn(issue, conversation_id="", conversation_messages=None, language_hint=""):
    """Analyze the customer's own words once, then run the English-only contextual
    resolver on the English rendering (it misreads romanized Indian languages). The
    router's grounded shortcuts and the orchestrator share this one LLM analysis."""
    merged = _merge_conversation(conversation_id, conversation_messages, issue)
    analysis = analyze_turn(issue, _prior_messages(merged, issue), language_hint)
    english_issue = issue
    if analysis.english and analysis.reply_language != ENGLISH:
        english_issue = analysis.english
    resolved_issue = resolve_contextual_support_issue(english_issue, merged)
    if resolved_issue != english_issue:
        logger.info("issue resolved from context %s", kv(raw=preview(issue, 120), resolved=preview(resolved_issue, 120)))
    if analysis.intent != "property" and _has_hard_property_signal(english_issue, resolved_issue):
        analysis = replace(analysis, intent="property")
    return TurnContext(merged, resolved_issue, analysis, resolved_issue)


def _language_fields(analysis):
    return {
        "route": "property" if analysis.is_property else "general",
        "reply_language": analysis.reply_language or "",
        "reply_script": analysis.script or "latin",
    }


def _log_retrieval(issue, response, is_property=False):
    """The retrieval engine lives in a compiled blob; log what it returned so an
    empty result is diagnosable (query, mode, matched chunk ids + scores)."""
    response = response or {}
    chunks = response.get("matched_chunks") or []
    retrieval_mode = response.get("retrieval_mode")
    logger.debug(
        "retrieval result %s",
        kv(mode=retrieval_mode, matched=len(chunks), query=preview(issue, 120)),
    )
    for chunk in chunks[:8]:
        logger.debug(
            "retrieval chunk %s",
            kv(source=chunk.get("source_key") or chunk.get("document_id") or chunk.get("article_id"),
               kind=chunk.get("record_kind"), score=chunk.get("score"),
               title=preview(chunk.get("title") or chunk.get("project_name"), 60)),
        )
    if is_property and not chunks:
        logger.warning(
            "property turn retrieved no evidence %s",
            kv(mode=retrieval_mode, query=preview(issue, 120)),
        )


def _current_local_time():
    try:
        return datetime.now(ZoneInfo("Asia/Kolkata"))
    except ZoneInfoNotFoundError:
        return datetime.now().astimezone()


def _ground_current_date_time_answer(issue, current_time):
    cleaned_issue = " ".join(str(issue or "").lower().split())
    asks_day = bool(re.search(r"\b(what|which) day\b|\bday is it\b", cleaned_issue))
    asks_date = bool(re.search(r"\b(what|today'?s|current) date\b|\bdate is it\b", cleaned_issue))
    asks_time = bool(re.search(r"\b(what|current|local) time\b|\btime is it\b", cleaned_issue))

    if not any((asks_day, asks_date, asks_time)):
        return ""
    if asks_time and not (asks_day or asks_date):
        return current_time.strftime("The current local time is %I:%M %p %Z.")
    if asks_time:
        return current_time.strftime("It is %A, %d %B %Y, %I:%M %p %Z.")
    return current_time.strftime("Today is %A, %d %B %Y.")


def _focus_simple_factual_answer(issue, answer):
    cleaned_issue = " ".join(str(issue or "").lower().split())
    is_short_fact = bool(re.match(
        r"^(?:who (?:is|was|are|were)|where (?:is|was|are|were)|when (?:is|was|did)|"
        r"what is the capital of)\b",
        cleaned_issue,
    ))
    if not is_short_fact or "tell me about" in cleaned_issue:
        return answer
    first_sentence = re.match(r"^(.+?[.!?])(?:\s|$)", str(answer or "").strip())
    return first_sentence.group(1).strip() if first_sentence else answer


def _ground_current_officeholder_answer(issue):
    cleaned_issue = re.sub(r"[^a-z0-9 ]+", " ", str(issue or "").lower())
    cleaned_issue = " ".join(cleaned_issue.split())
    asks_andhra_cm = (
        bool(re.search(r"\b(?:who is|who s|name)\b", cleaned_issue))
        and bool(re.search(r"\b(?:cm|chief minister)\b", cleaned_issue))
        and bool(re.search(r"\b(?:andhra pradesh|ap)\b", cleaned_issue))
    )
    if asks_andhra_cm:
        return "The current Chief Minister of Andhra Pradesh is N. Chandrababu Naidu."
    return ""


def _merge_conversation(conversation_id, incoming, issue):
    messages = []
    for message in incoming or []:
        clean = {"sender": str(message.get("sender", "customer")), "text": str(message.get("text", "")).strip()}
        if clean["text"] and (not messages or messages[-1] != clean):
            messages.append(clean)
    turn = {"sender": "customer", "text": str(issue or "").strip()}
    if turn["text"] and (not messages or messages[-1] != turn):
        messages.append(turn)
    return messages[-_MEMORY_MAX_MESSAGES:]


def _remember_response(conversation_id, messages, response):
    # Live-only mode never persists server-side conversation or answer memory.
    return
from services.ai_agent_service import (
    _build_contextual_flat_cost_answer,
    _build_contextual_same_price_floor_answer,
    build_ai_support_answer,
    stream_ai_support_answer_events,
)


CONCISE_REPLY_RULES = (
    "Be concise and plain: answer in 1 to 3 short sentences. No lists, headings, markdown, or emojis unless "
    "the user asks for detail. No filler, flattery, exclamations, restating the question, or offers of further help. "
)



LANGUAGE_CAPABILITY = (
    "You can converse fluently in English and in every major Indian language, including Hindi, Bengali, "
    "Telugu, Marathi, Tamil, Urdu, Gujarati, Kannada, Odia, Malayalam, Punjabi and Assamese, whether the "
    "customer types in the language's own script or in English letters. If asked which languages you speak, "
    "say so. Switch language whenever the customer asks, and never claim you cannot understand or use a "
    "language. "
)


def _general_chat_system_prompt(runtime_context):
    """Shared system prompt for free chat (non-property turns), used by both the
    non-streaming and streaming paths so they can't drift apart.

    Do not reintroduce "if you are not confident, say you are unsure": verified
    against the model, that clause made it refuse facts it knows correctly."""
    return (
        "You are Acrobuild Support, the virtual assistant of Acrobuild (GBK Group), a real-estate developer. "
        "Talk like a friendly, professional modern AI assistant. Answer the customer's question directly, "
        "naturally, and accurately using your model knowledge: general knowledge, small talk, and questions "
        "about yourself are all fine (you are an AI assistant, so answer things like your name or what you are "
        "doing naturally and briefly). "
        "Do not invent a name, date, place, or number you are not actually confident about. "
        "For roles or facts that can change over time (e.g. a current officeholder), give your best-known "
        "answer and briefly note it may have changed since your training data, rather than refusing to answer. "
        "Do not invent current Acrobuild property, pricing, availability, company, or customer facts; offer to "
        "look them up instead. Only offer help Acrobuild actually provides: project and flat information, pricing, "
        "availability, site visits, support tickets and connecting to the Acrobuild team. Never mention internal "
        "systems, APIs, data sources, or evidence. For other "
        "genuinely live external information, clearly state the limitation and still provide any useful "
        "non-live answer you can. Keep the answer focused on exactly what was asked. "
        + CONCISE_REPLY_RULES
        + LANGUAGE_CAPABILITY
        + "The customer's message ends with notes in square brackets: [Reply language: ...] says which "
        "language and script to write your whole reply in, and an optional [Meaning: ...] gives the message in "
        "English to help you understand it. Never mention these notes. "
        "Reference, only for questions about today's date, day or time (never mention it otherwise): the "
        f"current local date and time is {runtime_context}. Use this value directly for such questions instead "
        "of claiming that you cannot access it."
    )


def _heuristic_analysis(issue, conversation_messages):
    language, script = heuristic_reply_language(issue)
    return TurnAnalysis("general", language, script or "latin", "heuristic")


def _grounded_general_answer(issue, analysis, current_time):
    """Fixed English shortcuts only make sense when the reply is in English."""
    if analysis.reply_language != ENGLISH:
        return ""
    return (
        build_social_conversation_answer(issue)
        or _ground_current_date_time_answer(issue, current_time)
        or _ground_current_officeholder_answer(issue)
    )


def _needs_localization(answer, analysis):
    if not answer or analysis.reply_language in {"", ENGLISH}:
        return False
    if analysis.script == "native":
        return not detect_script_language(answer)
    return not detect_script_language(answer) and not guess_romanized_language(answer)


_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _localize_answer(answer, analysis):
    """Deterministic property answers are English templates; rewrite them into the
    customer's language, keeping every fact. Falls back to the original on any doubt."""
    if not _needs_localization(answer, analysis):
        return answer
    target = (
        f"{analysis.reply_language}, written in {analysis.reply_language} script"
        if analysis.script == "native"
        else f"{analysis.reply_language}, written in English letters (romanized {analysis.reply_language}) the way "
             "an Indian support agent types in chat"
    )
    # The instruction must sit in the user turn: with it only in the system prompt,
    # Sarvam echoes the English text back unchanged.
    source_numbers = {number.replace(",", "") for number in _NUMBER_RE.findall(answer)}
    for attempt in (1, 2):
        try:
            localized = str(generate_qwen_chat_response(
                system_prompt="You are a professional translator for an Indian real-estate company's chat support.",
                user_prompt=(
                    f"Translate the English support message below into {target}. Keep project names, place names, "
                    "numbers, prices, INR amounts, RERA numbers, dates, URLs, email addresses and real-estate terms "
                    "(BHK, wing, floor, site visit, carpet area, sq. ft.) exactly as they are. Keep the same line "
                    "breaks and bullets. Do not add or remove information. Output only the translation.\n\n"
                    f"ENGLISH MESSAGE:\n{answer}"
                ),
                conversation_messages=[],
                temperature=0 if attempt == 1 else 0.3,
            ) or "").strip()
        except Exception as error:
            logger.warning("answer localization failed %s", kv(error=error, language=analysis.reply_language))
            return answer
        localized_numbers = {number.replace(",", "") for number in _NUMBER_RE.findall(localized)}
        if localized and localized != answer and source_numbers <= localized_numbers:
            return localized
        logger.warning(
            "answer localization rejected %s",
            kv(language=analysis.reply_language, attempt=attempt, echoed=localized == answer,
               missing_numbers=sorted(source_numbers - localized_numbers)),
        )
    return answer


def localize_response(response, analysis):
    """Last step for every payload (including router shortcuts and the live-data
    fallback text), so no English template reaches a non-English conversation."""
    response = dict(response or {})
    response["answer"] = _localize_answer(response.get("answer", ""), analysis)
    response.update({key: value for key, value in _language_fields(analysis).items() if key != "route"})
    response.setdefault("route", _language_fields(analysis)["route"])
    return response


def _general_llm_failure_response(error, analysis):
    source_label = get_llm_source_label()
    return {
        "agent_mode": get_llm_agent_mode(success=False),
        "answer": f"The live LLM ({source_label}) is unavailable: {error}",
        "articles": [],
        "assist_error": str(error),
        "confidence_label": "low",
        "handoff_recommended": True,
        "knowledge_documents": [],
        "matched_chunks": [],
        "model": get_qwen_model_name(),
        "retrieval_mode": "none",
        "source_label": source_label,
        "source_status": "failed",
        "used_llm": False,
        **_language_fields(analysis),
    }


def _build_live_general_llm_response(issue, conversation_messages, analysis=None):
    analysis = analysis or _heuristic_analysis(issue, conversation_messages)
    current_time = _current_local_time()
    runtime_context = current_time.strftime(
        "%A, %d %B %Y at %I:%M %p %Z"
    )
    try:
        answer = generate_qwen_chat_response(
            system_prompt=_general_chat_system_prompt(runtime_context),
            user_prompt=_general_generation_issue(issue, analysis),
            conversation_messages=_recent_history(_prior_messages(conversation_messages, issue)),
            temperature=0,
        )
        grounded_answer = _grounded_general_answer(issue, analysis, current_time)
        if grounded_answer:
            answer = grounded_answer
        elif analysis.reply_language == ENGLISH:
            answer = _focus_simple_factual_answer(issue, answer)
        return {
            "agent_mode": get_llm_agent_mode(success=True),
            "answer": answer,
            "articles": [],
            "assist_error": "",
            "confidence_label": "medium",
            "handoff_recommended": False,
            "knowledge_documents": [],
            "matched_chunks": [],
            "model": get_qwen_model_name(),
            "retrieval_mode": "none",
            "source_label": get_llm_source_label(),
            "source_status": "live",
            "used_llm": True,
            **_language_fields(analysis),
        }
    except Exception as error:
        return _general_llm_failure_response(error, analysis)


def _finalize_property_response(response, resolved_issue, conversation_messages, analysis):
    response = dict(response or {})
    cleaned_issue = str(resolved_issue or "").lower()
    contextual_answer = (
        _build_contextual_same_price_floor_answer(cleaned_issue, response.get("matched_chunks", []), conversation_messages)
        or _build_contextual_flat_cost_answer(cleaned_issue, conversation_messages)
    )
    if contextual_answer:
        response.update({
            "answer": contextual_answer,
            "confidence_label": "high",
            "handoff_recommended": False,
            "used_llm": False,
        })
    response = dict(validate_support_node({"issue": resolved_issue, "response": response})["response"])
    response["agent_mode"] = normalize_agent_mode(response.get("agent_mode"))
    response["answer"] = _localize_answer(response.get("answer", ""), analysis)
    response.update(_language_fields(analysis))
    _log_retrieval(resolved_issue, response, is_property=True)
    return response


# -----------------------------------
# MAIN SUPPORT ORCHESTRATION
# -----------------------------------


def run_support_orchestration(
    issue,
    conversation_id="",
    customer_name="",
    customer_email="",
    business_hours_tag="",
    issue_type="",
    article_hint_url="",
    conversation_messages=None,
    limit=3,
    prefer_fast_response=False,
    prefer_qwen_response=True,
    language_hint="",
    turn=None,
):
    turn = turn or prepare_turn(issue, conversation_id, conversation_messages, language_hint)
    conversation_messages = turn.conversation_messages
    resolved_issue = turn.resolved_issue
    analysis = turn.analysis
    property_issue = turn.property_issue

    def existing_support_handler():
        return build_ai_support_answer(
            issue=_generation_issue(property_issue, analysis),
            customer_name=customer_name,
            customer_email=customer_email,
            business_hours_tag=business_hours_tag,
            issue_type=issue_type,
            article_hint_url=article_hint_url,
            conversation_messages=_recent_history(conversation_messages),
            limit=limit,
            prefer_fast_response=prefer_fast_response,
            prefer_qwen_response=prefer_qwen_response,
        )

    if prefer_qwen_response and not analysis.is_property:
        logger.info("orchestration branch %s", kv(mode="general_llm", language=analysis.reply_language))
        response = _build_live_general_llm_response(issue, conversation_messages, analysis)
    elif prefer_qwen_response:
        logger.info("orchestration branch %s", kv(mode="property", language=analysis.reply_language))
        response = _finalize_property_response(
            existing_support_handler(), property_issue, conversation_messages, analysis,
        )
    else:
        logger.info("orchestration branch %s", kv(mode="rag_pipeline", language=analysis.reply_language))
        response = run_conversation_pipeline(
            issue=resolved_issue,
            conversation_messages=conversation_messages,
            support_handler=existing_support_handler,
        )
        _log_retrieval(resolved_issue, response, is_property=analysis.is_property)
        if isinstance(response, dict):
            response.update(_language_fields(analysis))
    if isinstance(response, dict):
        response["agent_mode"] = normalize_agent_mode(response.get("agent_mode"))
    logger.info(
        "orchestration result %s",
        kv(source_status=response.get("source_status"), retrieval_mode=response.get("retrieval_mode"),
           used_llm=response.get("used_llm"), confidence=response.get("confidence_label"),
           agent_mode=response.get("agent_mode"), answer=preview(response.get("answer"))),
    )
    _remember_response(conversation_id, conversation_messages, response)
    return response


def stream_support_orchestration_events(
    issue,
    conversation_id="",
    customer_name="",
    customer_email="",
    business_hours_tag="",
    issue_type="",
    article_hint_url="",
    conversation_messages=None,
    limit=3,
    prefer_fast_response=False,
    prefer_qwen_response=True,
    language_hint="",
    turn=None,
):
    turn = turn or prepare_turn(issue, conversation_id, conversation_messages, language_hint)
    conversation_messages = turn.conversation_messages
    resolved_issue = turn.resolved_issue
    analysis = turn.analysis
    property_issue = turn.property_issue
    yield {"type": "route", **_language_fields(analysis)}

    if prefer_qwen_response and not analysis.is_property:
        logger.info("orchestration branch %s", kv(mode="general_llm_stream", language=analysis.reply_language))
        yield {"type": "progress", "stage": "generating"}
        current_time = _current_local_time()
        grounded = _grounded_general_answer(issue, analysis, current_time)
        if grounded:
            logger.info("grounded shortcut answer used %s", kv(answer=preview(grounded, 120)))
            yield {"type": "delta", "text": grounded}
            response = {"answer": grounded, "agent_mode": normalize_agent_mode(get_llm_agent_mode()),
                        "used_llm": False, "source_label": get_llm_source_label(),
                        "model": get_qwen_model_name(), "source_status": "live", "retrieval_mode": "none",
                        "confidence_label": "medium", "handoff_recommended": False,
                        "articles": [], "knowledge_documents": [], "matched_chunks": [], "assist_error": "",
                        **_language_fields(analysis)}
            yield {"response": response, "type": "done"}
            return
        pieces = []
        try:
            runtime_context = current_time.strftime("%A, %d %B %Y at %I:%M %p %Z")
            for piece in stream_qwen_chat_response(
                system_prompt=_general_chat_system_prompt(runtime_context),
                user_prompt=_general_generation_issue(issue, analysis),
                conversation_messages=_recent_history(_prior_messages(conversation_messages, issue)),
                temperature=0,
            ):
                pieces.append(piece)
                yield {"type": "delta", "text": piece}
        except Exception as error:
            response = _general_llm_failure_response(error, analysis)
            response["agent_mode"] = normalize_agent_mode(response["agent_mode"])
            yield {"type": "delta", "text": response["answer"]}
            yield {"response": response, "type": "done"}
            return
        response = {"answer": "".join(pieces), "agent_mode": normalize_agent_mode(get_llm_agent_mode()),
                    "used_llm": True, "source_label": get_llm_source_label(),
                    "model": get_qwen_model_name(), "source_status": "live", "retrieval_mode": "none",
                    "confidence_label": "medium", "handoff_recommended": False,
                    "articles": [], "knowledge_documents": [], "matched_chunks": [], "assist_error": "",
                    **_language_fields(analysis)}
        _remember_response(conversation_id, conversation_messages, response)
        yield {"response": response, "type": "done"}
        return

    if prefer_qwen_response:
        logger.info("orchestration branch %s", kv(mode="property_stream", language=analysis.reply_language))
        for event in stream_ai_support_answer_events(
            issue=_generation_issue(property_issue, analysis),
            customer_name=customer_name,
            customer_email=customer_email,
            business_hours_tag=business_hours_tag,
            issue_type=issue_type,
            article_hint_url=article_hint_url,
            conversation_messages=_recent_history(conversation_messages),
            limit=limit,
            prefer_fast_response=prefer_fast_response,
            prefer_qwen_response=prefer_qwen_response,
        ):
            if event.get("type") == "done" and isinstance(event.get("response"), dict):
                event = {
                    **event,
                    "response": _finalize_property_response(
                        event["response"], property_issue, conversation_messages, analysis,
                    ),
                }
                _remember_response(conversation_id, conversation_messages, event["response"])
            yield event
        return

    logger.info("orchestration branch %s", kv(mode="rag_pipeline_stream", language=analysis.reply_language))
    response = run_conversation_pipeline(
        issue=resolved_issue,
        conversation_messages=conversation_messages,
        support_handler=lambda: build_ai_support_answer(
            issue=_generation_issue(resolved_issue, analysis),
            customer_name=customer_name,
            customer_email=customer_email,
            business_hours_tag=business_hours_tag,
            issue_type=issue_type,
            article_hint_url=article_hint_url,
            conversation_messages=_recent_history(conversation_messages),
            limit=limit,
            prefer_fast_response=prefer_fast_response,
            prefer_qwen_response=prefer_qwen_response,
        ),
    )
    _log_retrieval(resolved_issue, response, is_property=analysis.is_property)
    if isinstance(response, dict):
        response["agent_mode"] = normalize_agent_mode(response.get("agent_mode"))
        response.update(_language_fields(analysis))
    _remember_response(conversation_id, conversation_messages, response)
    yield {"response": response, "type": "done"}
