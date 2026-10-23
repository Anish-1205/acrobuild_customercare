"""Properties HTTP endpoints."""
from fastapi import APIRouter
from api_context import (
    HTTPException,
    SiteVisitRequest,
    _cs_api_response,
    get_company_projects,
    get_project_wings,
    get_wing_inventory,
    get_wing_typologies,
)
from services.action_registry import submit_site_visit

router = APIRouter(tags=["properties"])

@router.get("/api/property-flow/projects")
def property_flow_projects():
    return _cs_api_response(get_company_projects, "Browse live projects")

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
    try:
        return submit_site_visit(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
