import hashlib
import time
from contextlib import closing
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel, Field

from services.database_service import get_ticket, open_database_connection
from services.otp_service import validate_email_access_token
from services.workflow_automation_service import escalation_queue, capacity_recommendations, propose_action, confirm_action

router = APIRouter(tags=["automation"])


class ProposalRequest(BaseModel):
    ticket_id: str = Field(min_length=1, max_length=100)
    kind: Literal["assign", "status"]
    value: str = Field(min_length=1, max_length=100)


class ConfirmationRequest(BaseModel):
    confirmed: Literal[True]


class FeedbackRequest(BaseModel):
    ticket_id: str = Field(min_length=1, max_length=100)
    rating: int = Field(ge=1, le=5)


@router.get("/api/admin/automation/escalations")
def escalations(request: Request):
    user = request.state.workspace_user
    return {"tickets": escalation_queue(user["name"] if user["role"] == "agent" else None), "clock": "elapsed_hours"}


@router.get("/api/admin/automation/capacity")
def capacity():
    return {"agents": capacity_recommendations()}


@router.post("/api/admin/automation/proposals")
def propose(payload: ProposalRequest, request: Request):
    user = request.state.workspace_user
    if user["role"] not in {"admin", "owner"}:
        raise HTTPException(403, "Manager access required")
    try:
        return propose_action(int(user["sub"]), payload.ticket_id, payload.kind, {"assigned_agent" if payload.kind == "assign" else "status": payload.value})
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.post("/api/admin/automation/proposals/{proposal_id}/confirm")
def confirm(proposal_id: str, payload: ConfirmationRequest, request: Request):
    if request.state.workspace_user["role"] not in {"admin", "owner"}:
        raise HTTPException(403, "Manager access required")
    try:
        return confirm_action(int(request.state.workspace_user["sub"]), proposal_id)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.post("/api/support/feedback")
def feedback(payload: FeedbackRequest, authorization: str = Header(...)):
    ticket = get_ticket(payload.ticket_id)
    token = authorization.removeprefix("Bearer ")
    if not ticket or not validate_email_access_token(ticket.get("customer_email", ""), token):
        raise HTTPException(401, "Verified customer session required")
    if ticket.get("status") not in {"Resolved", "Closed"}:
        raise HTTPException(409, "Feedback is available after resolution")
    email_hash = hashlib.sha256(ticket["customer_email"].strip().lower().encode()).hexdigest()
    with closing(open_database_connection()) as conn, conn:
        conn.execute("INSERT INTO ticket_feedback VALUES(?,?,?,?) ON CONFLICT(ticket_id,email_hash) DO UPDATE SET rating=excluded.rating,created_at=excluded.created_at", (payload.ticket_id, email_hash, payload.rating, time.time()))
    return {"saved": True}
