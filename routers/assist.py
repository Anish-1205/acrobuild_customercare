"""Assist HTTP endpoints."""
from services.amenity_search_service import (
    is_reverse_amenity_query,
    live_amenity_index,
    live_amenity_names,
    match_amenity_terms,
)
from services.property_clarification_service import apply_clarification_contract, resume_selection, continues_selection, build_inventory_selection_answer, narrow_project_choice_by_locality
from time import monotonic
from dataclasses import replace

from fastapi import APIRouter, Request
from services.conversation_store_service import (
    COOKIE_NAME,
    PENDING_CALL_BOOKING_MARKER,
    PENDING_HUMAN_CONTACT_MARKER,
    ConversationSession,
    build_pending_project_lookup_marker,
    get_pending_project_lookup,
)

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
    build_grounded_amenity_search_assist,
    build_grounded_project_amenities_assist,
    build_grounded_project_cost_clarification_assist,
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
from graph.main_orchestrator import build_confusion_response, localize_response, prepare_turn

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


def _grounded_property_shortcut(request, turn, failure_state=None, pending=None):
    """Router-level grounded answers only for property turns, matched on the English
    rendering so they work for questions asked in any language."""
    if not turn.analysis.is_property:
        return None
    shortcut_request = request
    if turn.property_issue != str(request.issue or "").strip():
        shortcut_request = SupportAssistRequest.model_validate({**request.model_dump(), "issue": turn.property_issue})
    try:
        payload = (
            # Reverse amenity search runs first: "which projects have a gym"
            # names no project, so the forward amenities builder below would
            # otherwise answer it as a "which project did you mean?" prompt.
            build_grounded_amenity_search_assist(shortcut_request, pending)
            or narrow_project_choice_by_locality(pending, shortcut_request.issue)
            or build_grounded_project_amenities_assist(request)
            or build_inventory_selection_answer(request.issue, pending)
            or build_grounded_site_visit_document_assist(shortcut_request)
            or build_grounded_project_amenities_assist(shortcut_request)
            or build_grounded_project_cost_clarification_assist(shortcut_request)
            or build_grounded_project_location_assist(shortcut_request)
        )
    except (RuntimeError, TimeoutError) as error:
        # A CS API timeout/failure here must not surface as a raw internal
        # error: fall through (return None) so the caller proceeds to the
        # general orchestration path, whose data-api trace already recorded
        # this failure — _enforce_live_property_data() turns that into the
        # existing honest "Live property data is unavailable" message.
        turn_logger.warning("grounded shortcut failed %s", kv(error=str(error)))
        if failure_state is not None:
            failure_state["failed"] = True
        return None
    if payload is not None:
        payload = {**payload, "route": "property"}
    return payload


def _pending_project_lookup(conversation_messages):
    messages = list(conversation_messages or [])
    if not messages or str(messages[-1].sender or "").lower() != "bot":
        return None
    return get_pending_project_lookup(messages[-1].text)


def _resume_project_lookup_request(request, pending, customer_issue):
    if not pending:
        return request, customer_issue
    if pending.get("kind") == "selection":
        effective_issue = resume_selection(pending, customer_issue)
        return SupportAssistRequest.model_validate({**request.model_dump(), "issue": effective_issue}), effective_issue
    selector = str(pending.get("selector") or customer_issue).strip()
    kind = pending["kind"]
    prompts = {
        "amenities": f"What amenities are available in {selector}?",
        "pricing": f"What is the pricing for {selector}?",
        "location": f"Where is {selector} located?",
    }
    effective_issue = prompts[kind]
    return SupportAssistRequest.model_validate({**request.model_dump(), "issue": effective_issue}), effective_issue


def _narrows_selection_by_locality(pending, english_issue):
    """Companion to _narrows_selection_by_amenity for the "tell me the area
    you're looking in" path."""
    try:
        return narrow_project_choice_by_locality(pending, english_issue) is not None
    except (RuntimeError, TimeoutError):
        return False


def _narrows_selection_by_amenity(pending, english_issue):
    """True when the customer answered a pending project choice with an
    amenity ("one with a swimming pool") instead of a project name."""
    if not isinstance(pending, dict) or pending.get("entity") != "project":
        return False
    try:
        names = live_amenity_names(live_amenity_index())
    except (RuntimeError, TimeoutError):
        return False
    return bool(match_amenity_terms(english_issue, names))


def _prepare_lookup_turn(request, cleaned_issue):
    turn = prepare_turn(cleaned_issue, request.conversation_id, _history(request), request.language_hint)
    pending = _pending_project_lookup(request.conversation_messages)
    if pending and (turn.analysis.intent in {"call_booking", "human_contact"}
                    or not continues_selection(pending, cleaned_issue)):
        pending = None
    # An amenity reply to "which project did you mean?" is a narrowing answer,
    # not a project selection: the disambiguation message explicitly invites it
    # ("tell me an amenity that matters to you"). Resuming the selection here
    # would find no matching option and just re-ask the same question, so leave
    # the issue untouched and let the amenity shortcut handle it.
    if pending and (_narrows_selection_by_amenity(pending, turn.property_issue)
                    or _narrows_selection_by_locality(pending, turn.property_issue)):
        processing_request, processing_issue = request, cleaned_issue
    else:
        processing_request, processing_issue = _resume_project_lookup_request(request, pending, cleaned_issue)
    if turn.analysis.intent not in {"call_booking", "human_contact"}:
        if pending or any(term in cleaned_issue.lower() for term in ("amenit", "facilit")):
            turn = replace(turn, resolved_issue=processing_issue, property_issue=processing_issue,
                           analysis=replace(turn.analysis, intent="property", unsure=False))
        # An amenity search ("which projects have a gym") is a property turn
        # even though it names no project and need not contain the word
        # "amenities". Detected on the English rendering so it holds in every
        # supported language -- and property_issue is deliberately left alone
        # here: overwriting it with the raw text would hand the amenity
        # shortcut the customer's untranslated message and break every
        # non-English case.
        elif is_reverse_amenity_query(turn.property_issue):
            turn = replace(turn, analysis=replace(turn.analysis, intent="property", unsure=False))
        elif turn.analysis.is_property:
            turn = replace(turn, analysis=replace(turn.analysis, unsure=False))
    return pending, processing_request, processing_issue, turn


def _project_lookup_marker(response_payload, pending=None, customer_issue="", shortcut_failed=False):
    kind = response_payload.get("pending_project_lookup")
    if kind:
        return build_pending_project_lookup_marker(kind)
    failed = shortcut_failed or response_payload.get("source_status") in {"failed", "unavailable", "error"}
    if pending and failed:
        if pending.get("kind") == "selection":
            return build_pending_project_lookup_marker(pending)
        selector = str(pending.get("selector") or customer_issue).strip()
        return build_pending_project_lookup_marker(pending["kind"], selector, int(pending.get("retry_count") or 0) + 1)
    if failed:
        return build_pending_project_lookup_marker({"kind": "selection", "original_issue": customer_issue,
                                                    "entity": "project", "options": [], "scope": {}})
    return ""


def _complete_payload(response_payload, cleaned_issue, turn):
    """Shared post-processing: live-data enforcement, then localization last so any
    replacement text (e.g. the live-data fallback) is in the customer's language.
    The blob-only localize_ai_answer() is not used: it returned garbled boilerplate."""
    try:
        response_payload = apply_clarification_contract(
            response_payload, turn.property_issue, turn.conversation_messages,
        )
    except (RuntimeError, TimeoutError) as error:
        turn_logger.warning("clarification options unavailable %s", kv(error=str(error)))
        response_payload = {**response_payload, "source_status": "failed"}
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
        pending_lookup, processing_request, processing_issue, turn = _prepare_lookup_turn(request, cleaned_issue)
        shortcut_failure = {}
        # call_booking/human_contact are explicit/actionable by construction
        # (regex-matched phrasing) — the LLM's fuzzy "unsure" judgement must
        # not divert either to the generic action menu instead of their own
        # phone/time or name/phone prompt below.
        if turn.analysis.unsure and turn.analysis.intent not in {"call_booking", "human_contact"}:
            turn_logger.info("turn branch %s", kv(branch="confusion_action_menu"))
            response_payload = build_confusion_response(turn.analysis)
        else:
            response_payload = _grounded_property_shortcut(processing_request, turn, shortcut_failure, pending_lookup)
            if response_payload is not None:
                turn_logger.info("turn branch %s", kv(branch="grounded_property_shortcut"))
            else:
                response_payload = run_support_orchestration(
                    issue=processing_issue,
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
        pending_marker = (
            PENDING_CALL_BOOKING_MARKER if response_payload.get("pending_call_booking")
            else PENDING_HUMAN_CONTACT_MARKER if response_payload.get("pending_human_contact")
            else _project_lookup_marker(response_payload, pending_lookup, cleaned_issue, shortcut_failure.get("failed", False))
        )
        session.append(cleaned_issue, response_payload.get("answer"), marker=pending_marker)
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
            pending_lookup, processing_request, processing_issue, turn = _prepare_lookup_turn(request, cleaned_issue)
            shortcut_failure = {}
            if turn.analysis.unsure and turn.analysis.intent not in {"call_booking", "human_contact"}:
                turn_logger.info("turn branch %s", kv(branch="confusion_action_menu"))
                response_payload = _complete_payload(build_confusion_response(turn.analysis), cleaned_issue, turn)
                session.append(cleaned_issue, response_payload.get("answer"))
                yield json.dumps({
                    "text": response_payload["answer"], "type": "delta",
                }, ensure_ascii=True) + "\n"
                yield json.dumps({
                    "response": response_payload, "type": "done",
                }, ensure_ascii=True) + "\n"
                _log_turn_result("stream", cleaned_issue, response_payload, started)
                return
            shortcut_payload = _grounded_property_shortcut(processing_request, turn, shortcut_failure, pending_lookup)
            if shortcut_payload is not None:
                turn_logger.info("turn branch %s", kv(branch="grounded_property_shortcut"))
                response_payload = _complete_payload(shortcut_payload, cleaned_issue, turn)
                session.append(cleaned_issue, response_payload.get("answer"), marker=_project_lookup_marker(response_payload, pending_lookup, cleaned_issue, shortcut_failure.get("failed", False)))
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
                issue=processing_issue,
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
                    pending_marker = (
                        PENDING_CALL_BOOKING_MARKER if response_payload.get("pending_call_booking")
                        else PENDING_HUMAN_CONTACT_MARKER if response_payload.get("pending_human_contact")
                        else _project_lookup_marker(response_payload, pending_lookup, cleaned_issue, shortcut_failure.get("failed", False))
                    )
                    session.append(cleaned_issue, response_payload.get("answer"), marker=pending_marker)
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
