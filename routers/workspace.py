"""Workspace HTTP endpoints."""
from fastapi import APIRouter
from services.database_service import list_tickets
from api_context import (
    AdminTicketMessageRequest,
    AdminTicketNoteRequest,
    AdminTicketReplyRequest,
    BusinessHoursProfileRequest,
    FileResponse,
    HTTPException,
    MESSAGE_UPLOAD_DIR,
    MacroArchiveRequest,
    MacroRequest,
    PROJECT_ROOT,
    Query,
    Request,
    SupportUserCreateRequest,
    SupportUserUpdateRequest,
    TagMergeRequest,
    TagRequest,
    TicketTagUpdateRequest,
    UpdateTicketAgentRequest,
    UpdateTicketStatusRequest,
    WorkflowRuleUpdateRequest,
    apply_macro_tags_to_ticket,
    archive_macro,
    close_ticket,
    create_business_hours_profile,
    create_macro,
    create_support_user,
    create_tag,
    create_workflow_rule,
    decode_admin_reply_attachments,
    delete_business_hours_profile,
    delete_macro,
    delete_tag,
    delete_workflow_rule,
    duplicate_macro,
    duplicate_workflow_rule,
    enrich_entries_with_attachment_urls,
    get_all_tickets,
    get_business_hours_profile,
    get_business_hours_profiles,
    get_business_hours_rule_windows,
    get_macro,
    get_macros,
    get_rule_affected_tickets,
    get_support_user,
    get_support_users,
    get_tags,
    get_ticket,
    get_ticket_messages,
    get_ticket_notes,
    get_ticket_recommended_macros,
    get_ticket_tags,
    get_workflow_rules,
    increment_macro_usage,
    merge_tags,
    refresh_support_assist_state,
    reset_unread,
    restore_default_workflow_rule,
    save_message,
    save_ticket_note,
    set_ticket_tags,
    update_business_hours_profile,
    update_macro,
    update_support_user,
    update_tag,
    update_ticket_agent,
    update_ticket_status,
    update_workflow_rule,
)

router = APIRouter(tags=["workspace"])

@router.get("/admin/all-tickets")
def get_admin_tickets(http_request: Request, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):

    try:
        return list_tickets(limit=limit, offset=offset, assigned_agent=http_request.state.workspace_user.get("name") if http_request.state.workspace_user.get("role") == "agent" else None)

    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

@router.put("/admin/tickets/{ticket_id}/assign")
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

@router.put("/admin/tickets/{ticket_id}/status")
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

@router.get("/api/admin/tickets")
def get_admin_tickets_api(http_request: Request, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), status: str = "", search: str = ""):

    return {
        **list_tickets(
            limit=limit, offset=offset, status=status, search=search,
            assigned_agent=http_request.state.workspace_user.get("name") if http_request.state.workspace_user.get("role") == "agent" else None,
        ),
    }

@router.get("/api/admin/users")
@router.get("/admin/users")
def get_admin_users_api():

    return {
        "users": get_support_users(),
    }

@router.post("/api/admin/users")
@router.post("/admin/users")
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

@router.put("/api/admin/users/{user_id}")
@router.put("/admin/users/{user_id}")
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

@router.get("/api/admin/tickets/{ticket_id}/detail")
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

@router.post("/api/admin/tickets/{ticket_id}/messages")
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

@router.post("/api/admin/tickets/{ticket_id}/reply")
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

@router.post("/api/admin/tickets/{ticket_id}/read")
def mark_admin_ticket_read(ticket_id: str):

    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    reset_unread(ticket_id)

    return {
        "ticket": get_ticket(ticket_id),
    }

@router.post("/api/admin/tickets/{ticket_id}/notes")
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

@router.put("/api/admin/tickets/{ticket_id}/status")
def update_admin_ticket_status(ticket_id: str, request: UpdateTicketStatusRequest):

    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    update_ticket_status(ticket_id, request.status)

    return {
        "ticket": get_ticket(ticket_id),
    }

@router.put("/api/admin/tickets/{ticket_id}/assign")
def update_admin_ticket_assignee(ticket_id: str, request: UpdateTicketAgentRequest):

    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    update_ticket_agent(ticket_id, request.agent_name)

    return {
        "ticket": get_ticket(ticket_id),
    }

@router.post("/api/admin/tickets/{ticket_id}/close")
def close_admin_ticket(ticket_id: str):

    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    close_ticket(ticket_id)

    return {
        "ticket": get_ticket(ticket_id),
    }

@router.get("/api/admin/tickets/{ticket_id}/recommended-macros")
def get_admin_recommended_macros(ticket_id: str):

    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    return {
        "macros": get_ticket_recommended_macros(ticket),
    }

@router.get("/api/admin/attachment")
def get_admin_attachment(http_request: Request, path: str = Query(...)):

    relative_path = str(path or "").strip().replace("\\", "/")

    if not relative_path:
        raise HTTPException(status_code=404, detail="Attachment not found.")

    resolved_path = (PROJECT_ROOT / relative_path).resolve()
    uploads_root = MESSAGE_UPLOAD_DIR.resolve()

    if uploads_root not in resolved_path.parents:
        raise HTTPException(status_code=404, detail="Attachment not found.")

    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Attachment not found.")

    if http_request.state.workspace_user["role"] == "agent":
        from contextlib import closing
        from services.database_service import open_database_connection
        import json
        with closing(open_database_connection()) as conn:
            rows = conn.execute("SELECT m.attachments_json FROM messages m JOIN tickets t ON t.ticket_id=m.ticket_id WHERE t.assigned_agent=?", (http_request.state.workspace_user["name"],)).fetchall()
        allowed = any((PROJECT_ROOT / item.get("path", "")).resolve() == resolved_path for row in rows for item in json.loads(row[0] or "[]"))
        if not allowed:
            raise HTTPException(404, "Attachment not found.")
    return FileResponse(resolved_path, filename=resolved_path.name, content_disposition_type="attachment")

@router.get("/api/admin/tags")
def get_admin_tags(search_term: str = ""):

    return {
        "tags": get_tags(search_term=search_term),
    }

@router.post("/api/admin/tags")
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

@router.put("/api/admin/tags/{tag_id}")
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

@router.delete("/api/admin/tags/{tag_id}")
def delete_admin_tag(tag_id: int):

    delete_tag(tag_id)

    return {
        "deleted": True,
        "tag_id": tag_id,
    }

@router.post("/api/admin/tags/merge")
def merge_admin_tags(request: TagMergeRequest):

    merge_tags(
        request.target_tag_id,
        request.source_tag_ids,
    )

    return {
        "merged": True,
        "target_tag_id": request.target_tag_id,
    }

@router.put("/api/admin/tickets/{ticket_id}/tags")
def update_admin_ticket_tags(ticket_id: str, request: TicketTagUpdateRequest):

    ticket = get_ticket(ticket_id)

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    set_ticket_tags(ticket_id, request.tag_ids)

    return {
        "tags": get_ticket_tags(ticket_id),
    }

@router.get("/api/admin/macros")
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

@router.get("/api/admin/macros/{macro_id}")
def get_admin_macro(macro_id: int):

    macro = get_macro(macro_id)

    if macro is None:
        raise HTTPException(status_code=404, detail="Macro not found.")

    return {
        "macro": macro,
    }

@router.post("/api/admin/macros")
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

@router.put("/api/admin/macros/{macro_id}")
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

@router.post("/api/admin/macros/{macro_id}/duplicate")
def duplicate_admin_macro(macro_id: int):

    try:
        duplicated_macro_id = duplicate_macro(macro_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    refresh_support_assist_state()

    return {
        "macro": get_macro(duplicated_macro_id),
    }

@router.post("/api/admin/macros/{macro_id}/archive")
def archive_admin_macro(macro_id: int, request: MacroArchiveRequest):

    archive_macro(
        macro_id,
        is_archived=request.is_archived,
    )
    refresh_support_assist_state()

    return {
        "macro": get_macro(macro_id),
    }

@router.delete("/api/admin/macros/{macro_id}")
def delete_admin_macro(macro_id: int):

    delete_macro(macro_id)
    refresh_support_assist_state()

    return {
        "deleted": True,
        "macro_id": macro_id,
    }

@router.get("/api/admin/workflow-rules")
def get_admin_workflow_rules():

    return {
        "rules": get_workflow_rules(),
    }

@router.get("/api/admin/workflow-rules/windows")
def get_admin_workflow_rule_windows():

    return {
        "windows": get_business_hours_rule_windows(),
    }

@router.get("/api/admin/workflow-rules/{rule_id}/affected")
def get_admin_workflow_rule_affected_tickets(rule_id: int):

    return {
        "tickets": get_rule_affected_tickets(rule_id),
    }

@router.post("/api/admin/workflow-rules")
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

@router.put("/api/admin/workflow-rules/{rule_id}")
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

@router.post("/api/admin/workflow-rules/{rule_id}/duplicate")
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

@router.delete("/api/admin/workflow-rules/{rule_id}")
def delete_admin_workflow_rule(rule_id: int):

    delete_workflow_rule(rule_id)

    return {
        "deleted": True,
        "rule_id": rule_id,
    }

@router.post("/api/admin/workflow-rules/restore-default")
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

@router.get("/api/admin/business-hours/profiles")
def get_admin_business_hours_profiles():

    return {
        "profiles": get_business_hours_profiles(),
    }

@router.get("/api/admin/business-hours/default")
def get_admin_default_business_hours():

    return {
        "profile": get_business_hours_profile(),
    }

@router.post("/api/admin/business-hours/profiles")
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

@router.put("/api/admin/business-hours/profiles/{profile_id}")
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

@router.delete("/api/admin/business-hours/profiles/{profile_id}")
def delete_admin_business_hours_profile(profile_id: int):

    try:
        delete_business_hours_profile(profile_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "deleted": True,
        "profile_id": profile_id,
    }
