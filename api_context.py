import base64
from contextlib import asynccontextmanager
import json
import logging
import os
import re
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
    get_project_wings,
    get_wing_inventory,
    get_wing_typologies,
    resolve_project_from_text,
    get_cs_api_status,
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
from qwen import warm_qwen_model_async
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
    if route == "general" or (route != "property" and not is_property_support_message(issue)):
        return response_payload
    failed_live_calls = [
        call for call in data_api_calls
        if call.get("provider") == "Acrobuild CS API" and call.get("status") == "failed"
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

    if completed_live_calls and not failed_live_calls and not non_live_calls and not ungrounded_answer:
        response_payload["articles"] = []
        response_payload["knowledge_documents"] = []
        response_payload["matched_chunks"] = company_api_chunks
        response_payload["source_label"] = "Live Acrobuild CS API"
        response_payload["source_status"] = "live_api"
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
        "answer": (
            f"Live property data is unavailable: {reason}. "
            "I did not use cached responses, server memory, snapshots, local knowledge, or predefined data. "
            "Please try again shortly, or I can connect you with the sales team."
        ),
        "articles": [],
        "confidence_label": "low",
        "handoff_recommended": True,
        "knowledge_documents": [],
        "matched_chunks": [],
        "retrieval_mode": "live_api_error",
        "source_label": "Acrobuild CS API",
        "source_status": source_status,
        "used_llm": False,
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
        warm_qwen_model_async()
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

    projects = get_company_projects()
    customer_history = [str(message.text or "").strip() for message in request.conversation_messages if str(message.sender or "").lower() == "customer" and str(message.text or "").strip()]
    selected_project = resolve_project_from_text(projects, issue)
    if selected_project is None:
        selected_project = next((resolved for text in reversed(customer_history) if (resolved := resolve_project_from_text(projects, text)) is not None), None)
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

    projects = get_company_projects()
    customer_history = [str(message.text or "").strip() for message in request.conversation_messages if str(message.sender or "").lower() == "customer" and str(message.text or "").strip()]
    selected_project = resolve_project_from_text(projects, issue)
    if selected_project is None:
        selected_project = next((resolved for text in reversed(customer_history) if (resolved := resolve_project_from_text(projects, text)) is not None), None)
    if selected_project is None:
        answer = (
            "Which project would you like me to check? Share the project name, "
            "and I'll look up its confirmed amenities in the available project data."
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
        }

    project_name = str(selected_project.get("projectName", "Project")).strip()
    wings = get_project_wings(selected_project["id"])
    amenity_values = []
    for wing in wings:
        for typology in get_wing_typologies(wing["id"]):
            value = typology.get("unitAmenities")
            if isinstance(value, list):
                amenity_values.extend(
                    str(item).strip() for item in value if str(item).strip()
                )
            elif str(value or "").strip():
                amenity_values.extend(
                    item.strip()
                    for item in re.split(r"[,;|\n]", str(value))
                    if item.strip()
                )
    amenities = list(dict.fromkeys(amenity_values))
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

    evidence = {
        "body_text": answer,
        "category": "AcroBuild property data",
        "excerpt": f"Amenity fields checked across {len(wings)} project wings",
        "project": selected_project,
        "record_kind": "company_api",
        "score": 100.0,
        "source_key": f"acrobuild-cs-project-{selected_project['id']}-amenities",
        "source_name": "AcroBuild CS API",
        "title": f"{project_name} amenities",
        "url": "",
        "wings_checked": len(wings),
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
    if not asks_location:
        return None

    projects = get_company_projects()
    if not projects:
        return None

    selected_project = resolve_project_from_text(projects, issue)
    if selected_project is None:
        selected_project = resolve_project_from_text(projects, prior_customer_text)
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
            return None
        requested_location = " ".join(
            location_match.group(1).strip().split()
        )
        ignored_trailing_words = ("project", "projects", "property", "properties")
        for trailing_word in ignored_trailing_words:
            suffix = f" {trailing_word}"
            if requested_location.endswith(suffix):
                requested_location = requested_location[:-len(suffix)].strip()
        if not requested_location:
            return None

        matching_projects = []
        for project in projects:
            location_text = " ".join(
                str(project.get(key, "") or "")
                for key in ("address", "locality", "city", "location", "zipcode")
            ).lower()
            if requested_location in location_text:
                matching_projects.append(project)

        location_label = requested_location.title()
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























































































































