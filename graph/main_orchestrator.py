from graph.haystack_conversation_pipeline import (
    build_social_conversation_answer,
    is_property_support_message,
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
from qwen import (
    generate_qwen_chat_response,
    stream_qwen_chat_response,
    get_llm_agent_mode,
    get_llm_source_label,
    get_qwen_model_name,
)
from services.observability import get_logger, kv, normalize_agent_mode, preview

logger = get_logger("orchestrator")

_CONVERSATION_MEMORY = {}
_MEMORY_LOCK = Lock()
_MEMORY_TTL_SECONDS = 7200
_MEMORY_MAX_MESSAGES = 60
_DEFAULT_LLM_HISTORY_TURNS = 10


# Non-Latin scripts + common romanised-Indic marker words / patterns. A message
# hitting these is treated as "not English" for language-consistency filtering.
_NON_LATIN_RE = re.compile(r"[^\x00-\x7f]")
# Transliterated Indic agglutination: "projects-a", "project-um", "Ambernath-la".
# A hyphen glued to a 1-3 letter case suffix almost never occurs in English.
_TRANSLIT_SUFFIX_RE = re.compile(r"[a-z]{2,}-(?:a|um|la|ku|ki|na|nu|il|la|kku|aana|oda|ana)\b", re.IGNORECASE)
_ROMANISED_INDIC_WORDS = frozenset("""
naan naanga naanum naa naam oru onnu ena enna epdi eppo enge yaar evvalavu sollunga
irukku irukka irukkura irukkanum panren panna panrom pannunga pannalam mudiyum venum
illa illai neenga unga ungal ungalukku adhu adhula idhu idhula ovvoru appuram innum sila
paakkalaam thevai konja neram sari vanakkam mattrum
chestunnav chestunav chestunnaru enti entha enthaa emiti ela edi idi meeru meku
unnava unnaru naaku naku kavali kaavali cheppu cheppandi avunu ledu enduku eppudu
ekkada bagunnara namaskaram kaani telusa telidu
kiti lagnar kasa kaay kuthe kevha kartoy ahe aahe pahije mala tumhi kase konta kadhi
kaise kya hai hain chahiye batao bataiye karo karna karni kitna kitne kahan kab kyun
mujhe aap nahin nahi hoga raha rahe kaisa haan bhai
""".split())


def _looks_english(text):
    text = str(text or "").strip()
    if not text:
        return True
    if _NON_LATIN_RE.search(text):
        return False
    if _TRANSLIT_SUFFIX_RE.search(text):
        return False
    words = re.findall(r"[a-zA-Z]+", text.lower())
    if not words:
        return True
    indic_hits = sum(1 for w in words if w in _ROMANISED_INDIC_WORDS)
    return indic_hits / len(words) < 0.15


_ENGLISH_DIRECTIVE = "\n\n[Note: the customer is writing in English. Reply in English.]"


def _generation_issue(issue):
    """Issue text for the answer-writing model. When the customer's message is
    English, append an explicit English directive so the multilingual model
    does not carry over a stale conversation language. Detection/retrieval keep
    the clean issue."""
    if _looks_english(issue):
        return f"{issue}{_ENGLISH_DIRECTIVE}"
    return issue


def _recent_history(conversation_messages, current_issue=None):
    """Trim the merged conversation before handing it to an LLM.

    - Cap to the last N turns (latency + hallucination surface).
    - If the current message is English, drop earlier non-English turns so the
      model does not mirror a stale language (Sarvam is Indian-multilingual and
      will otherwise answer an English question in romanised Tamil/Telugu when
      the history is in that language). The full store is untouched — this only
      shapes the model prompt.
    """
    try:
        turns = max(int(os.getenv("LLM_HISTORY_TURNS", _DEFAULT_LLM_HISTORY_TURNS)), 1)
    except (TypeError, ValueError):
        turns = _DEFAULT_LLM_HISTORY_TURNS
    messages = list(conversation_messages or [])
    if current_issue is not None and _looks_english(current_issue):
        messages = [m for m in messages if _looks_english(m.get("text", ""))]
    return messages[-(turns * 2):]


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


def _build_live_general_llm_response(issue, conversation_messages):
    current_time = _current_local_time()
    runtime_context = current_time.strftime(
        "%A, %d %B %Y at %I:%M %p %Z"
    )
    try:
        answer = generate_qwen_chat_response(
            system_prompt=(
                "You are Acrobuild Support, a virtual real-estate customer-support assistant for Acrobuild's "
                "property customers. Acrobuild is not software. Answer the user's general question directly, "
                "naturally, and accurately using your model knowledge. "
                "For factual questions, do not guess or substitute a different person, place, date, or number. "
                "If you are not confident that a fact is correct, say that you are unsure. "
                f"The current local date and time is {runtime_context}. Use this value directly for date, day, "
                "and time questions instead of claiming that you cannot access it. "
                "Do not invent current Acrobuild property, pricing, availability, company, or customer facts; those "
                "require the live CS API. For other genuinely live external information, clearly state the limitation "
                "and still provide any useful non-live answer you can. Keep the answer focused on exactly what was asked. "
                "Reply in the same language as the user's most recent message; if that message is in English, reply in English."
            ),
            user_prompt=issue,
            conversation_messages=_recent_history(conversation_messages, issue),
            temperature=0,
        )
        grounded_answer = (
            build_social_conversation_answer(issue)
            or _ground_current_date_time_answer(issue, current_time)
            or _ground_current_officeholder_answer(issue)
        )
        answer = grounded_answer or _focus_simple_factual_answer(issue, answer)
        source_label = get_llm_source_label()
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
            "source_label": source_label,
            "source_status": "live",
            "used_llm": True,
        }
    except Exception as error:
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
        }


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
):
    conversation_messages = _merge_conversation(conversation_id, conversation_messages, issue)
    resolved_issue = resolve_contextual_support_issue(issue, conversation_messages)
    if resolved_issue != issue:
        logger.info("issue resolved from context %s", kv(raw=preview(issue, 120), resolved=preview(resolved_issue, 120)))

    def existing_support_handler():
        return build_ai_support_answer(
            issue=_generation_issue(resolved_issue),
            customer_name=customer_name,
            customer_email=customer_email,
            business_hours_tag=business_hours_tag,
            issue_type=issue_type,
            article_hint_url=article_hint_url,
            conversation_messages=_recent_history(conversation_messages, resolved_issue),
            limit=limit,
            prefer_fast_response=prefer_fast_response,
            prefer_qwen_response=prefer_qwen_response,
        )

    is_property = is_property_support_message(resolved_issue)
    if prefer_qwen_response and not is_property:
        logger.info("orchestration branch %s", kv(mode="general_llm", is_property=is_property))
        response = _build_live_general_llm_response(resolved_issue, conversation_messages)
    else:
        logger.info("orchestration branch %s", kv(mode="rag_pipeline", is_property=is_property))
        response = run_conversation_pipeline(
            issue=resolved_issue,
            conversation_messages=conversation_messages,
            support_handler=existing_support_handler,
        )
        _log_retrieval(resolved_issue, response, is_property=is_property)
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
):
    conversation_messages = _merge_conversation(conversation_id, conversation_messages, issue)
    resolved_issue = resolve_contextual_support_issue(issue, conversation_messages)
    if resolved_issue != issue:
        logger.info("issue resolved from context %s", kv(raw=preview(issue, 120), resolved=preview(resolved_issue, 120)))
    is_property = is_property_support_message(resolved_issue)
    if prefer_qwen_response and not is_property:
        logger.info("orchestration branch %s", kv(mode="general_llm_stream", is_property=is_property))
        yield {"type": "progress", "stage": "generating"}
        grounded = build_social_conversation_answer(resolved_issue) or _ground_current_date_time_answer(resolved_issue, _current_local_time())
        if grounded:
            logger.info("grounded shortcut answer used %s", kv(answer=preview(grounded, 120)))
        pieces = []
        if grounded:
            pieces.append(grounded)
            yield {"type": "delta", "text": grounded}
        else:
            for piece in stream_qwen_chat_response(
                system_prompt=("You are Acrobuild Support, a real-estate customer support assistant. "
                               "Answer directly. Do not invent facts or claim access to live external data. "
                               "Current property, price and availability facts require verified CS API evidence. "
                               "Reply in the same language as the user's most recent message; if it is in English, reply in English. "
                               f"Current local time: {_current_local_time().isoformat()}."),
                user_prompt=resolved_issue, conversation_messages=_recent_history(conversation_messages, resolved_issue), temperature=0,
            ):
                pieces.append(piece)
                yield {"type": "delta", "text": piece}
        response = {"answer": "".join(pieces), "agent_mode": normalize_agent_mode(get_llm_agent_mode()),
                    "used_llm": not bool(grounded), "source_label": get_llm_source_label(),
                    "model": get_qwen_model_name(), "source_status": "live", "retrieval_mode": "none",
                    "confidence_label": "medium", "handoff_recommended": False,
                    "articles": [], "knowledge_documents": [], "matched_chunks": [], "assist_error": ""}
        _remember_response(conversation_id, conversation_messages, response)
        yield {"response": response, "type": "done"}
        return
    if is_property:
        logger.info("orchestration branch %s", kv(mode="property_stream"))
        for event in stream_ai_support_answer_events(
            issue=_generation_issue(resolved_issue),
            customer_name=customer_name,
            customer_email=customer_email,
            business_hours_tag=business_hours_tag,
            issue_type=issue_type,
            article_hint_url=article_hint_url,
            conversation_messages=_recent_history(conversation_messages, resolved_issue),
            limit=limit,
            prefer_fast_response=prefer_fast_response,
            prefer_qwen_response=prefer_qwen_response,
        ):
            if event.get("type") == "done" and isinstance(event.get("response"), dict):
                contextual_floor_price = _build_contextual_same_price_floor_answer(
                    str(resolved_issue or "").lower(),
                    event["response"].get("matched_chunks", []),
                    conversation_messages,
                )
                contextual_flat_cost = _build_contextual_flat_cost_answer(
                    str(resolved_issue or "").lower(),
                    conversation_messages,
                )
                contextual_answer = contextual_floor_price or contextual_flat_cost
                if contextual_answer:
                    event["response"] = {
                        **event["response"],
                        "answer": contextual_answer,
                        "confidence_label": "high",
                        "handoff_recommended": False,
                        "used_llm": False,
                    }
                event = {
                    **event,
                    "response": validate_support_node({
                        "issue": resolved_issue,
                        "response": event["response"],
                    })["response"],
                }
                if isinstance(event.get("response"), dict):
                    event["response"]["agent_mode"] = normalize_agent_mode(event["response"].get("agent_mode"))
                _log_retrieval(resolved_issue, event["response"], is_property=True)
                _remember_response(conversation_id, conversation_messages, event["response"])
            yield event
        return

    logger.info("orchestration branch %s", kv(mode="rag_pipeline_stream"))
    response = run_conversation_pipeline(
        issue=resolved_issue,
        conversation_messages=conversation_messages,
        support_handler=lambda: build_ai_support_answer(
            issue=_generation_issue(resolved_issue),
            customer_name=customer_name,
            customer_email=customer_email,
            business_hours_tag=business_hours_tag,
            issue_type=issue_type,
            article_hint_url=article_hint_url,
            conversation_messages=_recent_history(conversation_messages, resolved_issue),
            limit=limit,
            prefer_fast_response=prefer_fast_response,
            prefer_qwen_response=prefer_qwen_response,
        ),
    )
    _log_retrieval(resolved_issue, response, is_property=is_property)
    if isinstance(response, dict):
        response["agent_mode"] = normalize_agent_mode(response.get("agent_mode"))
    _remember_response(conversation_id, conversation_messages, response)
    yield {"response": response, "type": "done"}
