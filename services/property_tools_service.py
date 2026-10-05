"""Typed, read-only tools over the live AcroBuild CS API (Inquiry to Sales §33).

Every tool returns a ToolResult and never raises to its caller. Data comes only
from services/acrobuild_company_service.py (the 7 CS API endpoints already in
use); tools that need an endpoint AcroBuild does not expose yet are listed in
BLOCKED_TOOLS and make no network call.

``source_status`` is derived from the data-API log entries this call added
(services/internal_api_log_service.py), using the same rules as
api_context._enforce_live_property_data(), which stays the final authority for
any payload built from these results. Callers put ``evidence`` (record_kind
"company_api") into a payload's matched_chunks so specific figures are backed.

This module must never import the compiled runtime in
services/ai_agent_service.py or anything under graph/.
"""
from datetime import datetime, timezone
import re
from typing import Any, Callable, TypedDict

from services import acrobuild_company_service as company_service
from services.internal_api_log_service import get_current_data_api_logs, get_data_api_logs


class ToolResult(TypedDict):
    tool: str
    status: str          # "ok" | "empty" | "partial" | "unavailable" | "blocked" | "invalid"
    source_status: str   # "live_api" | "snapshot" | "failed" | "unavailable"
    data: Any
    evidence: list[dict]
    skipped: list[dict]
    error: str


# Matches internal_api_log_service._MAX_LOGS: the whole in-memory log window.
_LOG_WINDOW = 500
_LIVE_PROVIDER = "Acrobuild CS API"
_BHK_RE = re.compile(r"\b([1-6])\s*b(?:h)?ks?\b", re.IGNORECASE)
_ANY_LOCALITY = {"", "any"}


class _NotFound(Exception):
    """A requested record is not in the live data (never a transport error)."""


# -----------------------------------
# RESULT + SOURCE STATUS
# -----------------------------------

def _result(tool, status, source_status, data=None, evidence=None, skipped=None, error="") -> ToolResult:
    return {
        "tool": tool,
        "status": status,
        "source_status": source_status,
        "data": data if data is not None else [],
        "evidence": list(evidence or []),
        "skipped": list(skipped or []),
        "error": str(error or ""),
    }


def _log_ids():
    return {record.get("id") for record in get_data_api_logs(limit=_LOG_WINDOW)}


def _new_log_entries(before_ids):
    """Log entries added since ``before_ids`` for this turn, oldest first.

    Inside an assist turn only entries on the current trace count, so another
    request's concurrent calls never leak into this result."""
    new = [record for record in reversed(get_data_api_logs(limit=_LOG_WINDOW))
           if record.get("id") not in before_ids]
    traced_ids = {record.get("id") for record in get_current_data_api_logs()}
    if traced_ids:
        return [record for record in new if record.get("id") in traced_ids]
    return [record for record in new if not record.get("trace_id")]


def classify_source_status(entries):
    """"live_api" | "snapshot" | "failed" | "unavailable" for chronological log entries.

    Mirrors api_context._enforce_live_property_data(): the latest entry per
    (endpoint, params) is authoritative, a failed live call is only acceptable
    when a snapshot covered that endpoint, and no entries means no live
    evidence at all. A failed live call can therefore never yield "live_api".
    """
    latest = {}
    for entry in entries or []:
        key = (entry.get("endpoint"), tuple(sorted((entry.get("params") or {}).items())))
        latest[key] = entry
    calls = list(latest.values())
    failed = [c for c in calls if c.get("provider") == _LIVE_PROVIDER and c.get("status") == "failed"]
    snapshot_endpoints = {
        c.get("endpoint") for c in calls
        if "snapshot" in str(c.get("provider", "")).lower() and c.get("status") in {"cached", "completed"}
    }
    if any(c.get("endpoint") not in snapshot_endpoints for c in failed):
        return "failed"
    if snapshot_endpoints:
        return "snapshot"
    if any(c.get("provider") == _LIVE_PROVIDER and c.get("status") in {"completed", "cached"} for c in calls):
        return "live_api"
    return "unavailable"


def _run(tool, operation: Callable[[], tuple]) -> ToolResult:
    """Run one tool body; ``operation`` returns (data, evidence, skipped)."""
    before = _log_ids()
    try:
        data, evidence, skipped = operation()
    except _NotFound as error:
        return _result(tool, "empty", classify_source_status(_new_log_entries(before)), error=str(error))
    except (RuntimeError, OSError) as error:  # OSError covers TimeoutError and socket errors
        return _result(tool, "unavailable", "failed",
                       error=str(error) or "Live property data is unavailable.")
    source_status = classify_source_status(_new_log_entries(before))
    has_data = bool(data.get("items") if isinstance(data, dict) and "items" in data else data)
    if skipped or (source_status == "failed" and has_data):
        status = "partial"
    elif source_status == "failed":
        status = "unavailable"
    elif has_data:
        status = "ok"
    else:
        status = "empty"
    note = f"{len(skipped)} project(s) could not be checked." if skipped else ""
    return _result(tool, status, source_status, data, evidence, skipped, note)


# -----------------------------------
# VALIDATION + SHARED HELPERS
# -----------------------------------

def _valid_id(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    text = str(value or "").strip()
    return int(text) if text.isdecimal() and int(text) > 0 else None


def _config_numbers(config):
    """Normalise ["3", "3BHK", 3] to ["3"]; None when any value is not a 1-6 BHK."""
    numbers = []
    for value in config or []:
        text = str(value).strip()
        match = re.fullmatch(r"([1-6])", text) or _BHK_RE.fullmatch(text)
        if not match:
            return None
        numbers.append(match.group(1))
    return list(dict.fromkeys(numbers))


def _record_numbers(record):
    text = f"{record.get('typologyName') or ''} {record.get('typologyType') or ''}"
    return set(_BHK_RE.findall(text))


def _projects():
    return company_service.customer_facing_projects(company_service.get_company_projects())


def _project(project_id):
    project = next((p for p in _projects() if _valid_id(p.get("id")) == project_id), None)
    if project is None:
        raise _NotFound(f"Project {project_id} is not in the live catalogue.")
    return project


def _name(project):
    return str(project.get("projectName") or "").strip()


def _epoch_ms_to_date(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _chunk(tool, key, title, lines, **extra):
    return {
        "record_kind": "company_api",
        "source_key": f"tool-{tool}-{key}",
        "source_name": "AcroBuild CS API",
        "title": title,
        "body_text": "\n".join(str(line) for line in lines),
        "score": 100.0,
        **extra,
    }


_MARKER_CHAR = "⁣"
_CONTROL_CHARS_RE = re.compile("[\\x00-\\x1f\\x7f-\\x9f]")


def clean_place_text(value):
    """Place text as customers see it: U+2063 removed, C0/C1 control characters
    turned into spaces, whitespace collapsed.

    Deliberately the same rule as property_clarification_service._clean_option_text()
    (which imports this module, so it cannot be imported here); a test pins both
    to identical output."""
    text = str(value or "").replace(_MARKER_CHAR, "")
    return " ".join(_CONTROL_CHARS_RE.sub(" ", text).split())


def project_localities(project):
    """Live place values a project can be found under: its locality and city,
    cleaned like the options customers are shown."""
    return {clean_place_text(project.get(key)) for key in ("locality", "city")
            if clean_place_text(project.get(key))}


def project_in_locality(project, locality):
    """Same rule as property_clarification_service.narrow_project_choice_by_locality():
    the project's city/locality is that place, or its address names it.
    Both sides are cleaned first, so an option shown without invisible
    characters still matches the live value it came from."""
    wanted = clean_place_text(locality).lower()
    if not wanted:
        return False
    if wanted in {value.lower() for value in project_localities(project)}:
        return True
    address = clean_place_text(" ".join(str(project.get(key) or "") for key in ("address", "location"))).lower()
    return bool(re.search(r"\b" + re.escape(wanted) + r"\b", address))


def _project_display_locality(project):
    return str(project.get("locality") or "").strip() or str(project.get("city") or "").strip()


# -----------------------------------
# CATALOGUE TOOLS
# -----------------------------------

def list_localities(config: list[str] | None = None) -> ToolResult:
    """Distinct live localities (a project's ``locality``, else its ``city``),
    limited to projects whose typologies list every requested BHK number.

    Not a §33 tool; it supplies the options for the discovery locality question."""
    numbers = _config_numbers(config)
    if numbers is None:
        return _result("list_localities", "invalid", "unavailable", error="Unsupported configuration value.")

    def body():
        projects = _projects()
        skipped = []
        if numbers:
            index, failed = company_service.build_project_record_index(
                company_service.get_project_typologies, projects=projects)
            skipped = [{"project": _name(project), "error": str(error)} for project, error in failed]
            projects = [entry["project"] for entry in index.values()
                        if set(numbers) <= set().union(*(_record_numbers(r) for r in entry["records"]))]
        by_locality: dict[str, list[str]] = {}
        for project in projects:
            place = _project_display_locality(project)
            if place:
                by_locality.setdefault(place, []).append(_name(project))
        names = sorted(by_locality, key=str.lower)
        evidence = [_chunk("list_localities", re.sub(r"[^a-z0-9]+", "-", place.lower()), f"Projects in {place}",
                           by_locality[place], locality=place, project_names=by_locality[place])
                    for place in names]
        return names, evidence, skipped

    return _run("list_localities", body)


def _estimate(typology):
    """(min, max) estimated base amount in INR, or None when it can't be computed.

    Only per-sq.-ft. rates are multiplied by saleable area; the live values of
    ``rateType`` are unverified, so any other rate basis is left unpriced."""
    if "sq" not in str(typology.get("rateType") or "").lower():
        return None
    rate = typology.get("minBasePrice")
    rate_max = typology.get("maxBasePrice") or rate
    area = typology.get("saleableArea")
    values = (rate, rate_max, area)
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in values):
        return None
    return float(rate) * float(area), float(rate_max) * float(area)


def search_projects(config: list[str] | None = None, locality: str = "",
                    budget_max_inr: int | None = None) -> ToolResult:
    """Projects matching BHK config, live locality and an estimated-base-amount budget.

    data = {"locality_known", "matches", "over_budget", "unpriced"}; each entry is
    {"project", "typologies", "estimated_base_min_inr", "estimated_base_max_inr"}.
    Inventory is not fetched: availability is confirmed per project afterwards.
    """
    numbers = _config_numbers(config)
    if numbers is None:
        return _result("search_projects", "invalid", "unavailable", error="Unsupported configuration value.")
    if budget_max_inr is not None and (isinstance(budget_max_inr, bool) or not isinstance(budget_max_inr, int)
                                       or not 0 < budget_max_inr <= 10**10):
        return _result("search_projects", "invalid", "unavailable", error="Budget must be a positive amount in INR.")
    wanted = str(locality or "").strip()

    def body():
        projects = _projects()
        if wanted.lower() not in _ANY_LOCALITY:
            projects = [project for project in projects if project_in_locality(project, wanted)]
            if not projects:
                return {"locality_known": False, "items": [], "matches": [], "over_budget": [], "unpriced": []}, [], []
        index, failed = company_service.build_project_record_index(
            company_service.get_project_typologies, projects=projects)
        data: dict[str, Any] = {"locality_known": True, "matches": [], "over_budget": [], "unpriced": []}
        evidence = []
        for entry in index.values():
            project = entry["project"]
            typologies = [t for t in entry["records"] if not numbers or set(numbers) & _record_numbers(t)]
            if numbers and not set(numbers) <= set().union(*(_record_numbers(t) for t in entry["records"])):
                continue
            estimates = [e for e in (_estimate(t) for t in typologies) if e]
            item: dict[str, Any] = {
                "project": project,
                "typologies": typologies,
                "estimated_base_min_inr": min(e[0] for e in estimates) if estimates else None,
                "estimated_base_max_inr": max(e[1] for e in estimates) if estimates else None,
            }
            if not estimates:
                bucket = "unpriced"
            elif budget_max_inr is not None and item["estimated_base_min_inr"] > budget_max_inr:
                bucket = "over_budget"
            else:
                bucket = "matches"
            data[bucket].append(item)
            evidence.append(_chunk(
                "search_projects", project.get("id"), f"{_name(project)} configurations",
                [f"{t.get('typologyName') or t.get('typologyType')}: rate {t.get('minBasePrice')}-"
                 f"{t.get('maxBasePrice')} ({t.get('rateType') or 'rate basis not listed'}), "
                 f"saleable area {t.get('saleableArea')}" for t in typologies],
                project=project, typologies=typologies))
        data["items"] = data["matches"] + data["over_budget"] + data["unpriced"]
        skipped = [{"project": _name(project), "error": str(error)} for project, error in failed]
        return data, evidence, skipped

    return _run("search_projects", body)


# -----------------------------------
# PROJECT TOOLS
# -----------------------------------

def _project_tool(tool, project_id, build) -> ToolResult:
    """Shared id validation + project lookup for per-project tools.

    ``build(project)`` returns (data, lines, extra_evidence_fields)."""
    valid = _valid_id(project_id)
    if valid is None:
        return _result(tool, "invalid", "unavailable", error="project_id must be a positive integer.")

    def body():
        project = _project(valid)
        data, lines, extra = build(project)
        evidence = [_chunk(tool, valid, f"{_name(project)} {tool.replace('_', ' ')}", lines,
                           project=project, **extra)] if data else []
        return data, evidence, []

    return _run(tool, body)


def get_project_details(project_id: int) -> ToolResult:
    def build(project):
        wings = company_service.get_project_wings(project["id"])
        fields = ("projectName", "projectCode", "address", "locality", "city", "reraNo",
                  "propertyDetails", "projectType")
        lines = [f"{key}: {project.get(key)}" for key in fields if project.get(key) not in (None, "")]
        lines += [f"wing: {w.get('name') or w.get('code')}" for w in wings]
        return {"project": project, "wings": wings}, lines, {"wings": wings}
    return _project_tool("get_project_details", project_id, build)


def get_project_history(project_id: int) -> ToolResult:
    """Project-level estimated start/end dates only; phase and tower launch
    history needs an AcroBuild endpoint (see BLOCKED_TOOLS)."""
    def build(project):
        start = _epoch_ms_to_date(project.get("estimatedStartDate"))
        end = _epoch_ms_to_date(project.get("estimatedEndDate"))
        if not (start or end):
            return {}, [], {}
        data = {"project_name": _name(project), "estimated_start_date": start, "estimated_end_date": end}
        return data, [f"estimated start: {start}", f"estimated end: {end}"], {}
    return _project_tool("get_project_history", project_id, build)


def _wing_label(wing):
    return str(wing.get("name") or wing.get("code") or "").strip()


def search_inventory(project_id: int, config: list[str] | None = None, floor: int | None = None,
                     available_only: bool = True) -> ToolResult:
    numbers = _config_numbers(config)
    if numbers is None:
        return _result("search_inventory", "invalid", "unavailable", error="Unsupported configuration value.")
    if floor is not None and (isinstance(floor, bool) or not isinstance(floor, int)):
        return _result("search_inventory", "invalid", "unavailable", error="floor must be an integer.")

    def build(project):
        units = []
        for wing in company_service.get_project_wings(project["id"]):
            for unit in company_service.get_wing_inventory(wing["id"], available_only):
                if numbers and not set(numbers) & _record_numbers(unit):
                    continue
                if floor is not None and str(unit.get("floorNumber")) != str(floor):
                    continue
                units.append({**unit, "wingName": _wing_label(wing)})
        lines = [f"{u.get('wingName')} flat {u.get('unitNumber')}, floor {u.get('floorNumber')}, "
                 f"{u.get('typologyName')}, status {u.get('statusLabel') or u.get('status')}" for u in units]
        return units, lines, {"units": units}
    return _project_tool("search_inventory", project_id, build)


def get_unit_details(project_id: int, unit_number: str) -> ToolResult:
    """Every unit with that number (one per wing can exist); never picks one."""
    wanted = str(unit_number or "").strip()
    if not wanted:
        return _result("get_unit_details", "invalid", "unavailable", error="unit_number is required.")

    def build(project):
        units = [{**unit, "wingName": _wing_label(wing)}
                 for wing in company_service.get_project_wings(project["id"])
                 for unit in company_service.get_wing_inventory(wing["id"], False)
                 if str(unit.get("unitNumber") or "").strip() == wanted]
        lines = [f"{u.get('wingName')} flat {u.get('unitNumber')}: floor {u.get('floorNumber')}, "
                 f"{u.get('typologyName')}, carpet area {u.get('carpetArea')}, saleable area "
                 f"{u.get('saleableArea')}, status {u.get('statusLabel') or u.get('status')}" for u in units]
        return units, lines, {"units": units}
    return _project_tool("get_unit_details", project_id, build)


def get_live_price(project_id: int, config: list[str] | None = None) -> ToolResult:
    """Typology base-rate ranges as listed by the CS API; per-unit prices are
    not exposed (see BLOCKED_TOOLS["calculate_cost_sheet"])."""
    numbers = _config_numbers(config)
    if numbers is None:
        return _result("get_live_price", "invalid", "unavailable", error="Unsupported configuration value.")
    fields = ("typologyName", "typologyType", "rateType", "minBasePrice", "maxBasePrice", "carpetArea", "saleableArea")

    def build(project):
        rows = [{key: t.get(key) for key in fields}
                for t in company_service.get_project_typologies(project["id"])
                if not numbers or set(numbers) & _record_numbers(t)]
        rows = [row for row in rows if row.get("minBasePrice") is not None]
        lines = [f"{r['typologyName'] or r['typologyType']}: {r['minBasePrice']}-{r['maxBasePrice']} "
                 f"({r['rateType'] or 'rate basis not listed'})" for r in rows]
        return rows, lines, {"typologies": rows}
    return _project_tool("get_live_price", project_id, build)


def get_amenities(project_id: int) -> ToolResult:
    def build(project):
        rows = [{"name": str(r.get("iconName") or "").strip(), "type": r.get("type")}
                for r in company_service.get_project_amenities(project["id"])
                if isinstance(r, dict) and str(r.get("iconName") or "").strip()]
        return rows, [r["name"] for r in rows], {"amenities": [r["name"] for r in rows]}
    return _project_tool("get_amenities", project_id, build)


def get_construction_status(project_id: int) -> ToolResult:
    """Wing-level ``constructionStatus`` text only; percentages and dated
    updates need an AcroBuild endpoint."""
    def build(project):
        rows = [{"wing": _wing_label(w), "construction_status": w.get("constructionStatus")}
                for w in company_service.get_project_wings(project["id"]) if w.get("constructionStatus")]
        return rows, [f"{r['wing']}: {r['construction_status']}" for r in rows], {}
    return _project_tool("get_construction_status", project_id, build)


def get_possession(project_id: int) -> ToolResult:
    """Wing-level ``expectedPossesionDate`` (CS API spelling); unit-level and
    revised dates need an AcroBuild endpoint."""
    def build(project):
        rows = [{"wing": _wing_label(w), "expected_possession_date": _epoch_ms_to_date(w.get("expectedPossesionDate"))}
                for w in company_service.get_project_wings(project["id"])]
        rows = [r for r in rows if r["expected_possession_date"]]
        return rows, [f"{r['wing']}: {r['expected_possession_date']}" for r in rows], {}
    return _project_tool("get_possession", project_id, build)


def get_project_documents(project_id: int) -> ToolResult:
    """Typology ``imageUrl`` values only.

    What these images contain is unverified: docs/integrations/CS_API.md records
    the field as generic image content, and no live record has been checked, so
    callers must not present them as floor plans. Brochures, master plans and
    RERA documents need an AcroBuild endpoint."""
    def build(project):
        rows = [{"typology": t.get("typologyName") or t.get("typologyType"), "image_url": t.get("imageUrl"),
                 "content": "unverified"}
                for t in company_service.get_project_typologies(project["id"]) if t.get("imageUrl")]
        return rows, [f"{r['typology']}: {r['image_url']}" for r in rows], {}
    return _project_tool("get_project_documents", project_id, build)


def get_location_details(project_id: int) -> ToolResult:
    fields = ("address", "locality", "city", "latitude", "longitude", "location")

    def build(project):
        data = {key: project.get(key) for key in fields if project.get(key) not in (None, "")}
        return data, [f"{key}: {value}" for key, value in data.items()], {}
    return _project_tool("get_location_details", project_id, build)


def get_developer_details() -> ToolResult:
    """Company contact fields from GET /api/cs/{companyId}/company. History,
    awards and delivery track record are not exposed by the CS API."""
    fields = ("companyName", "businessName", "address", "city", "zipCode", "phoneNo",
              "contactEmail", "websiteUrl", "socialUrls")

    def body():
        # acrobuild_company_service has no public wrapper for /company.
        company = company_service._cached_request("/api/cs/company")
        if not isinstance(company, dict):
            return {}, [], []
        data = {key: company.get(key) for key in fields if company.get(key) not in (None, "")}
        lines = [f"{key}: {value}" for key, value in data.items()]
        return data, [_chunk("get_developer_details", "company", "Company contact details", lines)], []

    return _run("get_developer_details", body)


# -----------------------------------
# BLOCKED TOOLS
# -----------------------------------
# §33 tools whose data the CS API does not expose. They make no network call;
# callers must say the information is unavailable, never ask the LLM for it.

BLOCKED_TOOLS: dict[str, str] = {
    "calculate_cost_sheet": "AcroBuild pricing-engine endpoint (floor rise, PLC, parking, charges, taxes)",
    "get_price_history": "AcroBuild price-history endpoint",
    "get_active_offers": "AcroBuild offers endpoint (eligibility, validity, applicable units)",
    "get_payment_plan": "AcroBuild payment-plan endpoint",
    "get_nearby_places": "External maps/places provider",
    "get_distance": "External maps/distance provider",
    "get_travel_time": "External maps/directions provider",
    "get_available_site_visit_slots": "AcroBuild site-visit slot endpoint",
    "schedule_site_visit": "AcroBuild site-visit booking endpoint (local ticket fallback: POST /api/site-visits)",
    "schedule_revisit": "AcroBuild revisit endpoint and lead lookup",
    "create_lead": "AcroBuild lead endpoint",
    "update_lead": "AcroBuild lead endpoint",
    "request_callback": "AcroBuild callback/CRM endpoint (local ticket fallback: call_booking flow)",
    "get_customer_details": "AcroBuild customer lookup + verified customer identity",
    "get_payment_status": "AcroBuild finance/collection endpoint + verified customer identity",
    "get_documents": "AcroBuild customer-document endpoint + verified customer identity",
    "create_ticket": "AcroBuild ticket endpoint (local ticket fallback: POST /create_ticket)",
}


def blocked(tool: str) -> ToolResult:
    requirement = BLOCKED_TOOLS.get(tool)
    if requirement is None:
        return _result(tool, "invalid", "unavailable", error=f"Unknown blocked tool: {tool}")
    return _result(tool, "blocked", "unavailable", error=f"Not available yet; requires: {requirement}")
