"""Actions the chat may run, each behind a typed model and a customer confirmation.

The LLM never calls these: the flow engine fills the model, the customer confirms,
then code runs the action. Pending actions are single-use and expire.
"""
import secrets
import time

from pydantic import BaseModel

PENDING_TTL_SECONDS = 600


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


def submit_site_visit(request):
    """Shared by POST /api/site-visits and the chat flow. Raises ValueError on missing fields."""
    from graph.workflow import run_workflow

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
        raise ValueError(f"Required: {', '.join(missing)}")

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


ACTIONS = {
    "book_site_visit": (SiteVisitRequest, submit_site_visit),
}


def propose(name, args, now=None):
    """Validate args now so a bad payload never reaches the confirmation step."""
    model, _ = ACTIONS[name]
    model.model_validate(args)
    return {"action": name, "args": args, "nonce": secrets.token_urlsafe(8),
            "expires_at": (now or time.time()) + PENDING_TTL_SECONDS}


def confirm(pending, nonce, now=None):
    """Run a pending action once. Returns the action result, or None if stale/wrong."""
    if not pending or not secrets.compare_digest(str(pending.get("nonce", "")), str(nonce or "")):
        return None
    if pending.get("expires_at", 0) <= (now or time.time()):
        return None
    model, run = ACTIONS[pending["action"]]
    return run(model.model_validate(pending["args"]))
