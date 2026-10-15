"""Locality matching when live data holds invisible characters (Inquiry to Sales §28, §32).

Options are shown cleaned (U+2063 removed, control characters as spaces,
whitespace collapsed); a tapped or typed option must match the live record it
came from, and the stored slot must be the cleaned live value. Offline: the CS
client is a logging fake and _request_json fails the test if reached.
"""
import copy
import re

import pytest

from services import acrobuild_company_service as company_service
from services import discovery_slot_service as discovery
from services import property_clarification_service as clarification
from services import property_tools_service as tools
from services.conversation_store_service import build_discovery_slots_marker, get_discovery_slots
from services.internal_api_log_service import begin_data_api_trace, end_data_api_trace, log_data_api_call

SQFT = "Rate Per Sq.Ft."
DIRTY_PROJECTS = [
    {"id": 1, "projectName": "Alpha Heights", "locality": "Wa⁣kad", "city": "Pune"},
    {"id": 3, "projectName": "Gamma Park", "locality": "Hinje\x07wadi", "city": "Pune"},
    {"id": 4, "projectName": "Delta Towers", "locality": "Pimple  Saudagar", "city": "Pune"},
    {"id": 2, "projectName": "Beta Residency", "locality": "", "city": "Thane"},
    {"id": 6, "projectName": "Zeta Enclave", "locality": "Wakad East", "city": "Pune"},
]
CLEAN_PROJECTS = [
    {"id": 1, "projectName": "Alpha Heights", "locality": "Wakad", "city": "Pune", "address": "Wakad Road"},
    {"id": 2, "projectName": "Beta Residency", "locality": "", "city": "Thane", "address": "Ghodbunder Road"},
    {"id": 3, "projectName": "Gamma Park", "locality": "Hinjewadi", "city": "Pune", "address": "Phase 1"},
    {"id": 4, "projectName": "Delta Towers", "locality": "Wakad", "city": "Pune"},
    {"id": 5, "projectName": "Epsilon Homes", "locality": "Kalyan", "city": "Thane"},
]
TYPOLOGIES = {pid: [{"id": pid * 10, "typologyName": "3BHK", "rateType": SQFT, "minBasePrice": 10000,
                     "saleableArea": 1000 + pid}] for pid in range(1, 7)}
DIRTY_OPTIONS = ["Hinje wadi", "Pimple Saudagar", "Thane", "Wakad", "Wakad East"]
AWAIT_LOCALITY = {"config": ["3"], "awaiting": "locality", "origin_issue": "Show me 3 BHK"}


class FakeCS:
    def __init__(self, projects):
        self.projects = projects
        self.calls = []

    def __call__(self, path, params=None, ttl_seconds=None):
        self.calls.append(path)
        log_data_api_call(provider="Acrobuild CS API", endpoint=path, params=params, status="completed")
        if path == "/api/cs/projects":
            return copy.deepcopy(self.projects)
        match = re.fullmatch(r"/api/cs/projects/(\d+)/typologies", path)
        if match:
            return copy.deepcopy(TYPOLOGIES.get(int(match.group(1)), []))
        raise AssertionError(f"unexpected CS path {path}")


def _install(monkeypatch, projects):
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", "true")
    fake = FakeCS(projects)
    monkeypatch.setattr(company_service, "_cached_request", fake)
    monkeypatch.setattr(company_service, "_request_json", lambda *a, **k: pytest.fail("no network in tests"))
    return fake


@pytest.fixture
def dirty(monkeypatch):
    fake = _install(monkeypatch, DIRTY_PROJECTS)
    token = begin_data_api_trace("sanitise-test", "q")
    yield fake
    end_data_api_trace(token)


@pytest.fixture
def clean(monkeypatch):
    fake = _install(monkeypatch, CLEAN_PROJECTS)
    token = begin_data_api_trace("sanitise-clean-test", "q")
    yield fake
    end_data_api_trace(token)


def _build(issue, slots=None, pending=None):
    return discovery.build_discovery_answer(issue, slots, pending, [p["projectName"] for p in DIRTY_PROJECTS])


def _names(result, bucket="items"):
    return [item["project"]["projectName"] for item in result["data"][bucket]]


# -----------------------------------
# ONE CLEANING RULE (duplicated, pinned)
# -----------------------------------

SAMPLES = ["Wakad", "Wa⁣kad", "Hinje\x07wadi", "Pimple  Saudagar", "\tThane\n", "⁣", "", None,
           "Ambernath\x85East", "Kal\x7fyan", "  Badlapur   West ", "Ghod⁣bunder\x00Road", 42]


@pytest.mark.parametrize("value", SAMPLES)
def test_cleaning_rule_is_identical_everywhere(value):
    expected = clarification._clean_option_text(value)
    assert tools.clean_place_text(value) == expected
    assert discovery._clean(value) == expected


# -----------------------------------
# TAP / TYPE MATCHES THE LIVE RECORD
# -----------------------------------

@pytest.mark.parametrize("live,shown,project", [
    ("Wa⁣kad", "Wakad", "Alpha Heights"),
    ("Hinje\x07wadi", "Hinje wadi", "Gamma Park"),
    ("Pimple  Saudagar", "Pimple Saudagar", "Delta Towers"),
])
def test_shown_option_resumes_and_matches(dirty, live, shown, project):
    question = _build("Show me 3 BHK")
    assert question["discovery_kind"] == "locality_question"
    assert question["options"] == DIRTY_OPTIONS and shown in question["options"]
    assert f"- {shown}" in question["answer"]

    pending = question["pending_project_lookup"]
    assert clarification.continues_selection(pending, shown)          # a tap on the shown option
    effective = clarification.resume_selection(pending, shown)
    budget = _build(effective, question["discovery_slots"], pending)
    assert budget["discovery_kind"] == "budget_question"
    assert budget["discovery_slots"]["locality"] == shown
    assert {chunk["project"]["projectName"] for chunk in budget["matched_chunks"]} == {project}

    typed = _build(shown.lower(), AWAIT_LOCALITY)
    assert typed["discovery_slots"]["locality"] == shown

    assert _names(tools.search_projects(["3"], shown)) == [project]
    stored = get_discovery_slots(build_discovery_slots_marker(budget["discovery_slots"]))
    assert stored["locality"] == shown
    assert live != shown and live not in str(stored)


def test_results_are_scoped_to_the_cleaned_locality(dirty):
    results = _build("any budget", {"config": ["3"], "locality": "Wakad", "awaiting": "budget"})
    assert results["discovery_kind"] == "results"
    assert results["options"] == ["Alpha Heights"]


# -----------------------------------
# NO OVER-MATCHING, UNKNOWN TEXT STILL HONEST
# -----------------------------------

@pytest.mark.parametrize("locality,expected", [
    ("Wakad", ["Alpha Heights"]),            # not "Wakad East"
    ("Wakad East", ["Zeta Enclave"]),
    ("Pune", ["Alpha Heights", "Gamma Park", "Delta Towers", "Zeta Enclave"]),
    ("Thane", ["Beta Residency"]),
    ("Wakadd", []), ("Kad", []), ("Pimple", []), ("Saudagar", []), ("Hinje", []),
])
def test_no_over_matching(dirty, locality, expected):
    result = tools.search_projects(["3"], locality)
    assert _names(result) == expected
    assert result["data"]["locality_known"] is bool(expected)


def test_unknown_text_still_gets_not_found(dirty):
    draft = _build("Kharadi", AWAIT_LOCALITY)
    assert draft["discovery_kind"] == "locality_not_found"
    assert draft["answer"].startswith("I couldn't find any listed 3BHK projects in 'Kharadi'.")
    assert "locality" not in draft["discovery_slots"]


# -----------------------------------
# QUESTION, CONTRACT AND MATCHING INDEX AGREE
# -----------------------------------

def test_contract_discovery_and_index_agree_on_dirty_data(dirty):
    question = _build("Show me 3 BHK")
    assert clarification.locality_options("Show me 3 BHK") == question["options"] == DIRTY_OPTIONS
    items = tools.search_projects(["3"], "any")["data"]["items"]
    index = discovery._place_index(items)
    for option in question["options"]:
        assert index[discovery._norm(option)] == option          # every shown option is matchable as shown
    assert all(not re.search(r"[\x00-\x1f\x7f-\x9f⁣]", value) and "  " not in value
               for value in index.values())


# -----------------------------------
# CLEAN DATA: IDENTICAL TO BEFORE
# -----------------------------------

def _old_project_localities(project):
    """The Step 1 implementation, kept here as the regression reference."""
    return {str(project.get(key) or "").strip() for key in ("locality", "city")
            if str(project.get(key) or "").strip()}


def _old_project_in_locality(project, locality):
    wanted = str(locality or "").strip().lower()
    if not wanted:
        return False
    if wanted in {value.lower() for value in _old_project_localities(project)}:
        return True
    address = " ".join(str(project.get(key) or "") for key in ("address", "location")).lower()
    return bool(re.search(r"\b" + re.escape(wanted) + r"\b", address))


QUERIES = ["Wakad", "wakad", " WAKAD ", "Pune", "Thane", "Hinjewadi", "Kalyan", "Ghodbunder Road", "Road",
           "Phase 1", "Kharadi", "", "any", "Wak", "wakad road"]


@pytest.mark.parametrize("project", CLEAN_PROJECTS, ids=lambda p: p["projectName"])
def test_clean_data_matches_exactly_as_before(project):
    assert tools.project_localities(project) == _old_project_localities(project)
    for query in QUERIES:
        assert tools.project_in_locality(project, query) is _old_project_in_locality(project, query), query


def test_clean_data_discovery_output_unchanged(clean):
    question = discovery.build_discovery_answer("Show me 3 BHK", None, None, [])
    assert question["options"] == ["Hinjewadi", "Kalyan", "Thane", "Wakad"]
    budget = discovery.build_discovery_answer("wakad", AWAIT_LOCALITY, None, [])
    assert budget["discovery_slots"]["locality"] == "Wakad"
    assert {c["project"]["projectName"] for c in budget["matched_chunks"]} == {"Alpha Heights", "Delta Towers"}
    assert _names(tools.search_projects(["3"], "Wakad")) == ["Alpha Heights", "Delta Towers"]
