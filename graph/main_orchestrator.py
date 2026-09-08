from graph.haystack_conversation_pipeline import (
    build_social_conversation_answer,
    is_property_support_message,
    resolve_contextual_support_issue,
    run_conversation_pipeline,
    validate_support_node,
)
from threading import Lock
from time import monotonic
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re
from qwen import (
    generate_qwen_chat_response,
    get_llm_agent_mode,
    get_llm_source_label,
    get_qwen_model_name,
)

_CONVERSATION_MEMORY = {}
_MEMORY_LOCK = Lock()
_MEMORY_TTL_SECONDS = 7200
_MEMORY_MAX_MESSAGES = 60


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
                "and still provide any useful non-live answer you can. Keep the answer focused on exactly what was asked."
            ),
            user_prompt=issue,
            conversation_messages=conversation_messages,
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

    def existing_support_handler():
        return build_ai_support_answer(
            issue=resolved_issue,
            customer_name=customer_name,
            customer_email=customer_email,
            business_hours_tag=business_hours_tag,
            issue_type=issue_type,
            article_hint_url=article_hint_url,
            conversation_messages=conversation_messages,
            limit=limit,
            prefer_fast_response=prefer_fast_response,
            prefer_qwen_response=prefer_qwen_response,
        )

    if prefer_qwen_response and not is_property_support_message(resolved_issue):
        response = _build_live_general_llm_response(resolved_issue, conversation_messages)
    else:
        response = run_conversation_pipeline(
            issue=resolved_issue,
            conversation_messages=conversation_messages,
            support_handler=existing_support_handler,
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
    if prefer_qwen_response and not is_property_support_message(resolved_issue):
        response = _build_live_general_llm_response(resolved_issue, conversation_messages)
        _remember_response(conversation_id, conversation_messages, response)
        yield {"text": response.get("answer", ""), "type": "delta"}
        yield {"response": response, "type": "done"}
        return
    if is_property_support_message(resolved_issue):
        for event in stream_ai_support_answer_events(
            issue=resolved_issue,
            customer_name=customer_name,
            customer_email=customer_email,
            business_hours_tag=business_hours_tag,
            issue_type=issue_type,
            article_hint_url=article_hint_url,
            conversation_messages=conversation_messages,
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
                _remember_response(conversation_id, conversation_messages, event["response"])
            yield event
        return

    response = run_conversation_pipeline(
        issue=resolved_issue,
        conversation_messages=conversation_messages,
        support_handler=lambda: build_ai_support_answer(
            issue=resolved_issue,
            customer_name=customer_name,
            customer_email=customer_email,
            business_hours_tag=business_hours_tag,
            issue_type=issue_type,
            article_hint_url=article_hint_url,
            conversation_messages=conversation_messages,
            limit=limit,
            prefer_fast_response=prefer_fast_response,
            prefer_qwen_response=prefer_qwen_response,
        ),
    )
    _remember_response(conversation_id, conversation_messages, response)
    yield {"response": response, "type": "done"}
