import base64
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query
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
)
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

# -----------------------------------
# INIT DATABASE
# -----------------------------------

initialize_database()


def _enforce_live_property_data(response_payload, issue, data_api_calls):
    if not is_property_support_message(issue):
        return response_payload
    failed_live_calls = [
        call for call in data_api_calls
        if call.get("provider") == "Acrobuild CS API" and call.get("status") == "failed"
    ]
    non_live_calls = [
        call for call in data_api_calls
        if call.get("cache_hit") or "snapshot" in str(call.get("provider", "")).lower()
    ]
    completed_live_calls = [
        call for call in data_api_calls
        if call.get("provider") == "Acrobuild CS API" and call.get("status") == "completed"
        and not call.get("cache_hit")
    ]
    if completed_live_calls and not failed_live_calls and not non_live_calls:
        response_payload["articles"] = []
        response_payload["knowledge_documents"] = []
        response_payload["matched_chunks"] = [
            chunk for chunk in response_payload.get("matched_chunks", [])
            if chunk.get("record_kind") == "company_api"
        ]
        response_payload["source_label"] = "Live Acrobuild CS API"
        response_payload["source_status"] = "live_api"
        return response_payload

    errors = list(dict.fromkeys(
        str(call.get("error", "")).strip() for call in failed_live_calls if str(call.get("error", "")).strip()
    ))
    reason = errors[0] if errors else "No successful live CS API response was available for this request."
    response_payload.update({
        "agent_mode": "live_data_error",
        "answer": (
            f"Live property data is unavailable: {reason} "
            "I did not use cached responses, server memory, snapshots, local knowledge, or predefined data. "
            "Please try again when the CS API is available."
        ),
        "articles": [],
        "confidence_label": "low",
        "handoff_recommended": True,
        "knowledge_documents": [],
        "matched_chunks": [],
        "retrieval_mode": "live_api_error",
        "source_label": "Acrobuild CS API",
        "source_status": "failed",
        "used_llm": False,
    })
    return response_payload

# -----------------------------------
# FASTAPI
# -----------------------------------

api = FastAPI()

api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@api.on_event("startup")
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

class TicketRequest(BaseModel):
    issue: str
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


class UpdateTicketAgentRequest(BaseModel):
    ticket_id: str = ""
    agent_name: str


class UpdateTicketStatusRequest(BaseModel):
    ticket_id: str
    status: str


class TicketTagUpdateRequest(BaseModel):
    tag_ids: list[int]


class AdminTicketMessageRequest(BaseModel):
    message: str
    sender: str = "admin"


class AdminTicketAttachmentRequest(BaseModel):
    content_base64: str
    mime_type: str = ""
    name: str = "attachment"


class AdminTicketReplyRequest(BaseModel):
    applied_macro_id: int | None = None
    attachments: list[AdminTicketAttachmentRequest] = []
    message: str = ""
    sender: str = "admin"


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
    role: str = "agent"
    status: str = "Invited"
    team: str = "Support"


class SupportUserUpdateRequest(BaseModel):
    name: str
    role: str
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
    text: str = ""


class SupportAssistRequest(BaseModel):
    article_hint_url: str = ""
    business_hours_tag: str = ""
    conversation_id: str = ""
    conversation_messages: list[SupportAssistConversationMessageRequest] = Field(default_factory=list)
    customer_email: str = ""
    customer_name: str = ""
    issue: str
    issue_type: str = ""
    limit: int = 3
    prefer_fast_response: bool = False
    prefer_qwen_response: bool = True


class VoiceSynthesisRequest(BaseModel):
    text: str
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
    content_base64: str
    mime_type: str = ""
    name: str


class KnowledgeDocumentUploadRequest(BaseModel):
    category: str = "Knowledge"
    files: list[KnowledgeUploadFileRequest]
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
            file_bytes = base64.b64decode(raw_content)
        except Exception as error:
            raise HTTPException(status_code=400, detail="Invalid attachment payload.") from error

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

@api.get("/")
def home():

    return {
        "message": "AI Customer Support Backend Running"
    }


@api.get("/api/health")
def api_health():

    return {
        "status": "ok",
    }


@api.get("/api/local-product-feeds")
def get_local_product_feeds_api():

    feed_summaries = []

    for feed_key in (
        "macros",
        "soulara",
    ):
        try:
            summary = (
                get_local_product_feed_summary(
                    feed_key
                )
            )
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=str(error),
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail=str(error),
            ) from error
        except Exception as error:
            raise HTTPException(
                status_code=500,
                detail=str(error),
            ) from error

        feed_summaries.append(
            {
                "csv_url": f"/local-data/products/{feed_key}.csv",
                "html_url": f"/local-data/products/{feed_key}",
                "key": feed_key,
                "published_count": summary[
                    "published_count"
                ],
                "total_count": summary[
                    "total_count"
                ],
            }
        )

    return {
        "feeds": feed_summaries,
    }


@api.get(
    "/local-data/products/{feed_key}.csv"
)
def get_local_product_feed_csv_api(
    feed_key: str,
):

    try:
        csv_text = read_local_product_feed_csv(
            feed_key
        )
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error

    return Response(
        content=csv_text,
        headers={
            "Content-Disposition": (
                f'inline; filename="{feed_key}.csv"'
            )
        },
        media_type="text/csv",
    )


@api.get(
    "/local-data/products/{feed_key}"
)
def get_local_product_feed_html_api(
    feed_key: str,
):

    try:
        html_text = build_local_product_feed_html(
            feed_key
        )
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error

    return HTMLResponse(
        content=html_text
    )

# -----------------------------------

@api.post("/create_ticket")
def create_ticket(request: TicketRequest):

    result = run_workflow(
        request.issue,
        request.customer_email
    )

    return result


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


@api.get("/api/property-flow/projects")
def property_flow_projects():
    return _cs_api_response(get_company_projects, "Browse live projects")


@api.get("/api/property-flow/projects/{project_id}/wings")
def property_flow_wings(project_id: int):
    return _cs_api_response(
        lambda: get_project_wings(project_id),
        f"Load wings for project {project_id}",
    )


@api.get("/api/property-flow/wings/{wing_id}/typologies")
def property_flow_typologies(wing_id: int):
    return _cs_api_response(
        lambda: get_wing_typologies(wing_id),
        f"Load pricing for wing {wing_id}",
    )


@api.get("/api/property-flow/wings/{wing_id}/inventory")
def property_flow_inventory(wing_id: int, available_only: bool = True):
    return _cs_api_response(
        lambda: get_wing_inventory(wing_id, available_only),
        f"Load available flats for wing {wing_id}",
    )


@api.post("/api/site-visits")
def create_site_visit(request: SiteVisitRequest):
    required_values = {
        "Name": request.customer_name,
        "Email": request.customer_email,
        "Phone": request.customer_phone,
        "Project": request.project_name,
        "Preferred date": request.preferred_date,
        "Preferred time": request.preferred_time,
    }
    missing = [label for label, value in required_values.items() if not str(value or "").strip()]
    if missing:
        raise HTTPException(status_code=400, detail=f"Required: {', '.join(missing)}")

    issue_lines = [
        "Site visit booking request",
        f"Customer name: {request.customer_name.strip()}",
        f"Phone: {request.customer_phone.strip()}",
        f"Project: {request.project_name.strip()}",
        f"Preferred date: {request.preferred_date.strip()}",
        f"Preferred time: {request.preferred_time.strip()}",
    ]
    if request.wing_name.strip():
        issue_lines.append(f"Wing: {request.wing_name.strip()}")
    if request.typology_name.strip():
        issue_lines.append(f"Home type: {request.typology_name.strip()}")
    if request.unit_number.strip():
        issue_lines.append(f"Unit: {request.unit_number.strip()}")
    if request.notes.strip():
        issue_lines.append(f"Notes: {request.notes.strip()}")

    return run_workflow("\n".join(issue_lines), request.customer_email.strip())

@api.post("/api/support/assist")
def get_support_assist(request: SupportAssistRequest):
    cleaned_issue = str(request.issue or "").strip()
    if not cleaned_issue:
        raise HTTPException(status_code=400, detail="Issue is required.")

    clear_assist_response_cache()
    trace_token = begin_data_api_trace(request.conversation_id, cleaned_issue)
    try:
        response_payload = (
            build_grounded_site_visit_document_assist(request)
            or build_grounded_project_amenities_assist(request)
            or build_grounded_project_location_assist(request)
        )
        if response_payload is not None:
            data_api_calls = get_current_data_api_logs()
            response_payload = _enforce_live_property_data(response_payload, cleaned_issue, data_api_calls)
            response_payload["data_api_calls"] = data_api_calls
            response_payload["rag_evaluation"] = evaluate_rag_response(
                cleaned_issue, response_payload, data_api_calls,
            )
            return response_payload
        response_payload = run_support_orchestration(
            issue=cleaned_issue,
            conversation_id=request.conversation_id,
            customer_name=request.customer_name,
            customer_email=request.customer_email,
            business_hours_tag=request.business_hours_tag,
            issue_type=request.issue_type,
            article_hint_url=request.article_hint_url,
            conversation_messages=[message.model_dump() for message in request.conversation_messages if str(message.text or "").strip()],
            limit=min(max(int(request.limit or 3), 1), 6),
            prefer_fast_response=bool(request.prefer_fast_response),
            prefer_qwen_response=bool(request.prefer_qwen_response),
        )
        if not answer_matches_response_language(response_payload.get("answer"), cleaned_issue):
            response_payload["answer"] = localize_ai_answer(response_payload.get("answer"), cleaned_issue)
        data_api_calls = get_current_data_api_logs()
        response_payload = _enforce_live_property_data(response_payload, cleaned_issue, data_api_calls)
        response_payload["data_api_calls"] = data_api_calls
        response_payload["rag_evaluation"] = evaluate_rag_response(cleaned_issue, response_payload, data_api_calls)
        return response_payload
    finally:
        end_data_api_trace(trace_token)

@api.post("/api/support/voice/synthesize")
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


@api.post("/api/support/assist/stream")
def stream_support_assist(request: SupportAssistRequest):
    cleaned_issue = str(request.issue or "").strip()
    if not cleaned_issue:
        raise HTTPException(status_code=400, detail="Issue is required.")

    def event_stream():
        clear_assist_response_cache()
        trace_token = begin_data_api_trace(request.conversation_id, cleaned_issue)
        try:
            response_payload = (
                build_grounded_site_visit_document_assist(request)
            or build_grounded_project_amenities_assist(request)
                or build_grounded_project_location_assist(request)
            )
            if response_payload is not None:
                data_api_calls = get_current_data_api_logs()
                response_payload = _enforce_live_property_data(response_payload, cleaned_issue, data_api_calls)
                response_payload["data_api_calls"] = data_api_calls
                response_payload["rag_evaluation"] = evaluate_rag_response(
                    cleaned_issue, response_payload, data_api_calls,
                )
                yield json.dumps({
                    "text": response_payload["answer"], "type": "delta",
                }, ensure_ascii=True) + "\n"
                yield json.dumps({
                    "response": response_payload, "type": "done",
                }, ensure_ascii=True) + "\n"
                return
            property_events = []
            property_request = is_property_support_message(cleaned_issue)
            for event in stream_support_orchestration_events(
                issue=cleaned_issue,
                conversation_id=request.conversation_id,
                customer_name=request.customer_name,
                customer_email=request.customer_email,
                business_hours_tag=request.business_hours_tag,
                issue_type=request.issue_type,
                article_hint_url=request.article_hint_url,
                conversation_messages=[message.model_dump() for message in request.conversation_messages if str(message.text or "").strip()],
                limit=min(max(int(request.limit or 3), 1), 6),
                prefer_fast_response=bool(request.prefer_fast_response),
                prefer_qwen_response=bool(request.prefer_qwen_response),
            ):
                if event.get("type") == "done" and isinstance(event.get("response"), dict):
                    response_payload = event["response"]
                    if not answer_matches_response_language(response_payload.get("answer"), cleaned_issue):
                        response_payload["answer"] = localize_ai_answer(response_payload.get("answer"), cleaned_issue)
                    data_api_calls = get_current_data_api_logs()
                    response_payload = _enforce_live_property_data(response_payload, cleaned_issue, data_api_calls)
                    response_payload["data_api_calls"] = data_api_calls
                    response_payload["rag_evaluation"] = evaluate_rag_response(cleaned_issue, response_payload, data_api_calls)
                    event["response"] = response_payload
                if property_request:
                    property_events.append(event)
                else:
                    yield json.dumps(event, ensure_ascii=True) + "\n"
            if property_request:
                done_event = next((event for event in reversed(property_events) if event.get("type") == "done"), None)
                if done_event and isinstance(done_event.get("response"), dict):
                    final_answer = str(done_event["response"].get("answer", ""))
                    yield json.dumps({"text": final_answer, "type": "delta"}, ensure_ascii=True) + "\n"
                    yield json.dumps(done_event, ensure_ascii=True) + "\n"
        except Exception as error:
            yield json.dumps({
                "response": {
                    "agent_mode": "fallback",
                    "answer": "I hit an internal error while generating the reply. Please try again or send this to the support team.",
                    "articles": [], "assist_error": str(error), "confidence_label": "low",
                    "handoff_recommended": True, "knowledge_documents": [], "last_synced_at": None,
                    "matched_chunks": [], "model": "", "retrieval_mode": "empty",
                    "source_label": "Streaming fallback", "source_status": "fallback",
                    "support_base_url": get_support_base_url(), "sync_error": "", "used_llm": False,
                    "data_api_calls": get_current_data_api_logs(),
                },
                "type": "done",
            }, ensure_ascii=True) + "\n"
        finally:
            end_data_api_trace(trace_token)

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")

@api.get("/customer")
def get_customer(email: str = Query(...), api_base_url: str | None = Query(None)):
    del api_base_url
    normalized_email = str(email or "").strip().lower()
    matching_tickets = [
        ticket
        for ticket in get_all_tickets()
        if str(ticket.get("customer_email", "")).strip().lower() == normalized_email
    ]
    return {
        "customer": {
            "email": normalized_email,
            "name": normalized_email.split("@", 1)[0].replace(".", " ").replace("_", " ").title(),
            "total_orders": len(matching_tickets),
            "total_spent": 0,
            "source": "acrobuild_support",
        },
        "orders": [
            {
                "id": ticket.get("ticket_id"),
                "order_number": ticket.get("ticket_id"),
                "status": ticket.get("status", "Open"),
                "total": 0,
                "created_at": ticket.get("created_at", ""),
                "issue": ticket.get("issue", ""),
                "project_type": ticket.get("issue_type", "Support"),
            }
            for ticket in matching_tickets
        ],
        "subscriptions": [],
        "addresses": [],
        "source_status": "local_acrobuild_support",
    }


@api.post("/auth/otp/request")
def request_otp(request: OtpRequest):

    try:
        delivery = request_email_otp(request.email)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return {
        "message": "Verification code sent.",
        **delivery,
    }


@api.post("/auth/otp/verify")
def verify_otp(request: OtpVerifyRequest):

    try:
        verification = verify_email_otp(
            request.email,
            request.code,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "message": "Email verified.",
        **verification,
    }


@api.get("/customer/verified")
def get_verified_customer(
    email: str = Query(...),
    access_token: str = Query(...),
    api_base_url: str | None = Query(None),
):

    if not validate_email_access_token(
        email,
        access_token,
    ):
        raise HTTPException(
            status_code=401,
            detail="Verification expired. Request a new code.",
        )

    return get_customer(
        email=email,
        api_base_url=api_base_url,
    )

@api.get("/orders")
def get_orders(email: str = Query(...), api_base_url: str | None = Query(None)):
    del api_base_url
    return {"orders": get_customer(email=email).get("orders", [])}


@api.post("/ticket/message")
def add_ticket_message(request: TicketMessageRequest):

    ticket = get_ticket(request.ticket_id)

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message is required.")

    save_message(
        ticket_id=request.ticket_id,
        sender="customer",
        message=request.message.strip(),
    )

    return {
        "ticket_id": request.ticket_id,
        "status": "saved",
    }


@api.post("/order/refund")
def refund_order(request: RefundRequest):

    return {
        "message": "Refund request received",
        "order_number": request.order_number,
        "status": "submitted",
    }


@api.post("/subscription/cancel")
def cancel_subscription(request: SubscriptionCancelRequest):

    return {
        "message": "Subscription cancellation received",
        "subscription_id": request.subscription_id,
        "status": "submitted",
    }


@api.get("/admin/all-tickets")
def get_admin_tickets():

    try:
        return {
            "tickets": get_all_tickets()
        }

    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@api.put("/admin/tickets/{ticket_id}/assign")
def assign_ticket_to_agent(ticket_id: str, request: UpdateTicketAgentRequest):

    try:
        ticket = get_ticket(ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found.")

        update_ticket_agent(ticket_id, request.agent_name)

        return {
            "ticket_id": ticket_id,
            "assigned_agent": request.agent_name,
            "status": "updated"
        }

    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@api.put("/admin/tickets/{ticket_id}/status")
def update_ticket_status_endpoint(ticket_id: str, request: UpdateTicketStatusRequest):

    try:
        ticket = get_ticket(ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found.")

        update_ticket_status(ticket_id, request.status)

        return {
            "ticket_id": ticket_id,
            "status": request.status,
            "updated": "success"
        }

    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@api.get("/api/admin/tickets")
def get_admin_tickets_api():

    return {
        "tickets": get_all_tickets(),
    }


@api.get("/api/admin/users")
@api.get("/admin/users")
def get_admin_users_api():

    return {
        "users": get_support_users(),
    }


@api.post("/api/admin/users")
@api.post("/admin/users")
def create_admin_user_api(request: SupportUserCreateRequest):

    try:
        user = create_support_user(
            name=request.name,
            email=request.email,
            role=request.role,
            team=request.team,
            status=request.status,
        )
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "user": user,
    }


@api.put("/api/admin/users/{user_id}")
@api.put("/admin/users/{user_id}")
def update_admin_user_api(user_id: int, request: SupportUserUpdateRequest):

    existing_user = get_support_user(user_id)

    if not existing_user:
        raise HTTPException(status_code=404, detail="User not found.")

    user = update_support_user(
        user_id=user_id,
        name=request.name,
        role=request.role,
        team=request.team,
        status=request.status,
    )

    return {
        "user": user,
    }


@api.get("/api/admin/articles")
@api.get("/admin/articles")
def get_admin_articles_api():

    return {
        "articles": get_support_articles(),
    }


@api.post("/api/admin/articles")
@api.post("/admin/articles")
def create_admin_article_api(request: SupportArticleCreateRequest):

    try:
        article = create_support_article(
            title=request.title,
            category=request.category,
            status=request.status,
            summary=request.summary,
            body=request.body,
            keywords=request.keywords,
            url=request.url,
        )
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    refresh_support_assist_state()

    return {
        "article": article,
    }


@api.put("/api/admin/articles/{article_id}")
@api.put("/admin/articles/{article_id}")
def update_admin_article_api(article_id: int, request: SupportArticleUpdateRequest):

    existing_article = get_support_article(article_id)

    if not existing_article:
        raise HTTPException(status_code=404, detail="Article not found.")

    article = update_support_article(
        article_id=article_id,
        title=request.title,
        category=request.category,
        status=request.status,
        summary=request.summary,
        body=request.body,
        keywords=request.keywords,
        url=request.url,
    )
    refresh_support_assist_state()

    return {
        "article": article,
    }


@api.get("/api/admin/knowledge-documents")
@api.get("/admin/knowledge-documents")
def get_admin_knowledge_documents_api():

    return {
        "documents": get_knowledge_documents(),
    }


@api.post("/api/admin/knowledge-documents")
@api.post("/admin/knowledge-documents")
def create_admin_knowledge_document_api(request: KnowledgeDocumentCreateRequest):

    try:
        document = create_knowledge_document(
            title=request.title,
            category=request.category,
            status=request.status,
            summary=request.summary,
            body=request.body,
            tags=request.tags,
            source_name=request.source_name,
            source_type=request.source_type,
        )
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    refresh_support_assist_state()

    return {
        "document": document,
    }


@api.post("/api/admin/knowledge-documents/upload")
@api.post("/admin/knowledge-documents/upload")
def upload_admin_knowledge_documents_api(
    request: KnowledgeDocumentUploadRequest,
):

    if not request.files:
        raise HTTPException(
            status_code=400,
            detail="Add at least one training file before uploading.",
        )

    try:
        upload_result = ingest_uploaded_knowledge_files(
            uploaded_files=[
                file_item.model_dump()
                for file_item in request.files
            ],
            category=request.category,
            status=request.status,
            tags=request.tags,
            source_name=request.source_name,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error

    refresh_support_assist_state()

    return upload_result


@api.post("/api/admin/knowledge-documents/import-url")
@api.post("/admin/knowledge-documents/import-url")
def import_admin_knowledge_url_api(
    request: KnowledgeDocumentUrlImportRequest,
):

    try:
        import_result = ingest_url_knowledge_source(
            raw_url=request.url,
            category=request.category,
            status=request.status,
            tags=request.tags,
            title_prefix=request.title_prefix,
            summary_override=request.summary,
            body_note=request.body_note,
            source_type=request.source_type,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error

    refresh_support_assist_state()

    return import_result


@api.put("/api/admin/knowledge-documents/{document_id}")
@api.put("/admin/knowledge-documents/{document_id}")
def update_admin_knowledge_document_api(
    document_id: int,
    request: KnowledgeDocumentUpdateRequest,
):

    existing_document = get_knowledge_document(document_id)

    if not existing_document:
        raise HTTPException(status_code=404, detail="Knowledge document not found.")

    document = update_knowledge_document(
        document_id=document_id,
        title=request.title,
        category=request.category,
        status=request.status,
        summary=request.summary,
        body=request.body,
        tags=request.tags,
        source_name=request.source_name,
        source_type=request.source_type,
    )
    refresh_support_assist_state()

    return {
        "document": document,
    }


@api.post("/api/admin/knowledge-documents/delete")
@api.post("/admin/knowledge-documents/delete")
def delete_admin_knowledge_documents_api(
    request: KnowledgeDocumentDeleteRequest,
):

    if not request.document_ids:
        raise HTTPException(
            status_code=400,
            detail="Select at least one knowledge item to delete.",
        )

    try:
        delete_result = delete_knowledge_documents(
            request.document_ids
        )
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error

    refresh_support_assist_state()

    return delete_result


@api.post("/api/admin/knowledge-documents/reset")
@api.post("/admin/knowledge-documents/reset")
def reset_admin_workspace_knowledge_api():

    try:
        reset_result = reset_workspace_knowledge()
        clear_assist_response_cache()
        refresh_workspace_index(force_refresh=True)
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error

    return reset_result


@api.get("/api/admin/tickets/{ticket_id}/detail")
def get_admin_ticket_detail(ticket_id: str):

    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    return {
        "ticket": ticket,
        "messages": enrich_entries_with_attachment_urls(
            get_ticket_messages(ticket_id)
        ),
        "notes": enrich_entries_with_attachment_urls(
            get_ticket_notes(ticket_id)
        ),
        "tags": get_ticket_tags(ticket_id),
    }


@api.post("/api/admin/tickets/{ticket_id}/messages")
def post_admin_ticket_message(ticket_id: str, request: AdminTicketMessageRequest):

    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message is required.")

    message = save_message(
        ticket_id=ticket_id,
        sender=request.sender.strip().lower() or "admin",
        message=request.message.strip(),
    )

    return {
        "message": message,
        "ticket": get_ticket(ticket_id),
    }


@api.post("/api/admin/tickets/{ticket_id}/reply")
def post_admin_ticket_reply(ticket_id: str, request: AdminTicketReplyRequest):

    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    decoded_attachments = decode_admin_reply_attachments(request.attachments)
    cleaned_message = str(request.message or "").strip()

    if not cleaned_message and not decoded_attachments:
        raise HTTPException(
            status_code=400,
            detail="Add a reply or at least one image before sending.",
        )

    message = save_message(
        ticket_id=ticket_id,
        sender=request.sender.strip().lower() or "admin",
        message=cleaned_message,
        attachments=decoded_attachments,
    )

    applied_macro = None
    macro_status_applied = False

    if request.applied_macro_id:
        applied_macro = get_macro(request.applied_macro_id)

        if applied_macro is not None:
            apply_macro_tags_to_ticket(
                ticket_id,
                get_ticket_tags(ticket_id),
                applied_macro.get("tag_names", []),
            )

            if applied_macro.get("set_status"):
                update_ticket_status(
                    ticket_id,
                    applied_macro["set_status"],
                )
                macro_status_applied = True

            increment_macro_usage(request.applied_macro_id)

    if not macro_status_applied and ticket.get("status") not in ("Closed", "Resolved"):
        update_ticket_status(ticket_id, "Waiting on Customer")

    return {
        "applied_macro": applied_macro,
        "message": message,
        "tags": get_ticket_tags(ticket_id),
        "ticket": get_ticket(ticket_id),
    }


@api.post("/api/admin/tickets/{ticket_id}/read")
def mark_admin_ticket_read(ticket_id: str):

    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    reset_unread(ticket_id)

    return {
        "ticket": get_ticket(ticket_id),
    }


@api.post("/api/admin/tickets/{ticket_id}/notes")
def create_admin_ticket_note(ticket_id: str, request: AdminTicketNoteRequest):

    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    cleaned_note = str(request.note or "").strip()

    if not cleaned_note:
        raise HTTPException(status_code=400, detail="Add a note before saving.")

    save_ticket_note(
        ticket_id=ticket_id,
        note=cleaned_note,
        author=str(request.author or "").strip()
        or str(ticket.get("assigned_agent") or "").strip()
        or "Inbox Admin",
    )

    return {
        "notes": enrich_entries_with_attachment_urls(
            get_ticket_notes(ticket_id)
        ),
        "ticket": get_ticket(ticket_id),
    }


@api.put("/api/admin/tickets/{ticket_id}/status")
def update_admin_ticket_status(ticket_id: str, request: UpdateTicketStatusRequest):

    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    update_ticket_status(ticket_id, request.status)

    return {
        "ticket": get_ticket(ticket_id),
    }


@api.put("/api/admin/tickets/{ticket_id}/assign")
def update_admin_ticket_assignee(ticket_id: str, request: UpdateTicketAgentRequest):

    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    update_ticket_agent(ticket_id, request.agent_name)

    return {
        "ticket": get_ticket(ticket_id),
    }


@api.post("/api/admin/tickets/{ticket_id}/close")
def close_admin_ticket(ticket_id: str):

    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    close_ticket(ticket_id)

    return {
        "ticket": get_ticket(ticket_id),
    }


@api.get("/api/admin/tickets/{ticket_id}/recommended-macros")
def get_admin_recommended_macros(ticket_id: str):

    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    return {
        "macros": get_ticket_recommended_macros(ticket),
    }


@api.get("/api/admin/attachment")
def get_admin_attachment(path: str = Query(...)):

    relative_path = str(path or "").strip().replace("\\", "/")

    if not relative_path:
        raise HTTPException(status_code=404, detail="Attachment not found.")

    resolved_path = (PROJECT_ROOT / relative_path).resolve()
    uploads_root = MESSAGE_UPLOAD_DIR.resolve()

    if uploads_root not in resolved_path.parents:
        raise HTTPException(status_code=404, detail="Attachment not found.")

    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Attachment not found.")

    return FileResponse(resolved_path)


@api.get("/api/admin/tags")
def get_admin_tags(search_term: str = ""):

    return {
        "tags": get_tags(search_term=search_term),
    }


@api.post("/api/admin/tags")
def create_admin_tag(request: TagRequest):

    try:
        tag_id = create_tag(
            name=request.name,
            description=request.description,
            color=request.color,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "tag": next(
            (
                tag
                for tag in get_tags()
                if int(tag["id"]) == int(tag_id)
            ),
            None,
        ),
    }


@api.put("/api/admin/tags/{tag_id}")
def update_admin_tag(tag_id: int, request: TagRequest):

    try:
        update_tag(
            tag_id=tag_id,
            name=request.name,
            description=request.description,
            color=request.color,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "tag": next(
            (
                tag
                for tag in get_tags()
                if int(tag["id"]) == int(tag_id)
            ),
            None,
        ),
    }


@api.delete("/api/admin/tags/{tag_id}")
def delete_admin_tag(tag_id: int):

    delete_tag(tag_id)

    return {
        "deleted": True,
        "tag_id": tag_id,
    }


@api.post("/api/admin/tags/merge")
def merge_admin_tags(request: TagMergeRequest):

    merge_tags(
        request.target_tag_id,
        request.source_tag_ids,
    )

    return {
        "merged": True,
        "target_tag_id": request.target_tag_id,
    }


@api.put("/api/admin/tickets/{ticket_id}/tags")
def update_admin_ticket_tags(ticket_id: str, request: TicketTagUpdateRequest):

    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    set_ticket_tags(ticket_id, request.tag_ids)

    return {
        "tags": get_ticket_tags(ticket_id),
    }


@api.get("/api/admin/macros")
def get_admin_macros(
    search_term: str = "",
    language: str | None = None,
    category: str | None = None,
    tag_name: str | None = None,
    include_archived: bool = False,
):

    return {
        "macros": get_macros(
            search_term=search_term,
            language=language,
            category=category,
            tag_name=tag_name,
            include_archived=include_archived,
        ),
    }


@api.get("/api/admin/macros/{macro_id}")
def get_admin_macro(macro_id: int):

    macro = get_macro(macro_id)

    if macro is None:
        raise HTTPException(status_code=404, detail="Macro not found.")

    return {
        "macro": macro,
    }


@api.post("/api/admin/macros")
def create_admin_macro(request: MacroRequest):

    try:
        macro_id = create_macro(
            name=request.name,
            response_text=request.response_text,
            language=request.language,
            description=request.description,
            category=request.category,
            subject_template=request.subject_template,
            set_status=request.set_status,
            tag_names=request.tag_names,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    refresh_support_assist_state()

    return {
        "macro": get_macro(macro_id),
    }


@api.put("/api/admin/macros/{macro_id}")
def update_admin_macro(macro_id: int, request: MacroRequest):

    try:
        update_macro(
            macro_id=macro_id,
            name=request.name,
            response_text=request.response_text,
            language=request.language,
            description=request.description,
            category=request.category,
            subject_template=request.subject_template,
            set_status=request.set_status,
            tag_names=request.tag_names,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    refresh_support_assist_state()

    return {
        "macro": get_macro(macro_id),
    }


@api.post("/api/admin/macros/{macro_id}/duplicate")
def duplicate_admin_macro(macro_id: int):

    try:
        duplicated_macro_id = duplicate_macro(macro_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    refresh_support_assist_state()

    return {
        "macro": get_macro(duplicated_macro_id),
    }


@api.post("/api/admin/macros/{macro_id}/archive")
def archive_admin_macro(macro_id: int, request: MacroArchiveRequest):

    archive_macro(
        macro_id,
        is_archived=request.is_archived,
    )
    refresh_support_assist_state()

    return {
        "macro": get_macro(macro_id),
    }


@api.delete("/api/admin/macros/{macro_id}")
def delete_admin_macro(macro_id: int):

    delete_macro(macro_id)
    refresh_support_assist_state()

    return {
        "deleted": True,
        "macro_id": macro_id,
    }


@api.get("/api/admin/workflow-rules")
def get_admin_workflow_rules():

    return {
        "rules": get_workflow_rules(),
    }


@api.get("/api/admin/workflow-rules/windows")
def get_admin_workflow_rule_windows():

    return {
        "windows": get_business_hours_rule_windows(),
    }


@api.get("/api/admin/workflow-rules/{rule_id}/affected")
def get_admin_workflow_rule_affected_tickets(rule_id: int):

    return {
        "tickets": get_rule_affected_tickets(rule_id),
    }


@api.post("/api/admin/workflow-rules")
def create_admin_workflow_rule():

    rule_id = create_workflow_rule()

    return {
        "rule": next(
            (
                rule
                for rule in get_workflow_rules()
                if int(rule["id"]) == int(rule_id)
            ),
            None,
        ),
    }


@api.put("/api/admin/workflow-rules/{rule_id}")
def update_admin_workflow_rule(rule_id: int, request: WorkflowRuleUpdateRequest):

    update_workflow_rule(
        rule_id=rule_id,
        name=request.name,
        description=request.description,
        true_tag_id=request.true_tag_id,
        false_tag_id=request.false_tag_id,
        builder_mode=request.builder_mode,
        config=request.config,
        is_enabled=request.is_enabled,
    )

    return {
        "rule": next(
            (
                rule
                for rule in get_workflow_rules()
                if int(rule["id"]) == int(rule_id)
            ),
            None,
        ),
    }


@api.post("/api/admin/workflow-rules/{rule_id}/duplicate")
def duplicate_admin_workflow_rule(rule_id: int):

    try:
        duplicated_rule_id = duplicate_workflow_rule(rule_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "rule": next(
            (
                rule
                for rule in get_workflow_rules()
                if int(rule["id"]) == int(duplicated_rule_id)
            ),
            None,
        ),
    }


@api.delete("/api/admin/workflow-rules/{rule_id}")
def delete_admin_workflow_rule(rule_id: int):

    delete_workflow_rule(rule_id)

    return {
        "deleted": True,
        "rule_id": rule_id,
    }


@api.post("/api/admin/workflow-rules/restore-default")
def restore_admin_default_workflow_rule():

    rule_id = restore_default_workflow_rule()

    return {
        "rule": next(
            (
                rule
                for rule in get_workflow_rules()
                if int(rule["id"]) == int(rule_id)
            ),
            None,
        ),
    }


@api.get("/api/admin/business-hours/profiles")
def get_admin_business_hours_profiles():

    return {
        "profiles": get_business_hours_profiles(),
    }


@api.get("/api/admin/business-hours/default")
def get_admin_default_business_hours():

    return {
        "profile": get_business_hours_profile(),
    }


@api.post("/api/admin/business-hours/profiles")
def create_admin_business_hours_profile(request: BusinessHoursProfileRequest):

    try:
        profile_id = create_business_hours_profile(
            name=request.name,
            timezone_name=request.timezone_name,
            ranges=[
                range_item.model_dump()
                for range_item in request.ranges
            ],
            description=request.description,
            is_default=request.is_default,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "profile": get_business_hours_profile(profile_id),
    }


@api.put("/api/admin/business-hours/profiles/{profile_id}")
def update_admin_business_hours_profile(profile_id: int, request: BusinessHoursProfileRequest):

    try:
        update_business_hours_profile(
            profile_id=profile_id,
            name=request.name,
            timezone_name=request.timezone_name,
            ranges=[
                range_item.model_dump()
                for range_item in request.ranges
            ],
            description=request.description,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "profile": get_business_hours_profile(profile_id),
    }


@api.delete("/api/admin/business-hours/profiles/{profile_id}")
def delete_admin_business_hours_profile(profile_id: int):

    try:
        delete_business_hours_profile(profile_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "deleted": True,
        "profile_id": profile_id,
    }


