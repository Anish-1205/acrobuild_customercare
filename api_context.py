import base64
from contextlib import asynccontextmanager
import json
import logging
import os
import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    Response,
    StreamingResponse,
)
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware

from graph.workflow import run_workflow
from services.acrobuild_company_service import (
    get_company_projects,
    get_project_amenities,
    customer_facing_projects,
    get_project_wings,
    get_wing_inventory,
    get_wing_typologies,
    resolve_project_candidates_from_text,
    resolve_project_from_text,
    get_cs_api_status,
    get_company_data_snapshot_path,
)
from services.internal_api_log_service import (
    begin_data_api_trace,
    end_data_api_trace,
    get_current_data_api_logs,
)
from services.rag_evaluation_service import evaluate_rag_response

from services.database_service import (
    create_knowledge_document,
    close_ticket,
    create_support_article,
    create_support_user,
    delete_knowledge_documents,
    get_knowledge_document,
    get_knowledge_documents,
    get_ticket,
    get_ticket_messages,
    get_ticket_notes,
    get_support_article,
    get_support_articles,
    get_support_user,
    get_support_users,
    initialize_database,
    MESSAGE_UPLOAD_DIR,
    reset_workspace_knowledge,
    reset_unread,
    save_message,
    save_ticket_note,
    get_all_tickets,
    update_support_article,
    update_support_user,
    update_knowledge_document,
    update_ticket_agent,
    update_ticket_status,
)
from services.knowledge_ingestion_service import (
    ingest_url_knowledge_source,
    ingest_uploaded_knowledge_files,
)
from services.local_product_feed_service import (
    build_local_product_feed_html,
    get_local_product_feed_summary,
    read_local_product_feed_csv,
)
from services.knowledge_index_service import (
    mark_workspace_index_dirty,
    refresh_workspace_index,
    refresh_workspace_index_async,
    get_workspace_index_state,
)
from services.llm_service import is_llm_available, get_llm_provider
from services.database_service import open_database_connection
from services.admin_settings_service import (
    create_workflow_rule,
    create_tag,
    create_business_hours_profile,
    delete_tag,
    delete_business_hours_profile,
    delete_workflow_rule,
    get_business_hours_profile,
    get_business_hours_profiles,
    get_business_hours_rule_windows,
    get_tags,
    get_ticket_tags,
    get_rule_affected_tickets,
    get_workflow_rules,
    merge_tags,
    restore_default_workflow_rule,
    set_ticket_tags,
    update_tag,
    update_business_hours_profile,
    update_workflow_rule,
    duplicate_workflow_rule,
)
from services.macro_service import (
    archive_macro,
    create_macro,
    delete_macro,
    duplicate_macro,
    get_macro,
    get_macros,
    get_recommended_macros_for_ticket,
    increment_macro_usage,
    update_macro,
)
from services.ai_agent_service import (
    answer_matches_response_language,
    localize_ai_answer,
build_ai_support_answer,
    clear_assist_response_cache,
    stream_ai_support_answer_events,
)
from graph.main_orchestrator import (
    run_support_orchestration,
    stream_support_orchestration_events,
)
from graph.haystack_conversation_pipeline import is_property_support_message
from services.property_clarification_service import build_area_no_match_response, build_project_choice_answer, build_amenity_project_choices
from services.amenity_search_service import (
    is_amenity_lookup_query,
    is_reverse_amenity_query,
    live_amenity_index,
    live_amenity_names,
    match_amenity_terms,
    projects_with_amenities,
    scope_index_to_locality,
    resolve_named_project,
)
from services.indic_translation_service import warm_translation_model_async
from services.indic_tts_service import generate_fast_indic_speech, generate_indic_speech
from services.otp_service import (
    request_email_otp,
    validate_email_access_token,
    verify_email_otp,
)
from services.support_article_service import get_support_base_url
from services.auth_service import create_access_token, decode_access_token, verify_password
from services.database_service import get_support_user_for_login
from services.observability import (
    configure_logging,
    get_logger,
    kv,
    new_request_id,
    normalize_agent_mode,
    preview,
    set_request_id,
)

configure_logging()
logger = logging.getLogger(__name__)
request_logger = get_logger("request")

# -----------------------------------
# INIT DATABASE
# -----------------------------------



# Specific, checkable property claims (prices, areas, unit ids) that must be
# backed by retrieved live data — never by the model alone.
_PROPERTY_CLAIM_RE = re.compile(
    r"(₹\s?\d|\bINR\s?\d|\bRs\.?\s?\d|\bper\s*sq|\bsq\.?\s*ft|\bsqft\b|"
    r"\bcarpet\s*area\b|\bflat\s*[#:]?\s*[a-z]?\d)",
    re.IGNORECASE,
)
# Hedges that, combined with a specific number, mean the model contradicted
# itself (blob path runs at temperature 0.35).
_HEDGE_RE = re.compile(
    r"\b(i cannot|i can't|i am not able|i'm not able|unable to provide|"
    r"would be inaccurate|dynamic and change|changes frequently|"
    r"do not have (?:access|the current)|don't have (?:access|the current))\b",
    re.IGNORECASE,
)


def _enforce_live_property_data(response_payload, issue, data_api_calls):
    # The orchestrator's LLM turn analysis is authoritative; the keyword check only
    # covers payloads that carry no route (e.g. router-level grounded shortcuts).
    route = response_payload.get("route")
    # call_booking/human_contact answers are deterministic template text with
    # no CS API involvement; the live-data check below only makes sense for
    # property answers and would otherwise misfire on a booking/contact
    # message that happens to also contain a property-support word like
    # "ticket" or "agent".
    if route in {"general", "call_booking", "human_contact"} or (route != "property" and not is_property_support_message(issue)):
        return response_payload
    # A resource can be requested more than once within a single turn (e.g.
    # get_company_projects() is called from several independent steps); an
    # earlier timeout that a later call to the SAME resource resolved live
    # must not still make the final answer look like it used stale data.
    # data_api_calls is chronological, so keeping only the last entry per
    # (endpoint, params) keeps each resource's most recent, authoritative
    # outcome -- the one that actually fed the answer below.
    latest_calls = {}
    for call in data_api_calls:
        key = (call.get("endpoint"), tuple(sorted((call.get("params") or {}).items())))
        latest_calls[key] = call
    data_api_calls = list(latest_calls.values())
    failed_live_calls = [
        call for call in data_api_calls
        if call.get("provider") == "Acrobuild CS API" and call.get("status") == "failed"
    ]
    snapshot_calls = [
        call for call in data_api_calls
        if "snapshot" in str(call.get("provider", "")).lower()
        and call.get("status") in {"cached", "completed"}
    ]
    snapshot_endpoints = {call.get("endpoint") for call in snapshot_calls}
    uncovered_failures = [
        call for call in failed_live_calls if call.get("endpoint") not in snapshot_endpoints
    ]
    non_live_calls = [
        call for call in data_api_calls
        if (call.get("cache_hit") and str((call.get("response_summary") or {}).get("kind")) != "turn_cache")
        or "snapshot" in str(call.get("provider", "")).lower()
    ]
    completed_live_calls = [
        call for call in data_api_calls
        if call.get("provider") == "Acrobuild CS API" and call.get("status") == "completed"
        and (not call.get("cache_hit") or str((call.get("response_summary") or {}).get("kind")) == "turn_cache")
    ]
    cached_live_calls = [
        call for call in data_api_calls
        if call.get("provider") == "Acrobuild CS API" and call.get("status") == "cached"
    ]

    company_api_chunks = [
        chunk for chunk in response_payload.get("matched_chunks", [])
        if chunk.get("record_kind") == "company_api"
    ]
    answer_text = str(response_payload.get("answer", "") or "")
    makes_specific_claims = bool(_PROPERTY_CLAIM_RE.search(answer_text))
    # Ungrounded: specific figures with nothing retrieved to back them, or a
    # figure sitting next to a "I can't give you a number" hedge.
    ungrounded_answer = makes_specific_claims and (
        not company_api_chunks or bool(_HEDGE_RE.search(answer_text))
    )

    if (completed_live_calls or cached_live_calls) and not failed_live_calls and not snapshot_calls and not ungrounded_answer:
        response_payload["articles"] = []
        response_payload["knowledge_documents"] = []
        response_payload["matched_chunks"] = company_api_chunks
        response_payload["source_label"] = "Live Acrobuild CS API"
        response_payload["source_status"] = "live_api"
        response_payload["agent_mode"] = normalize_agent_mode(response_payload.get("agent_mode"))
        return response_payload

    if snapshot_calls and not uncovered_failures and not ungrounded_answer:
        snapshot_path = Path(get_company_data_snapshot_path()).with_suffix(".json")
        try:
            saved_at = datetime.fromtimestamp(snapshot_path.stat().st_mtime)
            saved_date = f"{saved_at.day} {saved_at:%B %Y}"
        except OSError:
            # The fallback data actually used came from _load_snapshot_fallback()'s
            # in-memory read, not this file lookup; a snapshot answer must not
            # crash just because its on-disk copy is unavailable (e.g. an
            # environment where the snapshot file is deliberately not present).
            saved_date = "an earlier sync"
        answer = answer_text.replace("Availability is live and may change.", "Availability may have changed.")
        answer = re.sub(r"\blive (?:Acrobuild CS API|project data|property data|data|inventory|API)\b",
                        "saved property data", answer, flags=re.IGNORECASE)
        response_payload["answer"] = (
            f"Live property data is unavailable. This answer uses saved data from {saved_date}; "
            "prices and availability may have changed.\n\n" + answer
        )
        response_payload["source_label"] = f"Acrobuild property snapshot ({saved_date})"
        response_payload["source_status"] = "snapshot"
        response_payload["agent_mode"] = normalize_agent_mode(response_payload.get("agent_mode"))
        return response_payload

    if ungrounded_answer and not failed_live_calls and not non_live_calls:
        reason = (
            "the live CS API response did not contain the specific figures in that draft answer, "
            "so I am not stating them"
        )
        source_status = "unverified"
    else:
        errors = list(dict.fromkeys(
            str(call.get("error", "")).strip() for call in failed_live_calls if str(call.get("error", "")).strip()
        ))
        reason = errors[0] if errors else "No successful live CS API response was available for this request."
        source_status = "failed"

    logger.info(
        "property answer rejected %s",
        kv(source_status=source_status, ungrounded=ungrounded_answer,
           failed_calls=len(failed_live_calls), draft=preview(answer_text, 160)),
    )
    response_payload.update({
        "agent_mode": "live_data_error",
        "answer": ("I couldn't verify that from live property data. Please try again shortly."
                   if source_status == "unverified" else
                   "Live property data is unavailable right now. Please try again shortly."),
        "articles": [],
        "confidence_label": "low",
        "handoff_recommended": True,
        "knowledge_documents": [],
        "matched_chunks": [],
        "retrieval_mode": "live_api_error",
        "source_label": "Acrobuild CS API",
        "source_status": source_status,
        "used_llm": False,
        "quick_replies": [],
    })
    return response_payload

# -----------------------------------
# FASTAPI
# -----------------------------------

@asynccontextmanager
async def lifespan(application):
    from services.database_service import DB_PATH
    from services.migration_service import apply_migrations
    initialize_database()
    apply_migrations(DB_PATH)
    warm_ai_knowledge_index()
    yield


api = FastAPI(lifespan=lifespan)
from services.request_security_service import RequestSecurityMiddleware
api.add_middleware(RequestSecurityMiddleware)
from routers.sessions import router as sessions_router
api.include_router(sessions_router)

trusted_origins = [
    origin.strip()
    for origin in os.getenv(
        "ACROBUILD_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
api.add_middleware(
    CORSMiddleware,
    allow_origins=trusted_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
)


def _bearer_token(authorization):
    scheme, _, token = str(authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Authentication required.")
    return token.strip()


def require_workspace_user(authorization: str | None = Header(None), workspace_session: str = Cookie("")):
    try:
        from services.session_service import active_session
        token = workspace_session if isinstance(workspace_session, str) and workspace_session else _bearer_token(authorization)
        claims = active_session(decode_access_token(token))
    except RuntimeError:
        logger.exception("Workspace authentication is not configured")
        raise HTTPException(status_code=503, detail="Authentication is unavailable.")
    except ValueError as error:
        raise HTTPException(status_code=401, detail="Invalid or expired session.") from error
    role = str(claims.get("role", "")).lower()
    if role not in {"owner", "admin", "agent"}:
        raise HTTPException(status_code=403, detail="Workspace access denied.")
    return claims


def require_admin_user(user=Depends(require_workspace_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return user


@api.middleware("http")
async def enforce_admin_route_auth(request: Request, call_next):
    """Backstop authorization for every current and future admin route."""
    path = request.url.path
    # CSRF protection covers workspace-mutating routes only. Public customer
    # endpoints must stay reachable even when the same browser also holds a
    # workspace session cookie (e.g. an admin browsing the customer site).
    csrf_protected = (
        path.startswith("/api/admin/")
        or path.startswith("/admin/")
        or path in {"/auth/logout", "/auth/refresh"}
    )
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        import secrets
        origin = request.headers.get("origin")
        if origin and origin not in trusted_origins and origin != str(request.base_url).rstrip("/"):
            return Response(status_code=403, content='{"detail":"Origin not allowed."}', media_type="application/json")
        if csrf_protected and (request.cookies.get("workspace_session") or request.cookies.get("workspace_refresh")):
            csrf = request.cookies.get("workspace_csrf", "")
            if not csrf or not secrets.compare_digest(csrf, request.headers.get("x-csrf-token", "")):
                return Response(status_code=403, content='{"detail":"CSRF validation failed."}', media_type="application/json")
    if path.startswith("/api/admin/") or path.startswith("/admin/"):
        try:
            claims = require_workspace_user(request.headers.get("Authorization"), request.cookies.get("workspace_session", ""))
        except HTTPException as error:
            return Response(
                content=json.dumps({"detail": error.detail}),
                status_code=error.status_code,
                media_type="application/json",
            )
        destructive = request.method == "DELETE" or path.endswith("/reset") or path.endswith("/restore-default")
        management_prefixes = (
            "/api/admin/users", "/admin/users", "/api/admin/articles", "/admin/articles",
            "/api/admin/knowledge-documents", "/admin/knowledge-documents", "/api/admin/tags",
            "/api/admin/macros", "/api/admin/workflow-rules", "/api/admin/business-hours",
        )
        if destructive:
            allowed_roles = {"admin"}
        elif path.startswith(management_prefixes):
            allowed_roles = {"admin", "owner"}
        else:
            allowed_roles = {"admin", "owner", "agent"}
        if claims.get("role") not in allowed_roles:
            return Response(
                content=json.dumps({"detail": "Insufficient workspace permissions."}),
                status_code=403,
                media_type="application/json",
            )
        request.state.workspace_user = claims
        if claims.get("role") == "agent":
            if path.endswith("/assign") or path.endswith("/tags"):
                return Response(status_code=403)
            match = re.match(r"/(?:api/)?admin/tickets/([^/]+)", path)
            if match:
                ticket = get_ticket(match.group(1))
                if not ticket or ticket.get("assigned_agent") != claims.get("name"):
                    return Response(status_code=404)
    return await call_next(request)


_REQUEST_LOG_PREFIXES = ("/api/support/", "/api/property-flow/", "/create_ticket", "/ticket/")


@api.middleware("http")
async def attach_request_id_and_log(request: Request, call_next):
    """Outermost middleware: give every request a correlation id and log
    one line in / one line out for chatbot-facing routes so a full turn is
    greppable by request_id."""
    from time import monotonic

    incoming = request.headers.get("x-request-id", "").strip()
    request_id = incoming[:64] if incoming else new_request_id()
    set_request_id(request_id)

    path = request.url.path
    tracked = any(path.startswith(prefix) or path == prefix.rstrip("/") for prefix in _REQUEST_LOG_PREFIXES)
    started = monotonic()
    if tracked:
        request_logger.info(
            "request in %s",
            kv(method=request.method, path=path, client=request.client.host if request.client else "-"),
        )
    try:
        response = await call_next(request)
    except Exception:
        if tracked:
            request_logger.exception(
                "request crashed %s",
                kv(method=request.method, path=path, duration_ms=round((monotonic() - started) * 1000, 1)),
            )
        raise

    response.headers["X-Request-ID"] = request_id
    if tracked:
        request_logger.info(
            "request out %s",
            kv(
                method=request.method,
                path=path,
                status=response.status_code,
                duration_ms=round((monotonic() - started) * 1000, 1),
            ),
        )
    return response


def warm_ai_knowledge_index():

    if os.getenv("ACROBUILD_REFRESH_INDEX_ON_STARTUP", "false").strip().lower() in {"1", "true", "yes", "on"}:
        refresh_workspace_index_async()
    if os.getenv("ACROBUILD_WARM_LOCAL_AI_MODELS", "false").strip().lower() in {"1", "true", "yes", "on"}:
        warm_translation_model_async()
# -----------------------------------
# REQUEST MODEL
# -----------------------------------

class OtpRequest(BaseModel):
    email: str


class OtpVerifyRequest(BaseModel):
    email: str
    code: str


class WorkspaceLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=72)

class TicketRequest(BaseModel):
    issue: str = Field(min_length=1, max_length=10000)
    customer_email: str = ""


class SiteVisitRequest(BaseModel):
    customer_name: str
    customer_email: str
    customer_phone: str
    project_name: str
    preferred_date: str
    preferred_time: str
    wing_name: str = ""
    typology_name: str = ""
    unit_number: str = ""
    notes: str = ""

class RefundRequest(BaseModel):
    order_number: str


class SubscriptionCancelRequest(BaseModel):
    subscription_id: str


class TicketMessageRequest(BaseModel):
    ticket_id: str
    message: str
    access_token: str = ""


class TicketStatus(str, Enum):
    open = "Open"
    pending = "Pending"
    waiting_on_customer = "Waiting on Customer"
    resolved = "Resolved"
    closed = "Closed"


class WorkspaceRole(str, Enum):
    owner = "owner"
    admin = "admin"
    agent = "agent"


class MessageSender(str, Enum):
    admin = "admin"
    owner = "owner"
    agent = "agent"


class UpdateTicketAgentRequest(BaseModel):
    ticket_id: str = ""
    agent_name: str


class UpdateTicketStatusRequest(BaseModel):
    ticket_id: str
    status: TicketStatus


class TicketTagUpdateRequest(BaseModel):
    tag_ids: list[int]


class AdminTicketMessageRequest(BaseModel):
    message: str
    sender: MessageSender = MessageSender.admin


class AdminTicketAttachmentRequest(BaseModel):
    content_base64: str = Field(max_length=14000000)
    mime_type: str = ""
    name: str = "attachment"


class AdminTicketReplyRequest(BaseModel):
    applied_macro_id: int | None = None
    attachments: list[AdminTicketAttachmentRequest] = Field(default_factory=list, max_length=5)
    message: str = ""
    sender: MessageSender = MessageSender.admin


class AdminTicketNoteRequest(BaseModel):
    author: str = ""
    note: str


class BusinessHoursRangeRequest(BaseModel):
    day_name: str
    start_time: str
    end_time: str


class BusinessHoursProfileRequest(BaseModel):
    name: str
    timezone_name: str
    ranges: list[BusinessHoursRangeRequest]
    description: str = ""
    is_default: bool = False


class TagRequest(BaseModel):
    name: str
    description: str = ""
    color: str = ""


class TagMergeRequest(BaseModel):
    target_tag_id: int
    source_tag_ids: list[int]


class MacroRequest(BaseModel):
    name: str
    response_text: str
    language: str = "English"
    description: str = ""
    category: str = ""
    subject_template: str = ""
    set_status: str = ""
    tag_names: list[str] = []


class MacroArchiveRequest(BaseModel):
    is_archived: bool = True


class SupportUserCreateRequest(BaseModel):
    email: str
    name: str
    role: WorkspaceRole = WorkspaceRole.agent
    status: str = "Invited"
    team: str = "Support"


class SupportUserUpdateRequest(BaseModel):
    name: str
    role: WorkspaceRole
    status: str
    team: str


class SupportArticleCreateRequest(BaseModel):
    body: str = ""
    category: str = "Support"
    keywords: list[str] = []
    status: str = "Draft"
    summary: str = ""
    title: str
    url: str = ""


class SupportArticleUpdateRequest(BaseModel):
    body: str = ""
    category: str = "Support"
    keywords: list[str] = []
    status: str = "Draft"
    summary: str = ""
    title: str
    url: str = ""


class WorkflowRuleUpdateRequest(BaseModel):
    name: str
    description: str = ""
    true_tag_id: int | None = None
    false_tag_id: int | None = None
    builder_mode: str | None = None
    config: dict[str, Any] | None = None
    is_enabled: bool = True


class SupportAssistConversationMessageRequest(BaseModel):
    sender: str = "customer"
    text: str = Field(default="", max_length=10000)


class SupportAssistRequest(BaseModel):
    article_hint_url: str = ""
    business_hours_tag: str = ""
    conversation_id: str = ""
    conversation_messages: list[SupportAssistConversationMessageRequest] = Field(default_factory=list, max_length=60)
    customer_email: str = ""
    customer_name: str = ""
    issue: str = Field(min_length=1, max_length=10000)
    issue_type: str = ""
    limit: int = 3
    prefer_fast_response: bool = False
    prefer_qwen_response: bool = True
    language_hint: str = Field(default="", max_length=40)


class VoiceSynthesisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=3000)
    description: str = ""
    language: str = ""


class KnowledgeDocumentCreateRequest(BaseModel):
    body: str = ""
    category: str = "Knowledge"
    source_name: str = ""
    source_type: str = "manual"
    status: str = "Draft"
    summary: str = ""
    tags: list[str] = []
    title: str


class KnowledgeDocumentUpdateRequest(BaseModel):
    body: str = ""
    category: str = "Knowledge"
    source_name: str = ""
    source_type: str = "manual"
    status: str = "Draft"
    summary: str = ""
    tags: list[str] = []
    title: str


class KnowledgeDocumentDeleteRequest(BaseModel):
    document_ids: list[int] = []


class KnowledgeUploadFileRequest(BaseModel):
    content_base64: str = Field(max_length=14000000)
    mime_type: str = ""
    name: str


class KnowledgeDocumentUploadRequest(BaseModel):
    category: str = "Knowledge"
    files: list[KnowledgeUploadFileRequest] = Field(min_length=1, max_length=5)
    source_name: str = ""
    status: str = "Draft"
    tags: list[str] = []


class KnowledgeDocumentUrlImportRequest(BaseModel):
    body_note: str = ""
    category: str = "Knowledge"
    status: str = "Published"
    summary: str = ""
    source_type: str = "url"
    tags: list[str] = []
    title_prefix: str = ""
    url: str


PROJECT_ROOT = Path(__file__).resolve().parent


def build_admin_attachment_url(relative_path: str):
    return f"/api/admin/attachment?path={quote(relative_path, safe='')}"


def enrich_entries_with_attachment_urls(entries):
    enriched_entries = []

    for entry in entries:
        next_entry = dict(entry)
        attachments = []

        for attachment in entry.get("attachments", []):
            next_attachment = dict(attachment)
            relative_path = str(next_attachment.get("path", "")).strip()

            if relative_path:
                next_attachment["url"] = build_admin_attachment_url(relative_path)

            attachments.append(next_attachment)

        next_entry["attachments"] = attachments
        enriched_entries.append(next_entry)

    return enriched_entries


def decode_admin_reply_attachments(attachments):
    decoded_attachments = []

    for attachment in attachments or []:
        raw_content = str(attachment.content_base64 or "").strip()

        if not raw_content:
            continue

        if "," in raw_content and raw_content.lower().startswith("data:"):
            raw_content = raw_content.split(",", 1)[1]

        try:
            file_bytes = base64.b64decode(raw_content, validate=True)
        except Exception as error:
            raise HTTPException(status_code=400, detail="Invalid attachment payload.") from error

        if len(file_bytes) > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Each attachment must be 5 MB or smaller.")

        decoded_attachments.append(
            {
                "bytes": file_bytes,
                "mime_type": str(attachment.mime_type or "").strip(),
                "name": str(attachment.name or "attachment").strip() or "attachment",
            }
        )

    return decoded_attachments


def resolve_or_create_tag_id_map(tag_names):
    existing_tags = get_tags()
    tag_id_map = {
        str(tag.get("name", "")).strip().lower(): int(tag["id"])
        for tag in existing_tags
        if str(tag.get("name", "")).strip()
    }
    resolved_ids = {}

    for tag_name in tag_names or []:
        normalized_name = str(tag_name or "").strip()

        if not normalized_name:
            continue

        normalized_key = normalized_name.lower()

        if normalized_key not in tag_id_map:
            create_tag(name=normalized_name)
            refreshed_tags = get_tags()
            tag_id_map = {
                str(tag.get("name", "")).strip().lower(): int(tag["id"])
                for tag in refreshed_tags
                if str(tag.get("name", "")).strip()
            }

        if normalized_key in tag_id_map:
            resolved_ids[normalized_name] = tag_id_map[normalized_key]

    return resolved_ids


def apply_macro_tags_to_ticket(ticket_id: str, ticket_tags, macro_tag_names):
    resolved_tag_map = resolve_or_create_tag_id_map(macro_tag_names)

    if not resolved_tag_map:
        return

    manual_tag_ids = {
        int(tag["id"])
        for tag in ticket_tags
        if tag.get("source") == "manual"
    }

    set_ticket_tags(
        ticket_id,
        sorted(manual_tag_ids.union(resolved_tag_map.values())),
    )


def get_ticket_recommended_macros(ticket):
    ticket_tags = get_ticket_tags(ticket["ticket_id"])
    ticket_tag_names = [
        str(tag.get("name", "")).strip()
        for tag in ticket_tags
        if str(tag.get("name", "")).strip()
    ]

    return get_recommended_macros_for_ticket(
        ticket,
        ticket_tag_names=ticket_tag_names,
        limit=12,
    )


def refresh_support_assist_state():

    clear_assist_response_cache()
    mark_workspace_index_dirty(
        rebuild_async=False,
    )

def _customer_facing_projects(projects):
    """Drop non-project records the live CS API mixes into the projects list
    (e.g. id 55 "GBK Group" -- the company entity itself, with
    address="palvinder@gbkgroup.in" instead of a street address). isPublished
    is not usable as a signal here: it is False for every record, including
    every legitimate project."""
    return customer_facing_projects(projects)


def _resolve_project_selection(projects, texts):
    """Return ``(selected_project, ambiguous_candidates)`` for ordered text.

    The current issue is passed first and therefore takes precedence over
    conversation history. Multiple matches stop the search so an ambiguous new
    name can never silently fall back to an older project selection.
    """
    for text in texts:
        candidates = resolve_project_candidates_from_text(projects, text)
        if len(candidates) == 1:
            return candidates[0], []
        if len(candidates) > 1:
            return None, candidates
    return None, []


def _build_ambiguous_project_response(candidates, lookup_label):
    candidate_names = list(dict.fromkeys(
        str(project.get("projectName", "")).strip()
        for project in candidates
        if str(project.get("projectName", "")).strip()
    ))
    # Shared with services/property_clarification_service.py so the "which
    # project did you mean?" wording is identical everywhere it is asked.
    answer = build_project_choice_answer(candidate_names, lookup_label)
    evidence = {
        "body_text": "\n".join(candidate_names),
        "category": "AcroBuild property data",
        "excerpt": f"{len(candidate_names)} matching projects; clarification required",
        "projects": candidates,
        "record_kind": "company_api",
        "score": 100.0,
        "source_key": f"acrobuild-cs-projects-{lookup_label}-ambiguity",
        "source_name": "AcroBuild CS API",
        "title": f"Projects matching {lookup_label} question",
        "url": "",
    }
    return {
        "agent_mode": "knowledge_retrieval",
        "answer": answer,
        "articles": [],
        "assist_error": "",
        "confidence_label": "high",
        "handoff_recommended": False,
        "knowledge_documents": [],
        "last_synced_at": None,
        "matched_chunks": [evidence],
        "model": "",
        "retrieval_mode": "live_project_records",
        "source_label": "Retrieved AcroBuild project data",
        "source_status": "live_api",
        "support_base_url": get_support_base_url(),
        "sync_error": "",
        "used_llm": False,
        "pending_project_lookup": lookup_label,
    }


def build_grounded_site_visit_document_assist(request):

    issue = str(request.issue or "").strip()
    cleaned_issue = issue.lower()
    asks_documents = "document" in cleaned_issue
    asks_site_visit = (
        any(term in cleaned_issue for term in ("site", "visit", "book", "booking"))
        and asks_documents
    )
    if not asks_site_visit:
        return None

    projects = _customer_facing_projects(get_company_projects())
    customer_history = [str(message.text or "").strip() for message in request.conversation_messages if str(message.sender or "").lower() == "customer" and str(message.text or "").strip()]
    selected_project, candidates = _resolve_project_selection(projects, [issue, *reversed(customer_history)])
    if candidates or (selected_project is None and projects):
        payload = _build_ambiguous_project_response(candidates or projects, "documents")
        payload["clarification_entity"] = "project"
        return payload
    project_name = (
        str(selected_project.get("projectName", "")).strip()
        if selected_project
        else "your selected project"
    )
    articles = [
        article for article in get_support_articles()
        if "site visit" in (
            str(article.get("title", "")) + " " + str(article.get("body", ""))
        ).lower()
    ]
    answer = (
        f"You don't need to upload any documents to request a site visit for {project_name}. "
        "Please provide the visitor's name, preferred date and time, purpose of the visit, "
        "and a callback number. The slot is confirmed only after the site coordinator approves it. "
        "If the team later needs identification or another document for site access, they will tell you specifically."
    )
    evidence = {
        "body_text": "\n".join(str(article.get("body", "")) for article in articles),
        "category": "Site Visit",
        "excerpt": "Site-visit booking requirements retrieved from support guidance",
        "record_kind": "article",
        "score": 100.0,
        "source_key": "site-visit-booking-requirements",
        "source_name": "Support knowledge base",
        "title": "Site visit booking requirements",
        "url": "",
    }
    return {
        "agent_mode": "knowledge_retrieval",
        "answer": answer,
        "articles": articles,
        "assist_error": "",
        "confidence_label": "high",
        "handoff_recommended": False,
        "knowledge_documents": [],
        "last_synced_at": None,
        "matched_chunks": [evidence],
        "model": "",
        "retrieval_mode": "knowledge_base",
        "source_label": "Support knowledge base",
        "source_status": "workspace",
        "support_base_url": get_support_base_url(),
        "sync_error": "",
        "used_llm": False,
    }

def build_grounded_project_amenities_assist(request):

    issue = str(request.issue or "").strip()
    cleaned_issue = issue.lower()
    if not any(
        term in cleaned_issue
        for term in ("amenit", "facilit")
    ):
        return None

    projects = _customer_facing_projects(get_company_projects())
    customer_history = [str(message.text or "").strip() for message in request.conversation_messages if str(message.sender or "").lower() == "customer" and str(message.text or "").strip()]
    catalogue_request = is_reverse_amenity_query(issue) and not re.search(
        r"\b(?:this|that|it|its|these|those|selected)\b", issue, re.I,
    )
    selected_project, ambiguous_candidates = _resolve_project_selection(
        projects, [issue, *([] if catalogue_request else reversed(customer_history))],
    )
    if ambiguous_candidates:
        return _build_ambiguous_project_response(
            ambiguous_candidates, "amenities",
        )
    if selected_project is None:
        if projects:
            index, locality = scope_index_to_locality(live_amenity_index(), issue)
            return build_amenity_project_choices(issue, index, locality)
        answer = (
            "The live catalogue currently lists no projects to select. Please try again later."
        )
        evidence = {
            "body_text": "\n".join(
                str(project.get("projectName", "")).strip()
                for project in projects
                if str(project.get("projectName", "")).strip()
            ),
            "category": "AcroBuild property data",
            "excerpt": f"{len(projects)} available projects; project selection required",
            "projects": projects,
            "record_kind": "company_api",
            "score": 100.0,
            "source_key": "acrobuild-cs-projects-amenity-selection",
            "source_name": "AcroBuild CS API",
            "title": "Projects available for amenity lookup",
            "url": "",
        }
        return {
            "agent_mode": "knowledge_retrieval",
            "answer": answer,
            "articles": [],
            "assist_error": "",
            "confidence_label": "high",
            "handoff_recommended": False,
            "knowledge_documents": [],
            "last_synced_at": None,
            "matched_chunks": [evidence],
            "model": "",
            "retrieval_mode": "live_project_records",
            "source_label": "Retrieved AcroBuild project data",
            "source_status": "live_api",
            "support_base_url": get_support_base_url(),
            "sync_error": "",
            "used_llm": False,
            "pending_project_lookup": "amenities",
        }

    project_name = str(selected_project.get("projectName", "Project")).strip()
    # GET /api/cs/{companyId}/projects/{id}/amenities is the curated amenity list for
    # the project ({iconName, type, url}, type is "Amenities" or "Facilities").
    # typology.get("unitAmenities") (the old source) is empty on every
    # typology of every project in the catalogue and can never return data.
    amenity_records = get_project_amenities(selected_project["id"])
    # Amenities and Facilities are merged into one flat list: the trigger
    # condition above already treats "amenities" and "facilities" as the same
    # customer intent, and the answer template below has always presented a
    # single list under one heading, so this keeps that existing structure
    # rather than introducing a second section customers didn't ask for.
    amenities = list(dict.fromkeys(
        str(record.get("iconName", "")).strip()
        for record in amenity_records
        if isinstance(record, dict) and str(record.get("iconName", "")).strip()
    ))
    if amenities:
        answer = "\n".join([
            f"The available data lists these amenities for {project_name}:",
            "",
            *[f"- {amenity}" for amenity in amenities],
        ])
    else:
        answer = (
            f"The available project data does not currently list amenities for {project_name}. "
            "Please contact the sales team for the latest confirmed amenity details."
        )

    if re.search(r"\b(location|address|located|where)\b", issue, re.I):
        location = str(selected_project.get("location") or selected_project.get("address") or selected_project.get("city") or "").strip()
        answer += f"\n\nLocation: {location or 'Not listed in the live project record.'}"
    answer += "\n\nWould you like to raise a support ticket, book a site visit, or request a call?"

    evidence = {
        "body_text": answer,
        "category": "AcroBuild property data",
        "excerpt": f"{len(amenity_records)} amenity record(s) checked via the project amenities endpoint",
        "project": selected_project,
        "record_kind": "company_api",
        "score": 100.0,
        "source_key": f"acrobuild-cs-project-{selected_project['id']}-amenities",
        "source_name": "AcroBuild CS API",
        "title": f"{project_name} amenities",
        "url": "",
        "amenities_checked": len(amenity_records),
    }
    return {
        "agent_mode": "knowledge_retrieval",
        "answer": answer,
        "articles": [],
        "assist_error": "",
        "confidence_label": "high",
        "handoff_recommended": False,
        "knowledge_documents": [],
        "last_synced_at": None,
        "matched_chunks": [evidence],
        "model": "",
        "retrieval_mode": "live_project_records",
        "source_label": "Retrieved AcroBuild project data",
        "source_status": "live_api",
        "support_base_url": get_support_base_url(),
        "sync_error": "",
        "used_llm": False,
    }


def _amenity_search_payload(answer, evidence_body, source_key, title, projects, amenities):
    return {
        "agent_mode": "knowledge_retrieval",
        "answer": answer,
        "articles": [],
        "assist_error": "",
        "confidence_label": "high",
        "handoff_recommended": False,
        "knowledge_documents": [],
        "last_synced_at": None,
        "matched_chunks": [{
            "body_text": evidence_body,
            "category": "AcroBuild property data",
            "excerpt": f"{len(projects)} project(s) checked against live amenity records",
            "projects": projects,
            "amenities_matched": amenities,
            "record_kind": "company_api",
            "score": 100.0,
            "source_key": source_key,
            "source_name": "AcroBuild CS API",
            "title": title,
            "url": "",
        }],
        "model": "",
        "retrieval_mode": "live_project_records",
        "source_label": "Retrieved AcroBuild project data",
        "source_status": "live_api",
        "support_base_url": get_support_base_url(),
        "sync_error": "",
        "used_llm": False,
        "amenity_search": True,
    }


def _amenity_phrase(terms):
    if len(terms) == 1:
        return terms[0]
    return ", ".join(terms[:-1]) + " and " + terms[-1]


def _pending_project_options(pending):
    """Project names a pending "which project did you mean?" is waiting on."""
    if not isinstance(pending, dict) or pending.get("kind") != "selection":
        return []
    if pending.get("entity") != "project":
        return []
    return [str(name).strip() for name in (pending.get("options") or []) if str(name).strip()]


def build_grounded_amenity_search_assist(request, pending=None):
    """Reverse amenity search: "which projects have a gym", "where can I find a
    swimming pool", and the single-project "does X have a gym?" form.

    Every project name and amenity name in the answer comes from the live CS
    API (services/amenity_search_service.py builds the index off
    /api/cs/{companyId}/projects and /api/cs/{companyId}/projects/{id}/amenities). If the customer's
    words do not resolve to an amenity that actually exists in that live data,
    this returns None and the turn continues down the normal path -- it never
    guesses a match.

    ``pending`` is the project selection this turn is answering, if any. The
    disambiguation message offers "tell me an amenity that matters to you and
    I'll shortlist the ones that fit", so a bare amenity reply ("one with a
    swimming pool") has to be honoured here -- it is not shaped like a
    question, and without this it fell through and re-showed the same list.
    """
    issue = str(request.issue or "").strip()
    if not issue:
        return None
    narrowing_options = _pending_project_options(pending)
    # Cheap shape test before touching the API at all. Skipped while narrowing
    # a pending selection, where a bare amenity phrase is the whole reply.
    if not narrowing_options and not (
        is_reverse_amenity_query(issue)
        or re.search(r"\b(?:does|do|has|have|is|are|got)\b", issue, re.I)
    ):
        return None

    index = live_amenity_index()
    live_names = live_amenity_names(index)
    if narrowing_options:
        if not match_amenity_terms(issue, live_names):
            return None  # not an amenity reply; let selection handling have it
        index = {key: entry for key, entry in index.items()
                 if str(entry["project"].get("projectName", "")).strip() in narrowing_options}
    elif not is_amenity_lookup_query(issue, live_names):
        return None
    terms = match_amenity_terms(issue, live_names)
    phrase = _amenity_phrase(terms)

    named_project = (
        None if (narrowing_options or is_reverse_amenity_query(issue))
        else resolve_named_project(issue)
    )
    if named_project is not None:
        # "Does Vishwajeet Prime have a gym?" -- same live records, yes/no form.
        entry = index.get(named_project["id"], {"amenities": []})
        project_name = str(named_project.get("projectName", "Project")).strip()
        present = [term for term in terms if term in entry["amenities"]]
        missing = [term for term in terms if term not in entry["amenities"]]
        if present and not missing:
            answer = (
                f"Yes — the live data for {project_name} lists {_amenity_phrase(present)}."
            )
        elif present:
            answer = (
                f"Partly — {project_name} lists {_amenity_phrase(present)}, but its live "
                f"amenity record does not list {_amenity_phrase(missing)}."
            )
        else:
            answer = (
                f"The live amenity record for {project_name} does not list "
                f"{phrase}. I can show you its full amenity list, or tell you which "
                "of our projects do list it."
            )
        others = [
            str(entry_value["project"].get("projectName", "")).strip()
            for entry_value in index.values()
            if entry_value["project"]["id"] != named_project["id"]
            and all(term in entry_value["amenities"] for term in terms)
        ]
        if missing or not present:
            if others:
                answer += "\n\nThese projects do list it:\n\n" + "\n".join(f"- {name}" for name in others)
        return _amenity_search_payload(
            answer, "\n".join(entry["amenities"]),
            f"acrobuild-cs-project-{named_project['id']}-amenity-check",
            f"{project_name} amenity check", [named_project], terms,
        )

    # "which projects in Pune have a gym" must not be answered from the whole
    # catalogue; scope to the live locality/city the customer named, if any.
    index, locality = scope_index_to_locality(index, issue)
    where = f" in {locality}" if locality else ""
    matches, per_term = projects_with_amenities(index, terms)
    names = [str(project.get("projectName", "")).strip() for project in matches]
    if names and narrowing_options:
        # Narrowing an open "which project?" question: shortlist, and keep the
        # original request pending so naming one of these resumes it.
        answer = "\n".join([
            f"Of those, {'this one lists' if len(names) == 1 else 'these list'} {phrase}:",
            "",
            *[f"- {name}" for name in names],
            "",
            "Shall I go ahead with " + (f"{names[0]}?" if len(names) == 1
                                        else "one of these? Just tell me which."),
        ])
    elif names:
        answer = "\n".join([
            f"These projects{where} list {phrase} in their live amenity data:",
            "",
            *[f"- {name}" for name in names],
            "",
            "Tell me which one you'd like and I'll pull up its full amenity list, "
            "pricing or location.",
        ])
    elif len(terms) > 1 and any(per_term[term] for term in terms):
        lines = [f"No project{where} currently lists all of {phrase} together. Here is what the live data does list:", ""]
        for term in terms:
            found = [str(project.get("projectName", "")).strip() for project in per_term[term]]
            lines.append(f"- {term}: " + (", ".join(found) if found else "not listed for any project right now"))
        lines += ["", "Tell me which of these matters most and I'll take it from there."]
        answer = "\n".join(lines)
    else:
        answer = (
            f"None of our projects{where} currently list {phrase} in their live amenity data. "
            "That data only covers what each project has published, so it is worth asking "
            "the sales team as well. I can also show you the full amenity list for any project."
        )
    payload = _amenity_search_payload(
        answer, "\n".join(f"{name}: {', '.join(entry['amenities'])}" for name, entry in
                          ((str(v["project"].get("projectName", "")).strip(), v) for v in index.values())),
        f"acrobuild-cs-amenity-search-{'-'.join(t.lower().replace(' ', '-') for t in terms)}",
        f"Projects listing {phrase}", matches, terms,
    )
    if narrowing_options:
        # Keep the customer's ORIGINAL request alive, now waiting on a shorter
        # list, so naming one of these answers what they first asked.
        payload["pending_project_lookup"] = {
            **pending,
            "options": names or narrowing_options,
        }
    elif names:
        payload["pending_project_lookup"] = {
            "kind": "selection", "entity": "project", "options": names,
            "scope": {}, "original_issue": issue, "purpose": "amenity_search",
        }
    if payload.get("pending_project_lookup"):
        payload["clarification_entity"] = "project"
        payload["quick_replies"] = [
            {"label": name, "value": name}
            for name in payload["pending_project_lookup"]["options"]
        ]
    return payload


def build_grounded_project_cost_clarification_assist(request):
    """Clarify an ambiguous project fragment before price retrieval.

    Non-ambiguous cost questions return ``None`` and continue through the
    existing detailed pricing/inventory pipeline.
    """
    issue = str(request.issue or "").strip()
    cleaned_issue = issue.lower()
    if not (
        any(term in cleaned_issue for term in ("cost", "price", "pricing", "rate", "budget"))
        or "how much" in cleaned_issue
    ):
        return None

    projects = _customer_facing_projects(get_company_projects())
    customer_history = [
        str(message.text or "").strip()
        for message in request.conversation_messages
        if str(message.sender or "").lower() == "customer" and str(message.text or "").strip()
    ]
    selected_project, ambiguous_candidates = _resolve_project_selection(
        projects, [issue, *reversed(customer_history)],
    )
    if selected_project is not None:
        # Detailed unit/budget/comparison requests retain their inventory path.
        if re.search(r"\b(?:wing|floor|flat|unit|shop|budget|under|below|above|cheapest|highest|lowest|compare|total)\b|\d\s*bhk", cleaned_issue):
            return None
        from services.acrobuild_company_service import get_project_typologies
        records = get_project_typologies(selected_project["id"])
        prices = list(dict.fromkeys(
            f"{record.get('typologyName') or 'Home type'}: INR {record.get('minBasePrice')}"
            f" to INR {record.get('maxBasePrice')} ({record.get('rateType') or 'rate basis not specified'})"
            for record in records
            if record.get("minBasePrice") is not None and record.get("maxBasePrice") is not None
        ))
        payload = _build_ambiguous_project_response([selected_project], "pricing")
        payload.pop("pending_project_lookup", None)
        payload["answer"] = (
            f"Live API-listed base pricing for {selected_project['projectName']}:\n\n"
            + "\n".join(f"- {price}" for price in prices)
            + "\n\nThese are the API-listed base rates, not an all-inclusive flat quotation."
            if prices else f"The live API currently lists no base pricing for {selected_project['projectName']}."
        )
        payload["matched_chunks"][0].update(body_text=payload["answer"], typologies=records,
                                          source_key=f"acrobuild-cs-project-{selected_project['id']}-pricing")
        return payload
    ambiguous_candidates = ambiguous_candidates or projects
    if not ambiguous_candidates:
        return None
    return _build_ambiguous_project_response(
        ambiguous_candidates, "pricing",
    )

def _known_localities(projects):
    """Real city/locality values pulled straight from live project records --
    the only values a resolved "location" is ever allowed to be, so a noisy
    or over-captured piece of text can never leak into a customer answer."""
    values = set()
    for project in projects:
        for key in ("city", "locality"):
            value = str(project.get(key, "") or "").strip()
            if value:
                values.add(value)
    return values


def _resolve_known_location(candidate_text, known_localities):
    """Match loosely-captured candidate text against real localities, longest
    first so a more specific match (e.g. "Ambernath East") wins over a
    shorter one (e.g. "Ambernath") that also happens to appear in it."""
    for locality in sorted(known_localities, key=len, reverse=True):
        if re.search(rf"\b{re.escape(locality.lower())}\b", candidate_text):
            return locality
    return None


def build_grounded_project_location_assist(request):

    issue = str(request.issue or "").strip()
    cleaned_issue = issue.lower()
    messages = [
        {
            "sender": str(message.sender or "").strip().lower(),
            "text": str(message.text or "").strip(),
        }
        for message in request.conversation_messages
        if str(message.text or "").strip()
    ]
    prior_customer_text = " ".join(
        message["text"]
        for message in messages[:-1]
        if message["sender"] == "customer"
    ).lower()
    has_project_subject = any(
        term in cleaned_issue
        for term in ("project", "projects", "property", "properties")
    )
    inherits_project_subject = (
        bool(re.search(r"\b(?:any|one|ones)\s+(?:of\s+them\s+)?in\s+", cleaned_issue))
        and any(
            term in prior_customer_text
            for term in ("project", "projects", "property", "properties")
        )
    )
    asks_location = (
        any(
            term in cleaned_issue
            for term in ("address", "city", "located", "location", "where")
        )
        or bool(re.search(
            r"\b(?:projects?|properties)\b.*\b(?:in|at|near)\s+",
            cleaned_issue,
        ))
        or inherits_project_subject
    )
    # "What is there / what's available / what do you have in <area>?" names an
    # area but no project word (the English rendering of e.g. "Kompally lo em
    # unnai?" varies between these forms). It is only an area question when it
    # names no project ("what is there in Vishwajeet Heights?" is about that
    # project, not a place).
    asks_area = not asks_location and bool(re.search(
        r"^(?:what(?:'s|\s+is|\s+are|\s+all)*|anything)"
        r"(?:\s+(?:there|available|do\s+you\s+have|you\s+have|have\s+you\s+got))*\s+in\s+[a-z]",
        cleaned_issue,
    ))
    if not (asks_location or asks_area):
        return None

    projects = _customer_facing_projects(get_company_projects())
    if not projects:
        return None
    if asks_area and resolve_project_candidates_from_text(projects, issue):
        return None

    selected_project, ambiguous_candidates = _resolve_project_selection(
        projects, [issue, prior_customer_text],
    )
    if ambiguous_candidates:
        return _build_ambiguous_project_response(
            ambiguous_candidates, "location",
        )
    asks_selected_project_location = (
        selected_project is not None
        and (
            any(term in cleaned_issue for term in ("this project", "its location", "its address"))
            or any(
                term in cleaned_issue
                for term in ("address", "located", "location", "where")
            )
        )
    )
    if asks_selected_project_location:
        project_name = str(selected_project.get("projectName", "Project")).strip()
        project_location = str(
            selected_project.get("location")
            or selected_project.get("address")
            or selected_project.get("city")
            or ""
        ).strip()
        answer = f"{project_name}: {project_location}"
    else:
        location_match = re.search(
            r"\b(?:in|at|near)\s+([a-z][a-z .'-]*?)(?:\?|\.|$)",
            cleaned_issue,
        )
        if not location_match:
            return _build_ambiguous_project_response(projects, "location")
        # Loosely-captured candidate text (may contain extra words the LLM's
        # English rendering added, e.g. "the properties in thane" or "pune
        # with you") -- never used directly. The resolved location must be a
        # real city/locality value from live project data, matched inside it.
        candidate_text = " ".join(location_match.group(1).strip().split())
        if not candidate_text:
            return None

        resolved_location = _resolve_known_location(candidate_text, _known_localities(projects))
        if resolved_location is None:
            return build_area_no_match_response(issue, projects)
        else:
            matching_projects = []
            for project in projects:
                location_text = " ".join(
                    str(project.get(key, "") or "")
                    for key in ("address", "locality", "city", "location", "zipcode")
                ).lower()
                if resolved_location.lower() in location_text:
                    matching_projects.append(project)

            location_label = resolved_location
            if matching_projects:
                lines = [
                    f"Yes, we currently have {len(matching_projects)} project"
                    + ("" if len(matching_projects) == 1 else "s")
                    + f" in {location_label}:",
                    "",
                ]
                lines.extend(
                    f"- {str(project.get('projectName', 'Project')).strip()}: "
                    f"{str(project.get('location') or project.get('address') or project.get('city') or '').strip()}"
                    for project in matching_projects
                )
                answer = "\n".join(lines)
            else:
                # Defensive only: resolved_location came from real project
                # city/locality data, so this should be unreachable.
                city_values = sorted({
                    str(project.get("city", "")).strip()
                    for project in projects
                    if str(project.get("city", "")).strip()
                })
                answer = f"No, we currently don't have any projects in {location_label}."
                if city_values:
                    available_cities = ", ".join(city_values)
                    answer += (
                        f" Our available projects are in {available_cities}."
                        if len(city_values) == 1
                        else f" Our available projects are in these cities: {available_cities}."
                    )

    project_chunk = {
        "body_text": "\n".join(
            f"{project.get('projectName', 'Project')}: "
            f"{project.get('location') or project.get('address') or project.get('city') or ''}"
            for project in projects
        ),
        "category": "AcroBuild property data",
        "excerpt": f"{len(projects)} retrieved project records",
        "projects": projects,
        "record_kind": "company_api",
        "score": 100.0,
        "source_key": "acrobuild-cs-projects",
        "source_name": "AcroBuild CS API",
        "title": "Company projects",
        "url": "",
    }
    return {
        "agent_mode": "knowledge_retrieval",
        "answer": answer,
        "articles": [],
        "assist_error": "",
        "confidence_label": "high",
        "handoff_recommended": False,
        "knowledge_documents": [],
        "last_synced_at": None,
        "matched_chunks": [project_chunk],
        "model": "",
        "retrieval_mode": "live_project_records",
        "source_label": "Retrieved AcroBuild project data",
        "source_status": "live_api",
        "support_base_url": get_support_base_url(),
        "sync_error": "",
        "used_llm": False,
    }

# -----------------------------------
# ROUTES
# -----------------------------------










# -----------------------------------



def _cs_api_response(loader, question):
    trace_token = begin_data_api_trace("property-flow", question)
    try:
        items = loader()
        return {
            "data_api_calls": get_current_data_api_logs(),
            "items": items,
        }
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    finally:
        end_data_api_trace(trace_token)















def _authorize_customer_identity(email, access_token="", authorization=""):
    if access_token and validate_email_access_token(email, access_token):
        return
    if authorization:
        require_workspace_user(authorization)
        return
    raise HTTPException(status_code=401, detail="A verified customer or workspace session is required.")








def workspace_login(request: WorkspaceLoginRequest):
    user = get_support_user_for_login(request.email)
    if not user or user.get("status") != "Active" or not verify_password(request.password, user.get("password", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    public_user = {key: value for key, value in user.items() if key != "password"}
    token = create_access_token({"sub": str(user["id"]), "email": user["email"], "role": user["role"]})
    return {"access_token": token, "token_type": "bearer", "user": public_user}




















































































































