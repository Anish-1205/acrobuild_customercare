"""Assist HTTP endpoints."""
from time import monotonic

from fastapi import APIRouter, Request
from services.conversation_store_service import COOKIE_NAME, ConversationSession

from services.observability import (
    get_logger,
    get_request_id,
    kv,
    mask_email,
    preview,
    set_conversation_id,
    set_request_id,
)
from api_context import (
    HTTPException,
    Response,
    StreamingResponse,
    SupportAssistRequest,
    VoiceSynthesisRequest,
    _enforce_live_property_data,
    begin_data_api_trace,
    build_grounded_project_amenities_assist,
    build_grounded_project_location_assist,
    build_grounded_site_visit_document_assist,
    clear_assist_response_cache,
    end_data_api_trace,
    evaluate_rag_response,
    generate_fast_indic_speech,
    generate_indic_speech,
    get_current_data_api_logs,
    get_support_base_url,
    json,
    run_support_orchestration,
    stream_support_orchestration_events,
)
from graph.main_orchestrator import localize_response, prepare_turn

router = APIRouter(tags=["assist"])

turn_logger = get_logger("assist")


def _log_turn_start(kind, request, cleaned_issue):
    set_conversation_id(request.conversation_id)
    turn_logger.info(
        "turn start %s",
        kv(
            kind=kind,
            conversation_id=request.conversation_id or "-",
            customer=mask_email(request.customer_email),
            issue_type=request.issue_type or "-",
            limit=request.limit,
            prefer_fast=bool(request.prefer_fast_response),
            prefer_qwen=bool(request.prefer_qwen_response),
            history_turns=len([m for m in request.conversation_messages if str(m.text or "").strip()]),
            question=preview(cleaned_issue),
        ),
    )
    turn_logger.debug("turn question (full) %s", kv(question=cleaned_issue))


def _log_turn_result(kind, cleaned_issue, payload, started):
    payload = payload or {}
    data_calls = payload.get("data_api_calls") or []
    failed_calls = [c for c in data_calls if c.get("status") == "failed"]
    rag = payload.get("rag_evaluation") or {}
    turn_logger.info(
        "turn done %s",
        kv(
            kind=kind,
            duration_ms=round((monotonic() - started) * 1000, 1),
            agent_mode=payload.get("agent_mode"),
            source_status=payload.get("source_status"),
            retrieval_mode=payload.get("retrieval_mode"),
            used_llm=payload.get("used_llm"),
            confidence=payload.get("confidence_label"),
            handoff=payload.get("handoff_recommended"),
            model=payload.get("model"),
            matched_chunks=len(payload.get("matched_chunks") or []),
            data_api_calls=len(data_calls),
            data_api_failed=len(failed_calls),
            rag_type=rag.get("evaluation_type"),
            assist_error=payload.get("assist_error") or None,
            answer=preview(payload.get("answer")),
        ),
    )
    if failed_calls:
        for call in failed_calls:
            turn_logger.warning(
                "data api failed %s",
                kv(provider=call.get("provider"), endpoint=call.get("endpoint"),
                   duration_ms=call.get("duration_ms"), error=call.get("error")),
            )
    turn_logger.debug("turn answer (full) %s", kv(answer=payload.get("answer")))

def _history(request):
    return [message.model_dump() for message in request.conversation_messages if str(message.text or "").strip()]


def _grounded_property_shortcut(request, turn):
    """Router-level grounded answers only for property turns, matched on the English
    rendering so they work for questions asked in any language."""
    if not turn.analysis.is_property:
        return None
    shortcut_request = request
    if turn.property_issue != str(request.issue or "").strip():
        shortcut_request = SupportAssistRequest.model_validate({**request.model_dump(), "issue": turn.property_issue})
    payload = (
        build_grounded_site_visit_document_assist(shortcut_request)
        or build_grounded_project_amenities_assist(shortcut_request)
        or build_grounded_project_location_assist(shortcut_request)
    )
    if payload is not None:
        payload = {**payload, "route": "property"}
    return payload


def _complete_payload(response_payload, cleaned_issue, turn):
    """Shared post-processing: live-data enforcement, then localization last so any
    replacement text (e.g. the live-data fallback) is in the customer's language.
    The blob-only localize_ai_answer() is not used: it returned garbled boilerplate."""
    data_api_calls = get_current_data_api_logs()
    response_payload = _enforce_live_property_data(response_payload, cleaned_issue, data_api_calls)
    response_payload = localize_response(response_payload, turn.analysis)
    response_payload["data_api_calls"] = data_api_calls
    response_payload["rag_evaluation"] = evaluate_rag_response(cleaned_issue, response_payload, data_api_calls)
    return response_payload


@router.post("/api/support/assist")
def get_support_assist(request: SupportAssistRequest, http_request: Request, response: Response):
    session = ConversationSession(http_request.cookies.get(COOKIE_NAME, ""), request.conversation_id)
    session.set_cookie(response)
    saved_history = session.load()
    if saved_history:
        request = SupportAssistRequest.model_validate({**request.model_dump(), "conversation_messages": saved_history})
    cleaned_issue = str(request.issue or "").strip()
    if not cleaned_issue:
        raise HTTPException(status_code=400, detail="Issue is required.")

    started = monotonic()
    _log_turn_start("assist", request, cleaned_issue)
    clear_assist_response_cache()
    trace_token = begin_data_api_trace(request.conversation_id, cleaned_issue)
    try:
        turn = prepare_turn(cleaned_issue, request.conversation_id, _history(request), request.language_hint)
        response_payload = _grounded_property_shortcut(request, turn)
        if response_payload is not None:
            turn_logger.info("turn branch %s", kv(branch="grounded_property_shortcut"))
        else:
            response_payload = run_support_orchestration(
                issue=cleaned_issue,
                conversation_id=request.conversation_id,
                customer_name=request.customer_name,
                customer_email=request.customer_email,
                business_hours_tag=request.business_hours_tag,
                issue_type=request.issue_type,
                article_hint_url=request.article_hint_url,
                conversation_messages=_history(request),
                limit=min(max(int(request.limit or 3), 1), 6),
                prefer_fast_response=bool(request.prefer_fast_response),
                prefer_qwen_response=bool(request.prefer_qwen_response),
                language_hint=request.language_hint,
                turn=turn,
            )
        response_payload = _complete_payload(response_payload, cleaned_issue, turn)
        _log_turn_result("assist", cleaned_issue, response_payload, started)
        session.append(cleaned_issue, response_payload.get("answer"))
        return response_payload
    except Exception:
        turn_logger.exception("turn failed %s", kv(kind="assist", question=preview(cleaned_issue)))
        raise
    finally:
        end_data_api_trace(trace_token)

@router.post("/api/support/voice/synthesize")
def synthesize_support_voice(request: VoiceSynthesisRequest):

    try:
        audio_bytes = generate_fast_indic_speech(request.text, request.language)
        media_type = "audio/mpeg"
        if audio_bytes is None:
            audio_bytes = generate_indic_speech(
                text=request.text,
                description=request.description,
            )
            media_type = "audio/wav"
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return Response(
        content=audio_bytes,
        media_type=media_type,
        headers={"Cache-Control": "no-store"},
    )

@router.post("/api/support/assist/stream")
def stream_support_assist(request: SupportAssistRequest, http_request: Request):
    session = ConversationSession(http_request.cookies.get(COOKIE_NAME, ""), request.conversation_id)
    saved_history = session.load()
    if saved_history:
        request = SupportAssistRequest.model_validate({**request.model_dump(), "conversation_messages": saved_history})
    cleaned_issue = str(request.issue or "").strip()
    if not cleaned_issue:
        raise HTTPException(status_code=400, detail="Issue is required.")

    started = monotonic()
    request_id = get_request_id()
    _log_turn_start("stream", request, cleaned_issue)

    def event_stream():
        # The streaming generator resumes in a fresh context; re-bind the ids
        # so pipeline logs stay grouped with the HTTP request and conversation.
        set_request_id(request_id)
        set_conversation_id(request.conversation_id)
        delta_count = 0
        streamed_chars = 0
        response_payload = None
        clear_assist_response_cache()
        trace_token = begin_data_api_trace(request.conversation_id, cleaned_issue)
        try:
            turn = prepare_turn(cleaned_issue, request.conversation_id, _history(request), request.language_hint)
            shortcut_payload = _grounded_property_shortcut(request, turn)
            if shortcut_payload is not None:
                turn_logger.info("turn branch %s", kv(branch="grounded_property_shortcut"))
                response_payload = _complete_payload(shortcut_payload, cleaned_issue, turn)
                session.append(cleaned_issue, response_payload.get("answer"))
                yield json.dumps({
                    "text": response_payload["answer"], "type": "delta",
                }, ensure_ascii=True) + "\n"
                yield json.dumps({
                    "response": response_payload, "type": "done",
                }, ensure_ascii=True) + "\n"
                _log_turn_result("stream", cleaned_issue, response_payload, started)
                return
            property_events = []
            # Property answers are buffered because validation, the live-data guard and
            # localization can replace the draft text before it is final.
            property_request = turn.analysis.is_property
            turn_logger.info(
                "turn branch %s",
                kv(branch="property" if property_request else "conversational",
                   language=turn.analysis.reply_language, source=turn.analysis.source),
            )
            for event in stream_support_orchestration_events(
                issue=cleaned_issue,
                conversation_id=request.conversation_id,
                customer_name=request.customer_name,
                customer_email=request.customer_email,
                business_hours_tag=request.business_hours_tag,
                issue_type=request.issue_type,
                article_hint_url=request.article_hint_url,
                conversation_messages=_history(request),
                limit=min(max(int(request.limit or 3), 1), 6),
                prefer_fast_response=bool(request.prefer_fast_response),
                prefer_qwen_response=bool(request.prefer_qwen_response),
                language_hint=request.language_hint,
                turn=turn,
            ):
                event_type = event.get("type")
                if event_type == "route":
                    continue
                if event_type == "delta":
                    delta_count += 1
                    streamed_chars += len(str(event.get("text", "")))
                elif event_type not in {"done", None}:
                    turn_logger.debug("stream event %s", kv(type=event_type, stage=event.get("stage")))
                if event_type == "done" and isinstance(event.get("response"), dict):
                    response_payload = _complete_payload(event["response"], cleaned_issue, turn)
                    event["response"] = response_payload
                    session.append(cleaned_issue, response_payload.get("answer"))
                if property_request:
                    property_events.append(event)
                else:
                    yield json.dumps(event, ensure_ascii=True) + "\n"
            if property_request:
                done_event = next((event for event in reversed(property_events) if event.get("type") == "done"), None)
                if done_event and isinstance(done_event.get("response"), dict):
                    response_payload = done_event["response"]
                    final_answer = str(response_payload.get("answer", ""))
                    yield json.dumps({"text": final_answer, "type": "delta"}, ensure_ascii=True) + "\n"
                    yield json.dumps(done_event, ensure_ascii=True) + "\n"

            turn_logger.debug("stream totals %s", kv(delta_events=delta_count, streamed_chars=streamed_chars))
            if isinstance(response_payload, dict):
                _log_turn_result("stream", cleaned_issue, response_payload, started)
            else:
                turn_logger.warning(
                    "turn done %s",
                    kv(kind="stream", note="no final response payload",
                       duration_ms=round((monotonic() - started) * 1000, 1),
                       delta_events=delta_count),
                )
        except Exception:
            turn_logger.exception(
                "stream failed %s",
                kv(question=preview(cleaned_issue), delta_events=delta_count,
                   duration_ms=round((monotonic() - started) * 1000, 1)),
            )
            yield json.dumps({
                "response": {
                    "agent_mode": "fallback",
                    "answer": "I hit an internal error while generating the reply. Please try again or send this to the support team.",
                    "articles": [], "assist_error": "", "confidence_label": "low",
                    "handoff_recommended": True, "knowledge_documents": [], "last_synced_at": None,
                    "matched_chunks": [], "model": "", "retrieval_mode": "empty",
                    "source_label": "Streaming fallback", "source_status": "fallback",
                    "support_base_url": get_support_base_url(), "sync_error": "", "used_llm": False,
                    "data_api_calls": get_current_data_api_logs(),
                },
                "type": "error",
            }, ensure_ascii=True) + "\n"
        finally:
            end_data_api_trace(trace_token)

    response = StreamingResponse(event_stream(), media_type="application/x-ndjson")
    session.set_cookie(response)
    return response


@router.delete("/api/support/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, http_request: Request):
    session = ConversationSession(http_request.cookies.get(COOKIE_NAME, ""), conversation_id)
    session.clear()
    return {"deleted": True}
