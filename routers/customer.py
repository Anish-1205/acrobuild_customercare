"""Customer HTTP endpoints."""
from fastapi import APIRouter
from api_context import (
    Depends,
    HTTPException,
    Header,
    OtpRequest,
    OtpVerifyRequest,
    Query,
    RefundRequest,
    Request,
    SubscriptionCancelRequest,
    TicketMessageRequest,
    TicketRequest,
    _authorize_customer_identity,
    _bearer_token,
    get_all_tickets,
    get_support_user,
    get_ticket,
    request_email_otp,
    require_workspace_user,
    run_workflow,
    save_message,
    validate_email_access_token,
    verify_email_otp,
)

router = APIRouter(tags=["customer"])
from contextlib import closing
from services.database_service import open_database_connection


def customer_data(email, assigned_agent=None):
    normalized_email = email.strip().lower()
    with closing(open_database_connection()) as conn:
        import sqlite3
        conn.row_factory = sqlite3.Row
        sql = "SELECT * FROM tickets WHERE lower(customer_email)=?"
        params = [normalized_email]
        if assigned_agent is not None:
            sql += " AND assigned_agent=?"
            params.append(assigned_agent)
        rows = conn.execute(sql + " ORDER BY created_at DESC LIMIT 500", params).fetchall()
    tickets = [dict(row) for row in rows]
    return {"customer": {"email": normalized_email, "name": normalized_email.split("@")[0],
                         "total_orders": len(tickets), "total_spent": 0, "source": "acrobuild_support"},
            "orders": [{"id": t["ticket_id"], "order_number": t["ticket_id"], "status": t["status"],
                        "issue": t["issue"], "total": 0, "created_at": t["created_at"],
                        "project_type": t["issue_type"]} for t in tickets],
            "subscriptions": [], "addresses": [], "source_status": "local_acrobuild_support"}

@router.post("/create_ticket")
def create_ticket(request: TicketRequest):

    result = run_workflow(
        request.issue,
        request.customer_email
    )

    return result

@router.get("/customer")
def get_customer(
    http_request: Request, email: str = Query(...),
    api_base_url: str | None = Query(None), authorization: str | None = Header(None),
):
    token = _bearer_token(authorization) if authorization else ""
    if token and validate_email_access_token(email, token):
        return customer_data(email)
    claims = require_workspace_user(authorization, http_request.cookies.get("workspace_session", ""))
    return customer_data(email, claims.get("name") if claims["role"] == "agent" else None)

@router.post("/auth/otp/request")
def request_otp(request: OtpRequest, http_request: Request):

    try:
        delivery = request_email_otp(
            request.email,
            client_ip=http_request.client.host if http_request.client else "unknown",
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return {
        "message": "Verification code sent.",
        **delivery,
    }

@router.post("/auth/otp/verify")
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

@router.get("/auth/me")
def workspace_me(claims=Depends(require_workspace_user)):
    user = get_support_user(int(claims["sub"]))
    if not user or user.get("status") != "Active":
        raise HTTPException(status_code=401, detail="Workspace account is unavailable.")
    return {"user": user}

@router.get("/customer/verified")
def get_verified_customer(
    email: str = Query(...),
    authorization: str = Header(...),
    api_base_url: str | None = Query(None),
):
    access_token = _bearer_token(authorization)

    if not validate_email_access_token(
        email,
        access_token,
    ):
        raise HTTPException(
            status_code=401,
            detail="Verification expired. Request a new code.",
        )

    return customer_data(email)

@router.get("/orders")
def get_orders(
    http_request: Request, email: str = Query(...),
    api_base_url: str | None = Query(None), authorization: str | None = Header(None),
):
    del api_base_url
    return {"orders": get_customer(http_request=http_request, email=email, authorization=authorization).get("orders", [])}

@router.post("/ticket/message")
def add_ticket_message(request: TicketMessageRequest):

    ticket = get_ticket(request.ticket_id)

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    if not validate_email_access_token(ticket.get("customer_email", ""), request.access_token):
        raise HTTPException(status_code=401, detail="A verified customer session is required.")

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

@router.post("/order/refund")
def refund_order(request: RefundRequest):
    raise HTTPException(status_code=501, detail="Refund processing is not implemented; contact support for manual review.")

@router.post("/subscription/cancel")
def cancel_subscription(request: SubscriptionCancelRequest):
    raise HTTPException(status_code=501, detail="Subscription cancellation is not implemented; contact support for manual review.")
