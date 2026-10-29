import base64
import contextvars
from concurrent.futures import ThreadPoolExecutor
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
    get_project_amenities,
    get_project_offers,
    get_project_payment_plans,
    get_project_typologies,
    get_project_wings,
    get_sellable_projects,
    get_wing_inventory,
    get_wing_typologies,
    resolve_project_from_text,
    get_cs_api_status,
    check_cs_api_contract,
)
from services.internal_api_log_service import (
    begin_data_api_trace,
    end_data_api_trace,
    get_current_data_api_logs,
)
from services.rag_evaluation_service import evaluate_rag_response
from services.vocabulary import AMENITY_TERMS, amenity_expansion

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
    def call_key(call):
        return call.get("endpoint"), tuple(sorted((call.get("params") or {}).items()))

    succeeded = {call_key(call) for call in data_api_calls
                 if call.get("provider") == "Acrobuild CS API" and call.get("status") == "completed"}
    # A failure that a later call to the same endpoint recovered from (e.g. a heuristic that swallowed a
    # timeout, then the shortcut's own fetch succeeded) did not leave the answer without live data.
    failed_live_calls = [
        call for call in data_api_calls
        if call.get("provider") == "Acrobuild CS API" and call.get("status") == "failed"
        and call_key(call) not in succeeded
    ]
    if response_payload.get("unchecked_projects"):
        failed_live_calls = []  # the answer already names the projects it couldn't load; the rest is live
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


from services.action_registry import SiteVisitRequest  # noqa: E402,F401 - re-exported for routers

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
    # True when `issue` is a quick-reply button's value: the reply keeps the conversation's language.
    from_choice: bool = False


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

# Customer words for amenities live in services/vocabulary.py (AMENITY_SYNONYMS), shared with routing.
# Only these words trigger the (one call per project) amenity lookup.
_AMENITY_HINT_RE = re.compile(
    r"(?<![\w-])(" + "|".join(re.escape(t) for t in sorted(AMENITY_TERMS, key=len, reverse=True)) + r")(?![\w-])",
    re.IGNORECASE,
)
_AMENITY_FILLER = {"and", "area", "the", "of", "a", "s"}


def _amenity_words(text):
    words = re.findall(r"[a-z0-9]+", str(text).lower())
    return {w[:-1] if w.endswith("s") and len(w) > 3 else w for w in words} - _AMENITY_FILLER


def requested_amenities(text, amenity_names):
    """Amenity names the customer asked for: every meaningful word of the name appears in their message.
    "swimming pool" matches "Swimming Pool" but not "Baby Swimming Area" or "Pool & Billards"."""
    from services.text_fuzz import correct_words

    vocabulary = ({w for name in amenity_names for w in re.findall(r"[a-z]+", name.lower())}
                  | {t for t in AMENITY_TERMS if " " not in t})
    lowered = correct_words(str(text or "").lower(), vocabulary)  # "swiming pool", "jogin track"
    expanded = amenity_expansion(lowered)  # "tarantal" -> "swimming pool"
    words = _amenity_words(expanded)
    matched = {name for name in amenity_names if _amenity_words(name) and _amenity_words(name) <= words}
    # Keep the most specific: "power backup" matches "Power Backup Lift", not also plain "Lift".
    return sorted(name for name in matched
                  if not any(other != name and _amenity_words(name) < _amenity_words(other) for other in matched))


def _live_payload(answer, title, source_key, choices, excerpt=""):
    """A grounded CS-API answer with quick-reply buttons (the router sets the route)."""
    evidence = {
        "body_text": answer, "category": "AcroBuild property data", "excerpt": excerpt or title,
        "record_kind": "company_api", "score": 100.0, "source_key": source_key, "source_name": "AcroBuild CS API",
        "title": title, "url": "",
    }
    return {
        "agent_mode": "knowledge_retrieval", "answer": answer, "articles": [], "assist_error": "",
        "choices": choices, "confidence_label": "high", "handoff_recommended": False, "knowledge_documents": [],
        "last_synced_at": None, "matched_chunks": [evidence], "model": "", "retrieval_mode": "live_project_records",
        "source_label": "Retrieved AcroBuild project data", "source_status": "live_api",
        "support_base_url": get_support_base_url(), "sync_error": "", "used_llm": False,
    }


_ASK_TEAM = {"label": "Ask our team", "value": "", "action": "handoff"}


def _project_from_request(request, projects):
    """The project named now, else the most recent one the customer named earlier in the chat."""
    project = resolve_project_from_text(projects, str(request.issue or "").strip())
    if project is None:
        history = [str(m.text or "").strip() for m in request.conversation_messages
                   if str(m.sender or "").lower() == "customer" and str(m.text or "").strip()]
        project = next((p for text in reversed(history) if (p := resolve_project_from_text(projects, text))), None)
    return project


def _pick_project_payload(question, projects, topic, value_template):
    names = [str(p.get("projectName", "")).strip() for p in projects if str(p.get("projectName", "")).strip()]
    return _live_payload(question, f"Project selection for {topic}", f"acrobuild-cs-{topic}-project-selection",
                         [{"label": n, "value": value_template.format(name=n)} for n in names],
                         f"{len(names)} projects; project selection required")


_BEST_RE = re.compile(r"\b(best|most|good|top|great|better|luxur\w*|premium|max(?:imum)?|accha|achhe|acche|"
                      r"badhiya|zyada|jyada|sabse)\b", re.IGNORECASE)


def build_grounded_project_amenities_assist(request):
    from services.choice_service import project_choices, single_project_choices

    issue = str(request.issue or "").strip()
    if not _AMENITY_HINT_RE.search(issue):
        return None
    generic = bool(re.search(r"\b(amenit|facilit)", issue, re.IGNORECASE))
    projects = get_company_projects()
    named = resolve_project_from_text(projects, issue)
    catalogue = {str(p.get("projectName", "")).strip(): [a["name"] for a in get_project_amenities(p["id"])]
                 for p in projects if p.get("id") is not None and str(p.get("projectName", "")).strip()}
    wanted = requested_amenities(issue, {name for names in catalogue.values() for name in names})
    if not wanted and not generic:
        return None  # an amenity-sounding word ("ground floor", "fire NOC") that names no amenity
    from services import home_finder
    if not wanted and named is None and (_BEST_RE.search(issue) or home_finder.is_search(issue)
                                         or re.search(r"\d|\bbhk\b|\brk\b", issue, re.IGNORECASE)):
        # "3BHK with the best amenities", "flats in Pune with good facilities": a home search, best-equipped first.
        ranked = build_grounded_home_finder_assist(request, amenities_by_project=catalogue, rank_by_amenities=True)
        if ranked is not None:
            return ranked
    if wanted:
        label = " and ".join(wanted)
        having = [project for project, names in catalogue.items() if set(wanted) <= set(names)]
        if named is not None:
            name = str(named.get("projectName", "")).strip()
            source = f"acrobuild-cs-project-{named['id']}-amenities"
            if name in having:
                return _live_payload(f"Yes, {name} has {label}.", f"{name} amenities", source,
                                     single_project_choices(name))
            others = f" Projects that do: {', '.join(having)}." if having else ""
            return _live_payload(f"{name} doesn't list {label} in the live project data.{others}",
                                 f"{name} amenities", source, project_choices(having) + [_ASK_TEAM])
        if having:
            # "a property with parking" (plus any BHK / budget / place) is a home search limited to these projects.
            found = build_grounded_home_finder_assist(request, wanted, catalogue)
            if found is not None:
                return found
            return _live_payload(f"These projects have {label}:\n" + "\n".join(f"- {p}" for p in having),
                                 f"Projects with {label}", "acrobuild-cs-amenity-filter", project_choices(having),
                                 f"Amenities checked across {len(catalogue)} projects")
        return _live_payload(f"None of our projects list {label} in the live project data.",
                             f"Projects with {label}", "acrobuild-cs-amenity-filter",
                             project_choices(list(catalogue)) + [_ASK_TEAM])
    project = named or _project_from_request(request, projects)
    if project is None:
        return _pick_project_payload("Which project's amenities would you like to see?", projects, "amenities",
                                     "What amenities does {name} have?")
    name = str(project.get("projectName", "")).strip()
    source = f"acrobuild-cs-project-{project['id']}-amenities"
    amenities = get_project_amenities(project["id"])
    if not amenities:
        return _live_payload(f"The live project data doesn't list amenities for {name} yet. Our team can confirm them.",
                             f"{name} amenities", source, single_project_choices(name, skip="amenities") + [_ASK_TEAM])
    names = [a["name"] for a in amenities]
    choices = single_project_choices(name, skip="amenities")
    if _FULL_LIST_RE.search(issue) or len(names) <= 8:
        groups = {}
        for amenity in amenities:
            groups.setdefault(amenity["type"], []).append(amenity["name"])
        answer = f"{name} amenities:\n" + "\n".join(f"{group}: {', '.join(n)}" for group, n in groups.items())
        return _live_payload(answer, f"{name} amenities", source, choices)
    top = ([a for a in _HEADLINE_AMENITIES if a in names] + [a for a in names if a not in _HEADLINE_AMENITIES])[:6]
    answer = f"{name} has {len(names)} amenities, including {', '.join(top)}."
    more = [{"label": f"All {len(names)} amenities", "value": f"Show all amenities of {name}"}]
    return _live_payload(answer, f"{name} amenities", source, more + choices)


_OFFER_RE = re.compile(r"\b(offers?|discounts?|schemes?|deals?)\b", re.IGNORECASE)
_PAYMENT_PLAN_RE = re.compile(
    r"\b(payment (?:plans?|schedules?|terms)|construction linked|milestones?|instal+ments?|booking amount|"
    r"how (?:do|can|should) i pay|pay(?:ment)? in parts)\b", re.IGNORECASE)


def build_grounded_project_offers_assist(request):
    from services.choice_service import single_project_choices

    if not _OFFER_RE.search(str(request.issue or "")):
        return None
    projects = get_company_projects()
    project = _project_from_request(request, projects)
    if project is None:
        return _pick_project_payload("Which project's offers would you like to see?", projects, "offers",
                                     "What offers are available at {name}?")
    name = str(project.get("projectName", "")).strip()
    offers = get_project_offers(project["id"])
    if not offers:
        answer = f"There are no running offers listed for {name} right now."
    else:
        everyone = {"Loan", "Self-Funding", "Investor"}
        shown = offers if _FULL_LIST_RE.search(str(request.issue or "")) else offers[:_SHORT_LIST]
        answer = f"Current offers at {name}:\n" + "\n".join(
            f"- {o['name']}" + ("" if not o["applies_to"] or set(o["applies_to"]) >= everyone
                               else f" (for {', '.join(o['applies_to'])} buyers)")
            for o in shown
        ) + (f"\n...and {len(offers) - len(shown)} more." if len(shown) < len(offers) else "")
        answer += "\nOur team confirms which offer applies."
        if len(shown) < len(offers):
            more = [{"label": f"All {len(offers)} offers", "value": f"Show all offers at {name}"}]
            return _live_payload(answer, f"{name} offers", f"acrobuild-cs-project-{project['id']}-offers",
                                 more + single_project_choices(name, skip="offers"))
    return _live_payload(answer, f"{name} offers", f"acrobuild-cs-project-{project['id']}-offers",
                         single_project_choices(name, skip="offers"))


def build_grounded_project_payment_plan_assist(request):
    from services.choice_service import single_project_choices

    if not _PAYMENT_PLAN_RE.search(str(request.issue or "")):
        return None
    projects = get_company_projects()
    project = _project_from_request(request, projects)
    if project is None:
        return _pick_project_payload("Which project's payment plan would you like to see?", projects,
                                     "payment plan", "What is the payment plan at {name}?")
    name = str(project.get("projectName", "")).strip()
    plans = [plan for plan in get_project_payment_plans(project["id"]) if plan["milestones"]]
    choices = single_project_choices(name, skip="payment plan")
    if not plans:
        answer = f"The live data doesn't list a payment plan for {name} yet. Our team can share it."
    else:
        parts = []
        for plan in plans:
            amount = plan["booking_amount"]
            head = f"{plan['name']} ({plan['type']})" + (
                f": booking amount INR {amount:,.0f}" if isinstance(amount, (int, float)) else "")
            parts.append((head, [m["name"] for m in plan["milestones"]]))
        if _FULL_LIST_RE.search(str(request.issue or "")):
            answer = f"Payment plans at {name}:\n\n" + "\n\n".join(
                head + "\n" + "\n".join(f"- {s}" for s in stages) for head, stages in parts)
        else:  # the API's stage order isn't reliable, so the short answer counts stages instead of quoting a few
            answer = f"Payment plans at {name}:\n" + "\n".join(
                f"- {head}, then {len(stages)} stages linked to construction" for head, stages in parts)
            choices = [{"label": "All payment stages", "value": f"Show all payment plan milestones at {name}"}] + choices
    return _live_payload(answer, f"{name} payment plans", f"acrobuild-cs-project-{project['id']}-payment-plans",
                         choices)


_PRICE_NOTE = "Approx. prices, before taxes and charges. Our team confirms availability and the final cost."
# Lists longer than this show the first few and a button for the rest (answer first, details on request).
_SHORT_LIST = 3
_FULL_LIST_RE = re.compile(r"\b(all|full|complete|every|saare|sabhi|poori|puri)\b", re.IGNORECASE)


def _city_choices(projects):
    cities = sorted({str(p.get("city") or "").strip() for p in projects if str(p.get("city") or "").strip()})
    return [{"label": f"Homes in {city}", "value": f"Show homes in {city}"} for city in cities]


_CONTACT_SUBJECT_RE = re.compile(r"\b(office|company|your|you|acrobuild|gbk|head ?office|customer care|helpline|"
                                 r"sales team|support team|builder|developer)\b", re.IGNORECASE)
_CONTACT_TOPIC_RE = re.compile(r"\b(location|contact|phone|number|call|email|e-mail|mail|reach|website|whatsapp|"
                               r"visit you|meet you)\b", re.IGNORECASE)


def build_grounded_company_contact_assist(request):
    """ "What is your office address?", "customer care number", "how do I contact you": from the company
    record. A question about one project's location is left to the project answers."""
    issue = str(request.issue or "").strip()
    if not (_CONTACT_SUBJECT_RE.search(issue) and _CONTACT_TOPIC_RE.search(issue)):
        return None
    if resolve_project_from_text(get_company_projects(), issue) is not None:
        return None
    from services.acrobuild_company_service import _cached_request

    company = _cached_request("/api/cs/company")
    if not isinstance(company, dict) or not company:
        return None
    name = str(company.get("businessName") or company.get("companyName") or "Acrobuild").strip()
    lines = [f"{name} office:"]
    for label, key in (("Address", "address"), ("Phone", "phoneNo"), ("Email", "contactEmail"),
                       ("Website", "websiteUrl")):
        value = str(company.get(key) or "").strip()
        if value:
            lines.append(f"- {label}: {value}")
    return _live_payload("\n".join(lines), "Company contact details", "acrobuild-cs-company",
                         [{"label": "Book a site visit", "value": "I want to book a site visit"}, _ASK_TEAM])


def _locality_city(place, projects_in_place):
    """The city a named locality belongs to: from the locality list, else from our projects there.
    "" when `place` is itself a city or unknown."""
    from services import home_finder

    if not place or place in home_finder.KNOWN_CITIES:
        return ""
    cities = {str(p.get("city") or "").strip().lower() for p in projects_in_place if p.get("city")}
    return home_finder.LOCALITY_CITY.get(place) or (cities.pop() if len(cities) == 1 else "")


def _any_homes(projects):
    """Whether any of these projects has wings; a project we can't check counts as having homes."""
    for project in projects:
        try:
            if get_project_wings(project["id"]):
                return True
        except RuntimeError:
            return True
    return False


def _project_listing(project):
    """Live wings, home types (by wing) and listed-flat counts (by (wing id, home type id)) for one project.

    The CS API lists flats under home-type ids their wing doesn't carry (159 flats in Prime wing A), so a
    flat's home type is found by id anywhere in the project, else by name, and attached to the flat's wing."""
    wings = get_project_wings(project["id"])
    typologies_by_wing, available = {}, {}
    project_typologies = get_project_typologies(project["id"]) if wings else []  # one call; rows carry wingId
    for typology in project_typologies:
        typologies_by_wing.setdefault(typology.get("wingId"), []).append(typology)
    by_id = {t["id"]: t for t in project_typologies}
    by_name = {(t.get("typologyName") or "").lower(): t for t in project_typologies if t.get("typologyName")}
    for wing in wings:
        listed = typologies_by_wing.setdefault(wing["id"], [])
        listed_ids = {t["id"] for t in listed}
        for unit in get_wing_inventory(wing["id"], available_only=True):
            typology = by_id.get(unit.get("typologyId")) or by_name.get((unit.get("typologyName") or "").lower())
            if typology is None:
                continue  # no size or rate anywhere for this flat: it can't be described or priced
            if typology["id"] not in listed_ids:
                listed.append(typology)
                listed_ids.add(typology["id"])
            key = (wing["id"], typology["id"])
            available[key] = available.get(key, 0) + 1
    return wings, typologies_by_wing, available


# What a family looks for first when comparing projects; the rest are counted, not listed.
_HEADLINE_AMENITIES = ("Swimming Pool", "Gym", "Community House", "Children's Playing Area", "Jogging Track",
                       "Park", "Power Backup Lift", "Security Personnel", "Parking", "Party Lawn")


def _amenity_highlights(names):
    if not names:
        return " · no amenities listed"
    top = ([a for a in _HEADLINE_AMENITIES if a in names] + sorted(set(names) - set(_HEADLINE_AMENITIES)))[:3]
    return f" · {len(names)} amenities incl. {', '.join(top)}"


def build_grounded_home_finder_assist(request, required_amenities=None, amenities_by_project=None,
                                      rank_by_amenities=False):
    """ "2BHK under 50 lakh in Pune", "2000 sqft", "ready to move", "property in Mumbai": matching homes per
    project with estimated prices and buttons, the closest options when nothing fits, never a dead end.
    With `required_amenities` ("flat with parking"), only projects listing all of them are searched.
    With `rank_by_amenities` ("3BHK with the best amenities"), projects with the most amenities come first."""
    from services import home_finder
    from services.choice_service import project_choices

    issue = str(request.issue or "").strip()
    if not required_amenities and not (home_finder.is_search(issue) or re.search(r"\d", issue)):
        return None  # cheap exit before any CS API call: this also runs on general-chat turns ("hi")
    projects = [p for p in get_company_projects() if isinstance(p, dict) and p.get("id") is not None]
    if resolve_project_from_text(projects, issue) is not None:
        return None  # a question about one named project belongs to the project answers
    places = {str(p.get(k) or "").strip() for p in projects for k in ("city", "locality") if p.get(k)}
    criteria = home_finder.parse_criteria(issue, places)
    # A size, BHK, budget or "ready to move" is a search on its own ("2000sqft best locality"); a bare place
    # needs a search word ("property in Pune"), so "office address in Pune" is left to other answers.
    if not (required_amenities or rank_by_amenities or criteria.bhk is not None or criteria.size
            or criteria.budget_max or criteria.ready or (criteria.place and home_finder.is_search(issue))):
        return None
    our_cities = sorted({str(p.get("city") or "").strip() for p in projects if p.get("city")})
    in_place = [p for p in projects if home_finder.project_in_place(p, criteria.place)]
    if required_amenities:
        in_place = [p for p in in_place
                    if set(required_amenities) <= set((amenities_by_project or {}).get(str(p.get("projectName", "")).strip(), []))]
        if not in_place:
            where = f" in {criteria.place.title()}" if criteria.place else ""
            answer = f"None of our projects{where} list {' and '.join(required_amenities)} in the live project data."
            return _live_payload(answer, "Amenity search", "acrobuild-cs-home-finder",
                                 _city_choices(projects) + [_ASK_TEAM])
    # Area-first: a locality with no homes of ours ("flat in Magarpatta", or Baner where the only project has
    # no homes listed) falls back to the rest of its city instead of a dead end.
    fallback_note = ""
    city = _locality_city(criteria.place, in_place)
    if city and city in {c.lower() for c in our_cities} and not _any_homes(in_place):
        fallback_note = (f"We don't have homes listed in {criteria.place.title()} right now. "
                         f"Here are our homes elsewhere in {city.title()}.\n\n")
        criteria.place, criteria.places = city, (city,)
        in_place = [p for p in projects if home_finder.project_in_place(p, city)]
    if not in_place:
        answer = (f"We don't have projects in {criteria.place.title()} right now. "
                  f"Our homes are in {', '.join(our_cities)}. Would you like to see those?")
        return _live_payload(answer, "Projects by city", "acrobuild-cs-home-finder", _city_choices(projects))

    # Projects load in parallel (a city search touches ~40 endpoints). Each worker runs in a copy of this
    # turn's context so its calls land in the same data-API trace the live-data guard checks.
    def load(project):
        try:
            return project["id"], _project_listing(project)
        except RuntimeError:  # one project's data failing to load must not sink the answer for the others
            return project["id"], None

    with ThreadPoolExecutor(max_workers=4) as pool:  # the CS API stalls under bursts; 4 keeps it responsive
        loaded = dict(pool.map(lambda job: job[0].run(load, job[1]),
                               [(contextvars.copy_context(), p) for p in in_place]))
    unchecked = [str(p.get("projectName", "")).strip() for p in in_place if loaded.get(p["id"]) is None]
    listings = {pid: listing for pid, listing in loaded.items() if listing is not None}
    searchable = [p for p in in_place if p["id"] in listings]

    def search(c):
        found = [home_finder.project_matches(p, *listings[p["id"]], c) for p in searchable]
        return [m for m in found if m]

    matches, relaxed = search(criteria), ""
    if not matches:
        for label, looser in home_finder.relaxations(criteria):
            matches, relaxed = search(looser), label
            if matches:
                break
    no_homes = [str(p.get("projectName", "")).strip() for p in searchable if not listings[p["id"]][0]]
    wanted = criteria.describe() + (f" with {' and '.join(required_amenities)}" if required_amenities else "")
    if not matches:
        answer = f"I couldn't find {wanted} in our live listings right now."
        choices = _city_choices(projects)
    else:
        if criteria.size and relaxed:
            matches.sort(key=lambda m: abs((m["area_min"] + m["area_max"]) / 2 - criteria.size))
        elif relaxed == "budget":
            matches.sort(key=lambda m: m["price_min"] or 0)
        amenities = amenities_by_project or {}
        if rank_by_amenities:
            matches.sort(key=lambda m: len(amenities.get(m["name"], [])), reverse=True)  # stable: ties keep order
            wanted += ", best amenities first"
        head = fallback_note + (f"Nothing matches {wanted} exactly. The closest options ({relaxed} relaxed):"
                                if relaxed else f"Here are {wanted}:")
        budget_set = bool(criteria.budget_max) and relaxed != "budget"
        answer = head + "\n" + "\n".join(
            f"- {home_finder.describe_match(m, budget_set)}"
            + (_amenity_highlights(amenities.get(m["name"], [])) if rank_by_amenities else "")
            for m in matches[:5])
        answer += "\n\n" + _PRICE_NOTE
        choices = project_choices([m["name"] for m in matches[:5]])
    if unchecked:
        answer += f"\n\nI couldn't load {', '.join(unchecked)} just now; please ask again in a moment."
    payload = _live_payload(answer, f"Search: {wanted}", "acrobuild-cs-home-finder", choices,
                            f"{len(searchable)} projects checked")
    payload["unchecked_projects"] = unchecked  # disclosed above, so the live-data guard may accept the rest
    return payload


_DETAILS_RE = re.compile(
    r"\b(size|sq\.? ?ft|sqft|square|bhk|rk|configurations?|types?|wing|floors?|storey|storeys|possession|"
    r"price|availab\w*|flat|how many|details|overview|carpet|about|info|information|rera)\b", re.IGNORECASE)


def build_grounded_project_details_assist(request):
    """One project's sizes, BHK types, wings, floors, possession, prices and availability ("sqft of 2bhk in
    Prime", "how many wing in Paradise", "price of Myspace"), from live data."""
    from services import home_finder
    from services.choice_service import single_project_choices

    issue = str(request.issue or "").strip()
    if not _DETAILS_RE.search(issue):
        return None
    projects = [p for p in get_company_projects() if isinstance(p, dict) and p.get("id") is not None]
    project = resolve_project_from_text(projects, issue)
    if project is None:
        places = {str(p.get(k) or "").strip() for p in projects for k in ("city", "locality") if p.get(k)}
        if home_finder.parse_criteria(issue, places).place:
            return None  # "2bhk price in Pune" is a search across projects, not a follow-up
        project = _project_from_request(request, projects)
    if project is None:
        return None
    name = str(project.get("projectName", "")).strip()
    bhk = home_finder.parse_criteria(issue, set()).bhks or None
    wings, typologies_by_wing, available = _project_listing(project)
    focus = _detail_focus(issue)
    wing_lines, home_lines = home_finder.project_summary(project, wings, typologies_by_wing, available, bhk,
                                                         fields=_FOCUS_FIELDS.get(focus, ("size", "price")))
    place = ", ".join(p for p in (project.get("locality"), project.get("city")) if p)
    title = f"{name}{f' ({place})' if place else ''}"
    source = f"acrobuild-cs-project-{project['id']}-details"
    choices = single_project_choices(name, question=issue)
    if not wings:
        answer = f"{title} has no homes listed yet. Our team can share the launch details."
        return _live_payload(answer, f"{name} details", source, choices + [_ASK_TEAM])
    rera = str(project.get("reraNo") or "").strip()
    # Answer what was asked, nothing more; the buttons lead to the rest.
    if focus == "rera":
        answer = (f"{name} RERA number: {rera}." if rera
                  else f"The live data has no RERA number for {name}; our team can share it.")
        return _live_payload(answer, f"{name} details", source, choices)
    if focus in ("wing", "possession"):
        return _live_payload(f"{title} wings:\n" + "\n".join(f"- {w}" for w in wing_lines),
                             f"{name} details", source, choices)
    if not home_lines:
        kinds = " or ".join("1 RK" if k == 0.5 else f"{k:g}BHK" for k in bhk) if bhk else "homes"
        return _live_payload(f"No {kinds} are listed at {name} right now.", f"{name} details", source, choices)
    heading = {"price": f"{name} prices:", "size": f"{name} sizes:"}.get(focus, f"{title}:")
    lines = [heading] + [f"- {line}" for line in home_lines]
    if focus == "general":
        lines += ["Wings: " + "; ".join(wing_lines)] + ([f"RERA: {rera}"] if rera else [])
    if focus != "size":
        lines += ["", _PRICE_NOTE]
    return _live_payload("\n".join(lines), f"{name} details", source, choices)


# What each kind of question needs from a project's BHK lines.
_FOCUS_FIELDS = {"price": ("price",), "size": ("size", "carpet"), "general": ("size", "price")}
_FOCUS_RES = (("rera", r"\brera\b"), ("wing", r"\b(wings?|floors?|storeys?|towers?)\b"),
              ("possession", r"\b(possession|ready to move|handover)\b"),
              ("size", r"\b(size|sq\.? ?ft|sqft|square|carpet|area)\b"), ("price", r"\b(price|cost|budget|rate)\b"))


def _detail_focus(issue):
    """The one thing a details question asks about, or "general" for none or several ("details of Prime")."""
    found = [name for name, pattern in _FOCUS_RES if re.search(pattern, issue, re.IGNORECASE)]
    return found[0] if len(found) == 1 else "general"


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























































































































