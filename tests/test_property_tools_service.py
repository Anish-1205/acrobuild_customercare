"""services/property_tools_service.py: typed CS API tools (Inquiry to Sales §33).

Fully offline: acrobuild_company_service._cached_request is replaced by a fake
that logs like the real client, and _request_json fails the test if reached.
"""
import ast
import copy
import re
from pathlib import Path

import pytest

import api_context
from services import acrobuild_company_service as company_service
from services import property_tools_service as tools
from services.internal_api_log_service import (
    begin_data_api_trace,
    end_data_api_trace,
    get_current_data_api_logs,
    log_data_api_call,
)

PROJECTS = [
    {"id": 1, "projectName": "Alpha Heights", "locality": "Wakad", "city": "Pune", "address": "Wakad Road, Pune",
     "estimatedStartDate": 1672531200000, "estimatedEndDate": 1767225600000,
     "latitude": "18.59", "longitude": "73.76"},
    {"id": 2, "projectName": "Beta Residency", "locality": "", "city": "Thane", "address": "Ghodbunder Road"},
    {"id": 3, "projectName": "Gamma Park", "locality": "Hinjewadi", "city": "Pune", "address": "Phase 1"},
    # Company record the CS API mixes into the project list; never customer-facing.
    {"id": 55, "projectName": "GBK Group", "address": "someone@example.invalid"},
]
TYPOLOGIES = {
    1: [{"id": 11, "typologyName": "3BHK", "rateType": "Rate Per Sq.Ft.", "minBasePrice": 10000,
         "maxBasePrice": 12000, "saleableArea": 1200, "carpetArea": 900, "imageUrl": "https://example.invalid/11.png"},
        {"id": 12, "typologyName": "2BHK", "rateType": "Rate Per Sq.Ft.", "minBasePrice": 9000,
         "maxBasePrice": 9500, "saleableArea": 800}],
    2: [{"id": 21, "typologyName": "3 BHK", "rateType": "Rate Per Sq.Ft.", "minBasePrice": 15000,
         "maxBasePrice": 16000, "saleableArea": 1300}],
    3: [{"id": 31, "typologyName": "3BHK", "rateType": "Lump sum", "minBasePrice": 9000000,
         "maxBasePrice": 9500000, "saleableArea": 1100}],
}
WINGS = {1: [{"id": 101, "name": "A", "constructionStatus": "Slab work", "expectedPossesionDate": 1798761600000}],
         2: [], 3: []}
INVENTORY = {101: [
    {"unitNumber": 1501, "floorNumber": 15, "typologyName": "3BHK", "typologyId": 11, "statusLabel": "Available",
     "carpetArea": 900, "saleableArea": 1200},
    {"unitNumber": 402, "floorNumber": 4, "typologyName": "2BHK", "typologyId": 12, "statusLabel": "Available",
     "carpetArea": 600, "saleableArea": 800},
]}
AMENITIES = {1: [{"iconName": "Swimming Pool", "type": "Amenities"}, {"iconName": " ", "type": "Facilities"}]}
COMPANY = {"id": 16, "companyName": "Acme Builders", "city": "Pune", "contactEmail": "info@example.invalid"}


def _route(path):
    if path == "/api/cs/company":
        return COMPANY
    if path == "/api/cs/projects":
        return PROJECTS
    match = re.fullmatch(r"/api/cs/projects/(\d+)/(typologies|wings|amenities)", path)
    if match:
        table = {"typologies": TYPOLOGIES, "wings": WINGS, "amenities": AMENITIES}[match.group(2)]
        return table.get(int(match.group(1)), [])
    match = re.fullmatch(r"/api/cs/wings/(\d+)/inventory", path)
    if match:
        return INVENTORY.get(int(match.group(1)), [])
    raise AssertionError(f"unexpected CS path {path}")


class FakeCS:
    """Stands in for acrobuild_company_service._cached_request and logs each
    call the way the real client does."""

    def __init__(self):
        self.calls = []
        self.fail = {}          # path -> exception to raise
        self.snapshot = set()   # paths served from the saved snapshot

    def __call__(self, path, params=None, ttl_seconds=None):
        self.calls.append(path)
        error = self.fail.get(path)
        if error is not None:
            if isinstance(error, RuntimeError):
                log_data_api_call(provider="Acrobuild CS API", endpoint=path, params=params,
                                  status="failed", error=str(error))
            raise error
        value = _route(path)
        if path in self.snapshot:
            log_data_api_call(provider="Acrobuild CS API snapshot", endpoint=path, params=params,
                              status="cached", cache_hit=True)
        else:
            log_data_api_call(provider="Acrobuild CS API", endpoint=path, params=params, status="completed")
        return copy.deepcopy(value)


@pytest.fixture
def cs(monkeypatch):
    fake = FakeCS()
    monkeypatch.setattr(company_service, "_cached_request", fake)
    monkeypatch.setattr(company_service, "_request_json",
                        lambda *a, **k: pytest.fail("tools must not reach the network in tests"))
    token = begin_data_api_trace("tools-test", "tool question")
    yield fake
    end_data_api_trace(token)


def _names(items):
    return [item["project"]["projectName"] for item in items]


# -----------------------------------
# SHAPE + CATALOGUE TOOLS
# -----------------------------------

def _assert_shape(result, tool):
    assert set(result) == {"tool", "status", "source_status", "data", "evidence", "skipped", "error"}
    assert result["tool"] == tool
    assert all(chunk["record_kind"] == "company_api" for chunk in result["evidence"])


def test_list_localities_uses_live_values_only(cs):
    result = tools.list_localities()
    _assert_shape(result, "list_localities")
    assert result["status"] == "ok" and result["source_status"] == "live_api"
    # locality when present, else city; the company record is excluded.
    assert result["data"] == ["Hinjewadi", "Thane", "Wakad"]
    assert not any("GBK" in chunk["body_text"] for chunk in result["evidence"])


@pytest.mark.parametrize("config,expected", [
    (["3"], ["Hinjewadi", "Thane", "Wakad"]),
    (["2"], ["Wakad"]),
    (["3BHK", 2], ["Wakad"]),
    (["5"], []),
])
def test_list_localities_filters_by_every_requested_config(cs, config, expected):
    result = tools.list_localities(config)
    assert result["data"] == expected
    assert result["status"] == ("ok" if expected else "empty")


def test_invalid_config_makes_no_call(cs):
    assert tools.list_localities(["7"])["status"] == "invalid"
    assert tools.search_projects(["penthouse"])["status"] == "invalid"
    assert cs.calls == []


def test_search_projects_buckets_by_estimated_base_amount(cs):
    result = tools.search_projects(["3"], "any", 15_000_000)
    _assert_shape(result, "search_projects")
    assert result["status"] == "ok" and result["source_status"] == "live_api"
    data = result["data"]
    assert data["locality_known"] is True
    assert _names(data["matches"]) == ["Alpha Heights"]
    assert data["matches"][0]["estimated_base_min_inr"] == 12_000_000
    assert data["matches"][0]["estimated_base_max_inr"] == 14_400_000
    assert _names(data["over_budget"]) == ["Beta Residency"]
    # A non per-sq.-ft. rate basis is never multiplied: reported, not priced.
    assert _names(data["unpriced"]) == ["Gamma Park"]
    assert {chunk["project"]["projectName"] for chunk in result["evidence"]} == {
        "Alpha Heights", "Beta Residency", "Gamma Park"}


def test_search_projects_locality_matches_locality_city_or_address(cs):
    assert _names(tools.search_projects(["3"], "wakad")["data"]["matches"]) == ["Alpha Heights"]
    pune = tools.search_projects(["3"], "Pune")["data"]
    assert _names(pune["matches"]) + _names(pune["unpriced"]) == ["Alpha Heights", "Gamma Park"]
    assert _names(tools.search_projects(["3"], "Ghodbunder Road")["data"]["matches"]) == ["Beta Residency"]


def test_search_projects_unknown_locality_is_empty_and_skips_typologies(cs):
    result = tools.search_projects(["3"], "Kharadi", 15_000_000)
    assert result["status"] == "empty"
    assert result["data"]["locality_known"] is False
    assert result["data"]["items"] == []
    assert not any("typologies" in path for path in cs.calls)


def test_search_projects_multi_config_needs_every_type(cs):
    data = tools.search_projects(["2", "3"])["data"]
    assert _names(data["items"]) == ["Alpha Heights"]
    assert {t["typologyName"] for t in data["items"][0]["typologies"]} == {"3BHK", "2BHK"}


@pytest.mark.parametrize("budget", [0, -5, True, 1.5, 10**11])
def test_search_projects_rejects_invalid_budget_without_calls(cs, budget):
    assert tools.search_projects(["3"], "", budget)["status"] == "invalid"
    assert cs.calls == []


def test_one_project_failure_is_partial_and_never_live(cs):
    cs.fail["/api/cs/projects/2/typologies"] = RuntimeError("CS API request timed out.")
    result = tools.search_projects(["3"])
    assert result["status"] == "partial"
    assert result["source_status"] == "failed"
    assert result["skipped"] == [{"project": "Beta Residency", "error": "CS API request timed out."}]
    assert "1 project(s) could not be checked." == result["error"]


# -----------------------------------
# PROJECT TOOLS
# -----------------------------------

def test_project_tools_read_live_records(cs):
    details = tools.get_project_details(1)
    assert details["status"] == "ok" and details["data"]["wings"][0]["name"] == "A"
    assert details["evidence"][0]["project"]["projectName"] == "Alpha Heights"

    history = tools.get_project_history(1)["data"]
    assert history == {"project_name": "Alpha Heights", "estimated_start_date": "2023-01-01",
                       "estimated_end_date": "2026-01-01"}

    assert [u["unitNumber"] for u in tools.search_inventory(1, ["3"])["data"]] == [1501]
    assert [u["unitNumber"] for u in tools.search_inventory(1, floor=4)["data"]] == [402]
    assert tools.search_inventory(1, ["3"])["data"][0]["wingName"] == "A"
    assert [u["floorNumber"] for u in tools.get_unit_details(1, "1501")["data"]] == [15]
    assert tools.get_unit_details(1, "999")["status"] == "empty"

    price = tools.get_live_price(1, ["3"])["data"]
    assert price == [{"typologyName": "3BHK", "typologyType": None, "rateType": "Rate Per Sq.Ft.",
                      "minBasePrice": 10000, "maxBasePrice": 12000, "carpetArea": 900, "saleableArea": 1200}]

    assert tools.get_amenities(1)["data"] == [{"name": "Swimming Pool", "type": "Amenities"}]
    assert tools.get_construction_status(1)["data"] == [{"wing": "A", "construction_status": "Slab work"}]
    assert tools.get_possession(1)["data"] == [{"wing": "A", "expected_possession_date": "2027-01-01"}]
    location = tools.get_location_details(1)["data"]
    assert location["locality"] == "Wakad" and location["latitude"] == "18.59"
    assert tools.get_developer_details()["data"]["companyName"] == "Acme Builders"


def test_typology_images_are_not_labelled_floor_plans(cs):
    result = tools.get_project_documents(1)
    assert result["data"] == [{"typology": "3BHK", "image_url": "https://example.invalid/11.png",
                               "content": "unverified"}]
    text = (str(result) + (tools.get_project_documents.__doc__ or "")).lower()
    assert "unverified" in text


def test_project_without_records_is_empty(cs):
    assert tools.get_construction_status(2)["status"] == "empty"
    assert tools.get_amenities(3)["status"] == "empty"


def test_unknown_project_is_empty_not_raised(cs):
    result = tools.get_amenities(999)
    assert result["status"] == "empty"
    assert "not in the live catalogue" in result["error"]


@pytest.mark.parametrize("bad_id", [0, -1, "abc", True, None, 1.5])
def test_invalid_project_id_makes_no_call(cs, bad_id):
    assert tools.get_project_details(bad_id)["status"] == "invalid"
    assert cs.calls == []


# -----------------------------------
# FAILURES: TOOLS NEVER RAISE
# -----------------------------------

PROJECT_TOOL_CALLS = [
    lambda: tools.get_project_details(1),
    lambda: tools.get_project_history(1),
    lambda: tools.search_inventory(1),
    lambda: tools.get_unit_details(1, "1501"),
    lambda: tools.get_live_price(1),
    lambda: tools.get_amenities(1),
    lambda: tools.get_construction_status(1),
    lambda: tools.get_possession(1),
    lambda: tools.get_project_documents(1),
    lambda: tools.get_location_details(1),
    lambda: tools.list_localities(["3"]),
    lambda: tools.search_projects(["3"], "Wakad", 15_000_000),
]


@pytest.mark.parametrize("call", PROJECT_TOOL_CALLS)
@pytest.mark.parametrize("error", [RuntimeError("CS API request timed out."), TimeoutError("timed out"),
                                   ConnectionResetError("reset")])
def test_catalogue_failure_is_unavailable_never_raised(cs, call, error):
    cs.fail["/api/cs/projects"] = error
    result = call()
    assert result["status"] == "unavailable"
    assert result["source_status"] == "failed"
    assert result["error"]


def test_raw_timeout_in_nested_call_is_unavailable(cs):
    cs.fail["/api/cs/projects/1/wings"] = TimeoutError("timed out")
    result = tools.get_possession(1)
    assert (result["status"], result["source_status"]) == ("unavailable", "failed")


def test_developer_details_failure_is_unavailable(cs):
    cs.fail["/api/cs/company"] = RuntimeError("Could not reach the CS API: offline")
    result = tools.get_developer_details()
    assert (result["status"], result["source_status"]) == ("unavailable", "failed")


# -----------------------------------
# SOURCE STATUS FROM LOG ENTRIES
# -----------------------------------

def _entry(provider, status, endpoint="/api/cs/projects", params=None):
    return {"provider": provider, "status": status, "endpoint": endpoint, "params": params or {}}


@pytest.mark.parametrize("entries,expected", [
    ([_entry("Acrobuild CS API", "completed")], "live_api"),
    ([_entry("Acrobuild CS API", "cached")], "live_api"),
    ([_entry("Acrobuild CS API", "failed")], "failed"),
    ([_entry("Acrobuild CS API", "completed"), _entry("Acrobuild CS API", "failed", "/api/cs/projects/1/wings")],
     "failed"),
    # A later successful retry of the same resource is authoritative.
    ([_entry("Acrobuild CS API", "failed"), _entry("Acrobuild CS API", "completed")], "live_api"),
    # A snapshot covering the failed endpoint is disclosed as snapshot, never live.
    ([_entry("Acrobuild CS API", "failed"), _entry("Acrobuild CS API snapshot", "cached")], "snapshot"),
    ([], "unavailable"),
])
def test_classify_source_status(entries, expected):
    assert tools.classify_source_status(entries) == expected


def test_snapshot_served_call_reports_snapshot(cs):
    cs.snapshot.add("/api/cs/projects")
    assert tools.get_location_details(1)["source_status"] == "snapshot"


def test_only_entries_added_during_the_call_count(cs):
    log_data_api_call(provider="Acrobuild CS API", endpoint="/api/cs/projects/9/wings", status="failed",
                      error="earlier, unrelated failure")
    assert tools.get_location_details(1)["source_status"] == "live_api"


def test_source_status_works_outside_an_assist_trace(monkeypatch):
    fake = FakeCS()
    monkeypatch.setattr(company_service, "_cached_request", fake)
    assert tools.get_location_details(1)["source_status"] == "live_api"
    fake.fail["/api/cs/projects"] = RuntimeError("offline")
    assert tools.get_location_details(1)["source_status"] == "failed"


# -----------------------------------
# LIVE-DATA GUARD INTEGRATION
# -----------------------------------

def test_tool_evidence_satisfies_live_data_guard(cs):
    result = tools.search_projects(["3"], "Wakad", 15_000_000)
    payload = {"route": "property", "answer": "Alpha Heights: estimated base amount from INR 1,20,00,000.",
               "matched_chunks": result["evidence"]}
    guarded = api_context._enforce_live_property_data(payload, "Show me 3 BHK", get_current_data_api_logs())
    assert guarded["source_status"] == "live_api"


def test_failed_tool_call_is_rejected_by_live_data_guard(cs):
    cs.fail["/api/cs/projects"] = RuntimeError("CS API request timed out.")
    result = tools.search_projects(["3"], "Wakad", 15_000_000)
    payload = {"route": "property", "answer": "Here are the matching projects.",
               "matched_chunks": result["evidence"]}
    guarded = api_context._enforce_live_property_data(payload, "Show me 3 BHK", get_current_data_api_logs())
    assert guarded["source_status"] == "failed"


# -----------------------------------
# BLOCKED TOOLS + SPEC COVERAGE
# -----------------------------------

SPEC_TOOLS = {  # Inquiry to Sales §33, in spec order
    "search_projects", "get_project_details", "get_developer_details", "get_project_history",
    "search_inventory", "get_unit_details", "get_live_price", "calculate_cost_sheet", "get_price_history",
    "get_active_offers", "get_payment_plan", "get_amenities", "get_construction_status", "get_possession",
    "get_project_documents", "get_location_details", "get_nearby_places", "get_distance", "get_travel_time",
    "get_available_site_visit_slots", "schedule_site_visit", "schedule_revisit", "create_lead", "update_lead",
    "request_callback", "get_customer_details", "get_payment_status", "get_documents", "create_ticket",
}


def test_every_spec_tool_is_implemented_or_blocked():
    implemented = {name for name in SPEC_TOOLS if callable(getattr(tools, name, None))}
    assert implemented | set(tools.BLOCKED_TOOLS) == SPEC_TOOLS
    assert not implemented & set(tools.BLOCKED_TOOLS)


@pytest.mark.parametrize("name", sorted(tools.BLOCKED_TOOLS))
def test_blocked_tools_make_zero_cs_calls(cs, name):
    result = tools.blocked(name)
    assert result["status"] == "blocked"
    assert result["source_status"] == "unavailable"
    assert result["error"].startswith("Not available yet; requires:")
    assert result["evidence"] == [] and result["data"] == []
    assert cs.calls == []
    assert get_current_data_api_logs() == []


def test_unknown_blocked_tool_is_invalid(cs):
    assert tools.blocked("book_helicopter")["status"] == "invalid"
    assert cs.calls == []


# -----------------------------------
# COMPILED RUNTIME ISOLATION
# -----------------------------------

def test_module_never_imports_compiled_runtime():
    source = Path(tools.__file__).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported.add(module)
            imported.update(f"{module}.{alias.name}" for alias in node.names)
    assert not any(name == "services.ai_agent_service" or name.startswith("services.ai_agent_service")
                   for name in imported)
    assert not any(name.startswith("graph") for name in imported)
