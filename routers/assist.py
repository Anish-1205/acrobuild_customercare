"""Assist HTTP endpoints."""
from services.amenity_search_service import (
    is_reverse_amenity_query,
    live_amenity_index,
    live_amenity_names,
    match_amenity_terms,
)
from services.property_clarification_service import (
    apply_clarification_contract, resume_selection, continues_selection, build_inventory_selection_answer,
    narrow_project_choice_by_locality, build_project_browse_response, is_unmatched_selection_reply,
    build_unmatched_selection_answer, project_detail_followup, build_project_detail_choice,
)
from graph.haystack_conversation_pipeline import is_small_talk_message
from services.project_home_type_service import (
    build_catalogue_home_type_answer, build_generic_home_type_answer,
    build_project_home_type_answer, requested_home_types,
)
import re
from time import monotonic
from dataclasses import replace

from fastapi import APIRouter, Request
from services import acrobuild_company_service as company_service
from services.conversation_store_service import (
    COOKIE_NAME,
    PENDING_CALL_BOOKING_MARKER,
    PENDING_HUMAN_CONTACT_MARKER,
    ConversationSession,
    build_current_project_marker,
    build_discovery_slots_marker,
    build_pending_project_lookup_marker,
    get_pending_project_lookup,
    latest_discovery_slots,
)
from services.discovery_slot_service import (
    build_discovery_answer,
    build_reset_answer,
    discovery_enabled,
    explicit_locality_search_text,
    is_reset_only,
    is_reset_request,
    is_slot_reply,
)
from services.property_tools_service import project_localities

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


# -----------------------------------
# DISCOVERY SLOTS (Inquiry to Sales §28), behind ACROBUILD_DISCOVERY_SLOTS
# -----------------------------------
# Every helper here returns None / "" / False when the flag is off, so the
# existing request path is unchanged.

class _LiveProjectNames:
    """Live project names, fetched only if the discovery check needs them (a
    configuration question). An unavailable catalogue yields no names; the
    discovery builder's own live read then reports the outage honestly."""

    def __iter__(self):
        try:
            projects = company_service.customer_facing_projects(company_service.get_company_projects())
        except (RuntimeError, TimeoutError):
            return iter(())
        return iter([str(project.get("projectName") or "").strip() for project in projects])


def _live_places():
    """Live locality and city values. Empty when the catalogue is unavailable, so
    the turn keeps today's routing and its own reads report the outage."""
    try:
        projects = company_service.customer_facing_projects(company_service.get_company_projects())
    except (RuntimeError, TimeoutError):
        return []
    return sorted({place for project in projects for place in project_localities(project)})


_REDACTED_CS_ERROR = "Live data request failed; details are in the server log."


def _discovery_slots(request):
    """Stored discovery slots for this conversation, or None when the flag is off."""
    if not discovery_enabled():
        return None
    return latest_discovery_slots(request.conversation_messages)


def _discovery_texts(cleaned_issue, turn):
    return [text for text in (cleaned_issue, getattr(turn.analysis, "english", "")) if text]


def _discovery_slot_reply(slots, cleaned_issue, turn):
    """This turn answers the awaited discovery slot (budget or area)."""
    return bool(slots) and any(is_slot_reply(slots, text) for text in _discovery_texts(cleaned_issue, turn))


def _discovery_reset(slots, cleaned_issue, turn):
    """"start over" / "reset" / "new search" / "clear my preferences" with slots stored."""
    return bool(slots) and any(is_reset_request(text) for text in _discovery_texts(cleaned_issue, turn))


def _discovery_reset_only(slots, cleaned_issue, turn):
    """A bare "start over" with slots stored: answered by a fixed reply, no LLM."""
    return bool(slots) and turn.analysis.intent not in {"call_booking", "human_contact"} and any(
        is_reset_only(text) for text in _discovery_texts(cleaned_issue, turn))


def _is_discovery_pending(pending):
    return isinstance(pending, dict) and (pending.get("source") == "discovery" or pending.get("purpose") == "discovery")


def _discovery_answer(issue, slots, pending):
    """Discovery draft for this turn, or None. A pending selection from another
    flow keeps priority: discovery only continues its own pending state."""
    if slots is None or not discovery_enabled() or (pending is not None and not _is_discovery_pending(pending)):
        return None
    # A live area named in the customer's own words is a catalogue search even with
    # a project in context: answer their text, without the project the resolver
    # appended. A project they name themselves never reaches here (no suffix).
    project_names = _LiveProjectNames()
    payload = build_discovery_answer(
        explicit_locality_search_text(issue, _live_places, project_names) or issue, slots, pending, project_names)
    if payload is None:
        return None
    # A discovery answer is a catalogue-wide search: it must never set
    # current_project, even when a single project matches. Skipped projects
    # are disclosed by name only; their raw CS API error stays in server logs.
    payload = {**payload, "catalogue_home_type_search": True,
               "skipped": [{"project": str(entry.get("project") or "")}
                           for entry in payload.get("skipped") or [] if isinstance(entry, dict)]}
    if isinstance(payload.get("pending_project_lookup"), dict):
        payload["pending_project_lookup"] = {**payload["pending_project_lookup"], "source": "discovery"}
    return payload


def _discovery_slots_marker(response_payload, slots=None, slot_reply=False, reset=False):
    """The discovery_slots marker to store with this turn ("" = keep the previous one)."""
    if slots is None:
        return ""
    # A discovery answer built this turn (after any reset) carries the slots to keep.
    if "discovery_slots" in response_payload:
        return build_discovery_slots_marker(response_payload.get("discovery_slots") or {})
    if reset:
        return build_discovery_slots_marker({}) if slots else ""
    if slots.get("awaiting") and not slot_reply:
        # The customer moved on: the stored question lapses, the slots stay.
        return build_discovery_slots_marker({**slots, "awaiting": None})
    return ""


def _grounded_property_shortcut(request, turn, failure_state=None, pending=None, slots=None):
    """Router-level grounded answers only for property turns, matched on the English
    rendering so they work for questions asked in any language."""
    if not turn.analysis.is_property:
        return None
    shortcut_request = request
    if turn.property_issue != str(request.issue or "").strip():
        shortcut_request = SupportAssistRequest.model_validate({**request.model_dump(), "issue": turn.property_issue})
    # A selected option has already been folded into an effective question.
    # It is not an amenity/area narrowing reply to the preceding option list.
    narrowing_pending = None if (isinstance(pending, dict) and
                                 pending.get("effective_issue") == request.issue) else pending
    try:
        payload = (
            build_grounded_site_visit_document_assist(shortcut_request)
            # Discovery slot flow (IS §28); None whenever the flag is off.
            or _discovery_answer(shortcut_request.issue, slots, pending)
            # A catalogue home-type filter is also shaped like a reverse
            # amenity query ("what properties have ..."). Handle the explicit
            # BHK signal first so an amenity lookup cannot intercept it or,
            # on failure, prevent the home-type search from running.
            or build_catalogue_home_type_answer(shortcut_request.issue)
            or build_project_home_type_answer(shortcut_request.issue, turn.conversation_messages)
            # A numberless BHK question ("what bhks are available") names no
            # specific type, so neither builder above matches it; without this,
            # it fell through to the general pipeline, which could re-ask for
            # the project even when one was already unambiguous from context.
            or build_generic_home_type_answer(shortcut_request.issue, turn.conversation_messages)
            # Reverse amenity search runs first: "which projects have a gym"
            # names no project, so the forward amenities builder below would
            # otherwise answer it as a "which project did you mean?" prompt.
            or (build_grounded_amenity_search_assist(shortcut_request, narrowing_pending)
                if not requested_home_types(shortcut_request.issue) else None)
            or narrow_project_choice_by_locality(narrowing_pending, shortcut_request.issue)
            or (build_project_detail_choice(narrowing_pending)
                if narrowing_pending and narrowing_pending.get("purpose") == "project_details" else None)
            or (build_unmatched_selection_answer(narrowing_pending)
                if _unmatched_selection_reply(narrowing_pending, request.issue, turn) else None)
            or build_inventory_selection_answer(request.issue, pending)
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


def _is_broad_project_request(*issues):
    """Only unscoped catalogue requests; named and location questions use normal routing."""
    allowed = {"what", "which", "show", "list", "browse", "tell", "me", "us", "all",
               "the", "your", "you", "do", "does", "have", "has", "are", "is", "any",
               "available", "projects", "project", "there", "at", "with", "acrobuild", "our",
               "hi", "hello", "mee", "kada", "em", "emi", "vunnai", "vunnayi", "unnai", "unnayi",
               "ikkada", "enni", "konni", "lo", "e", "unnaya"}
    for issue in issues:
        words = re.findall(r"[a-z]+", str(issue or "").lower())
        if not words or not set(words).intersection({"project", "projects"}):
            continue
        if set(words) <= allowed and (set(words) & {"what", "which", "show", "list", "browse", "available", "have", "has", "em", "emi", "vunnai", "unnai", "unnayi"}):
            return True
    return False


def _resume_project_lookup_request(request, pending, customer_issue):
    if not pending:
        return request, customer_issue
    if pending.get("kind") == "selection":
        # Older/fallback discovery replies stored a generic selection instead
        # of explore_project. A click must become an overview request, not the
        # original catalogue question with a selected name appended to it.
        if pending.get("entity") == "project" and _is_broad_project_request(pending.get("original_issue")):
            pending["purpose"] = "explore_project"
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


def _unmatched_selection_reply(pending, issue, turn):
    """A short reply that selects no offered option and is not small talk or a
    new request: re-ask the choice rather than answer it from general chat."""
    return bool(is_unmatched_selection_reply(pending, issue)
                and not is_small_talk_message(issue)
                and not is_small_talk_message(turn.analysis.english or ""))


def _prepare_lookup_turn(request, cleaned_issue, slots=None):
    turn = prepare_turn(cleaned_issue, request.conversation_id, _history(request), request.language_hint)
    pending = _pending_project_lookup(request.conversation_messages)
    selection_reply = bool(pending and continues_selection(pending, cleaned_issue))
    # A bare reset answers no pending choice, so it must not read live amenity or area data for one.
    can_narrow = bool(pending and not selection_reply and not _discovery_reset_only(slots, cleaned_issue, turn)
                      and turn.analysis.intent not in {"call_booking", "human_contact"})
    narrows_by_amenity = bool(can_narrow and _narrows_selection_by_amenity(pending, turn.property_issue))
    narrows_by_locality = bool(can_narrow and _narrows_selection_by_locality(pending, turn.property_issue))
    unmatched_reply = bool(can_narrow and not (narrows_by_amenity or narrows_by_locality)
                           and _unmatched_selection_reply(pending, cleaned_issue, turn))
    detail_followup = None
    if can_narrow and not (narrows_by_amenity or narrows_by_locality or unmatched_reply):
        try:
            detail_followup = project_detail_followup(pending, turn.analysis.english or turn.property_issue)
        except (RuntimeError, TimeoutError):
            # Keep the offered scope and complete new request available for retry.
            if re.search(r"amenit|facilit|location|address|pricing|price|cost", cleaned_issue, re.I):
                detail_followup = {**pending, "original_issue": cleaned_issue, "purpose": "project_details"}
    if detail_followup:
        pending = detail_followup
    if pending and (turn.analysis.intent in {"call_booking", "human_contact"}
                    or not (selection_reply or narrows_by_amenity or narrows_by_locality or unmatched_reply or detail_followup)):
        pending = None
    # An amenity reply to "which project did you mean?" is a narrowing answer,
    # not a project selection: the disambiguation message explicitly invites it
    # ("tell me an amenity that matters to you"). Resuming the selection here
    # would find no matching option and just re-ask the same question, so leave
    # the issue untouched and let the amenity shortcut handle it.
    if pending and (narrows_by_amenity or narrows_by_locality or unmatched_reply or detail_followup):
        processing_request, processing_issue = request, cleaned_issue
    else:
        processing_request, processing_issue = _resume_project_lookup_request(request, pending, cleaned_issue)
    if turn.analysis.intent not in {"call_booking", "human_contact"}:
        if pending:
            turn = replace(turn, resolved_issue=processing_issue, property_issue=(turn.analysis.english or processing_issue) if detail_followup else processing_issue,
                           analysis=replace(turn.analysis, intent="property", unsure=False))
        elif any(term in cleaned_issue.lower() for term in ("amenit", "facilit")):
            # Preserve the English rendering and resolved project context. Only
            # use the customer's text if analysis dropped the explicit topic.
            property_issue = turn.property_issue if any(
                term in turn.property_issue.lower() for term in ("amenit", "facilit")
            ) else cleaned_issue
            turn = replace(turn, property_issue=property_issue,
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
    # "1.5 crore" answering the discovery budget question, or "Wakad lo"
    # answering the area question after its pending selection was dropped, is a
    # property turn whatever the analyzer called it (IS §28). Only then.
    if (slots and slots.get("awaiting") in {"budget", "locality"} and pending is None
            and turn.analysis.intent not in {"call_booking", "human_contact"}
            and _discovery_slot_reply(slots, cleaned_issue, turn)):
        turn = replace(turn, analysis=replace(turn.analysis, intent="property", unsure=False))
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


def _current_project_marker(response_payload, pending=None):
    """Store resolved project scope even after clarification state is gone."""
    if response_payload.get("route") != "property":
        return ""
    response_pending = response_payload.get("pending_project_lookup")
    if response_payload.get("catalogue_home_type_search") or (
        isinstance(response_pending, dict)
        and response_pending.get("entity") == "project"
        and not (response_pending.get("scope") or {}).get("project")
    ):
        return build_current_project_marker("")

    names = []
    for state in (response_pending, pending):
        if isinstance(state, dict):
            name = str((state.get("scope") or {}).get("project") or "").strip()
            if name:
                names.append(name)
    for chunk in response_payload.get("matched_chunks") or []:
        project = chunk.get("project")
        name = str(project.get("projectName") or "").strip() if isinstance(project, dict) else ""
        name = name or str(chunk.get("project_name") or "").strip()
        if name:
            names.append(name)
    names = list(dict.fromkeys(names))
    return build_current_project_marker(names[0]) if len(names) == 1 else ""


def _conversation_state_marker(response_payload, pending=None, customer_issue="", shortcut_failed=False,
                               slots=None, slot_reply=False, reset=False):
    return (
        _project_lookup_marker(response_payload, pending, customer_issue, shortcut_failed)
        + _current_project_marker(response_payload, pending)
        + _discovery_slots_marker(response_payload, slots, slot_reply, reset)
    )


def _turn_marker(response_payload, pending=None, customer_issue="", shortcut_failed=False,
                 slots=None, slot_reply=False, reset=False):
    """Server-only state stored with a completed turn, shared by both endpoints."""
    discovery = _discovery_slots_marker(response_payload, slots, slot_reply, reset)
    if response_payload.get("pending_call_booking"):
        return PENDING_CALL_BOOKING_MARKER + discovery
    if response_payload.get("pending_human_contact"):
        return PENDING_HUMAN_CONTACT_MARKER + discovery
    return (_project_lookup_marker(response_payload, pending, customer_issue, shortcut_failed)
            + _current_project_marker(response_payload, pending) + discovery)


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
    if (turn.analysis.is_property and response_payload.get("source_status") in {"live_api", "snapshot"}
            and not response_payload.get("pending_project_lookup")
            and not response_payload.get("clarification_entity")
            and not response_payload.get("quick_replies")):
        project_names = set()
        for chunk in response_payload.get("matched_chunks", []):
            if isinstance(chunk.get("project"), dict):
                project_names.add(str(chunk["project"].get("projectName") or "").strip())
            # The main orchestration pipeline's chunks (pricing, location,
            # overview, availability, wing/floor/flat inventory) name the
            # project with a plain "project_name" string instead of the
            # amenities builder's nested "project" dict.
            project_names.add(str(chunk.get("project_name") or "").strip())
            # The cost/location grounded shortcuts evidence a resolved single
            # project as a one-entry "projects" list rather than either shape
            # above.
            chunk_projects = chunk.get("projects")
            if isinstance(chunk_projects, list) and len(chunk_projects) == 1 and isinstance(chunk_projects[0], dict):
                project_names.add(str(chunk_projects[0].get("projectName") or "").strip())
        project_names.discard("")
        project_name = next(iter(project_names)) if len(project_names) == 1 else ""
        response_payload["quick_replies"] = [
            {"label": "Browse all projects", "value": "Show me all projects", "action": "browse_projects"},
            {"label": "Book a site visit", "value": "Book a site visit", "action": "site_visit", "project_name": project_name},
            {"label": "Raise a support ticket", "value": "Raise a support ticket", "action": "ticket"},
        ]
    response_payload = localize_response(response_payload, turn.analysis)
    response_payload["data_api_calls"] = data_api_calls
    response_payload["rag_evaluation"] = evaluate_rag_response(cleaned_issue, response_payload, data_api_calls)
    if response_payload.get("discovery_kind"):
        # Discovery never sends raw CS API error text to the client; the full
        # text is already in the server log (log_data_api_call / _log_turn_result).
        response_payload["data_api_calls"] = [
            {**call, "error": _REDACTED_CS_ERROR} if call.get("error") else call for call in data_api_calls
        ]
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
        slots = _discovery_slots(request)
        pending_lookup, processing_request, processing_issue, turn = _prepare_lookup_turn(
            request, cleaned_issue, slots=slots)
        slot_reply = _discovery_slot_reply(slots, cleaned_issue, turn)
        reset_slots = _discovery_reset(slots, cleaned_issue, turn)
        shortcut_failure: dict[str, bool] = {}
        # call_booking/human_contact are explicit/actionable by construction
        # (regex-matched phrasing) — the LLM's fuzzy "unsure" judgement must
        # not divert either to the generic action menu instead of their own
        # phone/time or name/phone prompt below.
        # Checked on the resumed issue too, so "retry" after a catalogue outage
        # re-offers the catalogue instead of falling into generic routing.
        if _discovery_reset_only(slots, cleaned_issue, turn):
            turn_logger.info("turn branch %s", kv(branch="discovery_reset"))
            response_payload = build_reset_answer()
        elif _is_broad_project_request(processing_issue, turn.property_issue):
            turn_logger.info("turn branch %s", kv(branch="project_browse"))
            response_payload = build_project_browse_response(processing_issue)
            reset_slots = True  # browsing the whole catalogue starts a fresh search
        elif turn.analysis.unsure and turn.analysis.intent not in {"call_booking", "human_contact"}:
            turn_logger.info("turn branch %s", kv(branch="confusion_action_menu"))
            response_payload = build_confusion_response(turn.analysis)
        else:
            # "start over, show me 3 BHK": the new search starts from empty slots.
            response_payload = _grounded_property_shortcut(processing_request, turn, shortcut_failure, pending_lookup,
                                                           slots={} if reset_slots else slots)
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
        pending_marker = _turn_marker(response_payload, pending_lookup, cleaned_issue,
                                      shortcut_failure.get("failed", False), slots, slot_reply, reset_slots)
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
            slots = _discovery_slots(request)
            pending_lookup, processing_request, processing_issue, turn = _prepare_lookup_turn(
                request, cleaned_issue, slots=slots)
            slot_reply = _discovery_slot_reply(slots, cleaned_issue, turn)
            reset_slots = _discovery_reset(slots, cleaned_issue, turn)
            shortcut_failure = {}
            if _discovery_reset_only(slots, cleaned_issue, turn):
                turn_logger.info("turn branch %s", kv(branch="discovery_reset"))
                response_payload = _complete_payload(build_reset_answer(), cleaned_issue, turn)
                session.append(cleaned_issue, response_payload.get("answer"),
                               marker=_discovery_slots_marker(response_payload, slots, slot_reply, True))
                yield json.dumps({"text": response_payload["answer"], "type": "delta"}, ensure_ascii=True) + "\n"
                yield json.dumps({"response": response_payload, "type": "done"}, ensure_ascii=True) + "\n"
                _log_turn_result("stream", cleaned_issue, response_payload, started)
                return
            if _is_broad_project_request(processing_issue, turn.property_issue):
                turn_logger.info("turn branch %s", kv(branch="project_browse"))
                response_payload = _complete_payload(build_project_browse_response(processing_issue), cleaned_issue, turn)
                # Browsing the whole catalogue starts a fresh search (reset=True).
                marker = _conversation_state_marker(response_payload, None, cleaned_issue,
                                                    slots=slots, slot_reply=slot_reply, reset=True)
                session.append(cleaned_issue, response_payload.get("answer"), marker=marker)
                yield json.dumps({"text": response_payload["answer"], "type": "delta"}, ensure_ascii=True) + "\n"
                yield json.dumps({"response": response_payload, "type": "done"}, ensure_ascii=True) + "\n"
                _log_turn_result("stream", cleaned_issue, response_payload, started)
                return
            if turn.analysis.unsure and turn.analysis.intent not in {"call_booking", "human_contact"}:
                turn_logger.info("turn branch %s", kv(branch="confusion_action_menu"))
                response_payload = _complete_payload(build_confusion_response(turn.analysis), cleaned_issue, turn)
                session.append(cleaned_issue, response_payload.get("answer"),
                               marker=_discovery_slots_marker(response_payload, slots, slot_reply, reset_slots))
                yield json.dumps({
                    "text": response_payload["answer"], "type": "delta",
                }, ensure_ascii=True) + "\n"
                yield json.dumps({
                    "response": response_payload, "type": "done",
                }, ensure_ascii=True) + "\n"
                _log_turn_result("stream", cleaned_issue, response_payload, started)
                return
            # "start over, show me 3 BHK": the new search starts from empty slots.
            shortcut_payload = _grounded_property_shortcut(processing_request, turn, shortcut_failure, pending_lookup,
                                                           slots={} if reset_slots else slots)
            if shortcut_payload is not None:
                turn_logger.info("turn branch %s", kv(branch="grounded_property_shortcut"))
                response_payload = _complete_payload(shortcut_payload, cleaned_issue, turn)
                session.append(cleaned_issue, response_payload.get("answer"),
                               marker=_turn_marker(response_payload, pending_lookup, cleaned_issue,
                                                   shortcut_failure.get("failed", False), slots, slot_reply,
                                                   reset_slots))
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
                    pending_marker = _turn_marker(response_payload, pending_lookup, cleaned_issue,
                                                  shortcut_failure.get("failed", False), slots, slot_reply,
                                                  reset_slots)
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
