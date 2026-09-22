"""Properties HTTP endpoints."""
from fastapi import APIRouter
from api_context import (
    HTTPException,
    SiteVisitRequest,
    _cs_api_response,
    _customer_facing_projects,
    get_company_projects,
    get_project_wings,
    get_wing_inventory,
    get_wing_typologies,
    run_workflow,
)

router = APIRouter(tags=["properties"])

@router.get("/api/property-flow/projects")
def property_flow_projects():
    # Same customer-facing list the chat offers, so "Browse projects" and a
    # typed "what projects do you have?" never show different choices.
    return _cs_api_response(lambda: _customer_facing_projects(get_company_projects()), "Browse live projects")

@router.get("/api/property-flow/projects/{project_id}/wings")
def property_flow_wings(project_id: int):
    return _cs_api_response(
        lambda: get_project_wings(project_id),
        f"Load wings for project {project_id}",
    )

@router.get("/api/property-flow/wings/{wing_id}/typologies")
def property_flow_typologies(wing_id: int):
    return _cs_api_response(
        lambda: get_wing_typologies(wing_id),
        f"Load pricing for wing {wing_id}",
    )

@router.get("/api/property-flow/wings/{wing_id}/inventory")
def property_flow_inventory(wing_id: int, available_only: bool = True):
    return _cs_api_response(
        lambda: get_wing_inventory(wing_id, available_only),
        f"Load available flats for wing {wing_id}",
    )

@router.post("/api/site-visits")
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
