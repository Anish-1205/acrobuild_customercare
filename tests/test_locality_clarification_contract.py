"""The "locality" clarification entity and the discovery_prompt guard in
services/property_clarification_service.py (Inquiry to Sales §28, §32).

Offline: acrobuild_company_service._cached_request is a fake that logs like the
real client, and _request_json fails the test if it is ever reached.
"""
import ast
import copy
import re
import subprocess
import sys
from pathlib import Path

import pytest

from graph import main_orchestrator
from graph.main_orchestrator import localize_response
from routers import assist
from services import acrobuild_company_service as company_service
from services import discovery_slot_service as discovery
from services import property_clarification_service as clarification
from services import property_tools_service as tools
from services.conversation_store_service import build_pending_project_lookup_marker, get_pending_project_lookup
from services.internal_api_log_service import begin_data_api_trace, end_data_api_trace, log_data_api_call
from services.project_home_type_service import requested_home_types
from services.turn_analysis_service import TurnAnalysis

ROOT = Path(__file__).resolve().parent.parent
SQFT = "Rate Per Sq.Ft."
PROJECTS = [
    {"id": 1, "projectName": "Alpha Heights", "locality": "Wakad", "city": "Pune"},
    {"id": 2, "projectName": "Beta Residency", "locality": "", "city": "Thane"},
    {"id": 3, "projectName": "Gamma Park", "locality": "Hinjewadi", "city": "Pune"},
    {"id": 4, "projectName": "Delta Towers", "locality": "Wakad", "city": "Pune"},
    {"id": 5, "projectName": "Epsilon Homes", "locality": "Kalyan", "city": "Thane"},
    {"id": 6, "projectName": "Zeta Enclave", "locality": "aundh", "city": "Pune"},
    {"id": 55, "projectName": "GBK Group", "address": "someone@example.invalid"},
]
TYPOLOGIES = {
    1: [{"id": 11, "typologyName": "3BHK", "rateType": SQFT, "minBasePrice": 10000, "saleableArea": 1200},
        {"id": 12, "typologyName": "2BHK", "rateType": SQFT, "minBasePrice": 9000, "saleableArea": 800}],
    2: [{"id": 21, "typologyName": "3 BHK", "rateType": SQFT, "minBasePrice": 15000, "saleableArea": 1300}],
    3: [{"id": 31, "typologyName": "3BHK", "rateType": "Lump sum", "minBasePrice": 9000000, "saleableArea": 1100}],
    4: [{"id": 41, "typologyName": "3BHK", "rateType": SQFT, "minBasePrice": 11000, "saleableArea": 1500}],
    5: [{"id": 51, "typologyName": "1BHK", "rateType": SQFT, "minBasePrice": 8000, "saleableArea": 600}],
    6: [{"id": 61, "typologyName": "3BHK", "rateType": SQFT, "minBasePrice": 9500, "saleableArea": 1250}],
}
WINGS = {1: [{"id": 101, "name": "IRIS"}, {"id": 102, "name": "TULIP"}]}
AREAS_3BHK = ["aundh", "Hinjewadi", "Thane", "Wakad"]      # case-insensitive order, Thane via city
AREAS_ALL = ["aundh", "Hinjewadi", "Kalyan", "Thane", "Wakad"]
LOCALITY_PAYLOAD = {"clarification_entity": "locality", "route": "property", "answer": ""}


def _route(path, projects):
    if path == "/api/cs/projects":
        return projects
    match = re.fullmatch(r"/api/cs/projects/(\d+)/(typologies|wings)", path)
    if match:
        table = TYPOLOGIES if match.group(2) == "typologies" else WINGS
        return table.get(int(match.group(1)), [])
    raise AssertionError(f"unexpected CS path {path}")


class FakeCS:
    def __init__(self):
        self.calls = []
        self.fail = {}
        self.projects = PROJECTS

    def __call__(self, path, params=None, ttl_seconds=None):
        self.calls.append(path)
        error = self.fail.get(path)
        if error is not None:
            log_data_api_call(provider="Acrobuild CS API", endpoint=path, params=params, status="failed",
                              error=str(error))
            raise error
        log_data_api_call(provider="Acrobuild CS API", endpoint=path, params=params, status="completed")
        return copy.deepcopy(_route(path, self.projects))


@pytest.fixture
def cs(monkeypatch):
    fake = FakeCS()
    monkeypatch.setattr(company_service, "_cached_request", fake)
    monkeypatch.setattr(company_service, "_request_json",
                        lambda *a, **k: pytest.fail("the contract must not reach the network in tests"))
    token = begin_data_api_trace("locality-contract-test", "question")
    yield fake
    end_data_api_trace(token)


# -----------------------------------
# clarification_entity()
# -----------------------------------

def test_explicit_locality_is_accepted():
    assert clarification.clarification_entity({"clarification_entity": "locality"}) == "locality"


@pytest.mark.parametrize("entity", ["project", "wing", "floor", "flat", "home_type"])
def test_existing_explicit_entities_unchanged(entity):
    assert clarification.clarification_entity({"clarification_entity": entity}) == entity


@pytest.mark.parametrize("payload,expected", [
    ({"answer": "Which project would you like me to check?"}, "project"),
    ({"answer": "Please share the project name, tower or block, and unit number."}, "project"),
    ({"answer": "Choose a wing to continue."}, "wing"),
    ({"answer": "Which tower should I check?"}, "wing"),
    ({"answer": "Which floor would you like to explore?"}, "floor"),
    ({"answer": "Which flat did you mean?"}, "flat"),
    ({"answer": "Which unit should I check?"}, "flat"),
    ({"answer": "Please choose another available home type or floor."}, "home_type"),
    ({"answer": "Which configuration do you prefer?"}, "home_type"),
    ({"answer": "Vishwajeet Prime is in Badlapur."}, None),
    ({"answer": "", "pending_project_lookup": "amenities"}, "project"),
    ({"answer": "", "clarification_entity": "budget"}, None),
    # The area question is only ever explicit; its prose is not detected.
    ({"answer": "Which area should I check?\n- Wakad"}, None),
])
def test_prose_detector_regressions(payload, expected):
    assert clarification.clarification_entity(payload) == expected


# -----------------------------------
# live_options(): locality branch
# -----------------------------------

def test_locality_options_named_deduplicated_ordered(cs):
    assert clarification.live_options("locality", "Show me 3 BHK", []) == ("locality", AREAS_3BHK, {})


@pytest.mark.parametrize("issue,expected", [
    ("Show me 2 BHK", ["Wakad"]),
    ("Show me 2bhks and 3 bhk", ["Wakad"]),
    ("Show me 1 BHK", ["Kalyan"]),
    ("Show me 5 BHK", []),
    ("Show me homes", AREAS_ALL),
])
def test_locality_options_follow_the_requested_config(cs, issue, expected):
    assert clarification.live_options("locality", issue, [])[1] == expected


def test_city_is_used_when_locality_is_blank(cs):
    assert "Thane" in clarification.live_options("locality", "Show me 3 BHK", [])[1]
    assert "Pune" not in clarification.live_options("locality", "Show me 3 BHK", [])[1]


def test_locality_branch_reads_only_projects_and_typologies(cs):
    clarification.live_options("locality", "Show me 3 BHK", [])
    assert cs.calls[0] == "/api/cs/projects"
    assert all(path == "/api/cs/projects" or path.endswith("/typologies") for path in cs.calls)


def test_option_text_is_stripped_of_marker_and_control_characters(cs):
    cs.projects = [{"id": 1, "projectName": "Alpha Heights", "locality": "Wa⁣kad\n", "city": "Pune"},
                   {"id": 3, "projectName": "Gamma Park", "locality": "\tHinje\x07wadi", "city": "Pune"}]
    options = clarification.live_options("locality", "Show me 3 BHK", [])[1]
    assert options == ["Hinje wadi", "Wakad"]
    assert not any("⁣" in option or re.search(r"[\x00-\x1f]", option) for option in options)


def test_empty_catalogue_is_reported_honestly(cs):
    cs.projects = []
    result = clarification.apply_clarification_contract(dict(LOCALITY_PAYLOAD), "Show me 3 BHK")
    assert result["answer"] == ("The live data currently lists no matching area options for this request. "
                                "Please try again later.")
    assert result["pending_project_lookup"]["options"] == []
    assert result["quick_replies"] == []


def test_unavailable_tool_raises_like_other_live_reads(cs, monkeypatch):
    monkeypatch.setattr(tools, "search_projects", lambda *a, **k: tools.blocked("search_projects"))
    with pytest.raises(RuntimeError):
        clarification.live_options("locality", "Show me 3 BHK", [])


def test_home_type_pattern_matches_requested_home_types():
    for text in ("3 BHK", "3bhks", "2 bhk and 3BHK", "Show me 3 B H K", "7 bhk", "4bk", "none"):
        assert list(dict.fromkeys(clarification._HOME_TYPE_NUMBER_RE.findall(text))) == requested_home_types(text)


# -----------------------------------
# COPY
# -----------------------------------

def test_area_question_copy_and_state(cs):
    result = clarification.apply_clarification_contract(dict(LOCALITY_PAYLOAD), "Show me 3 BHK")
    assert result["answer"] == "Which area should I check?\n" + "\n".join(f"- {area}" for area in AREAS_3BHK)
    assert result["clarification_entity"] == "locality"
    assert result["quick_replies"] == [{"label": area, "value": area} for area in AREAS_3BHK]
    assert result["pending_project_lookup"] == {
        "kind": "selection", "original_issue": "Show me 3 BHK", "entity": "locality",
        "options": AREAS_3BHK, "scope": {}, "purpose": "discovery"}
    assert result["source_status"] == "live_api" and result["used_llm"] is False


def test_unmatched_reply_re_asks_the_area(cs):
    state = {"kind": "selection", "original_issue": "Show me 3 BHK", "entity": "locality",
             "options": AREAS_3BHK, "scope": {}, "purpose": "discovery"}
    result = clarification.build_unmatched_selection_answer(state)
    assert result["answer"] == ("That doesn't match any area option. Which area should I check?\n"
                                + "\n".join(f"- {area}" for area in AREAS_3BHK))
    assert result["pending_project_lookup"]["purpose"] == "discovery"
    assert result["clarification_entity"] == "locality"


def test_area_bullets_survive_localization_verbatim(cs, monkeypatch):
    payload = clarification.apply_clarification_contract(dict(LOCALITY_PAYLOAD), "Show me 3 BHK")
    bullets = "\n".join(f"- {area}" for area in AREAS_3BHK)
    analysis = TurnAnalysis("property", "Telugu", "latin", "test")
    monkeypatch.setattr(main_orchestrator, "generate_qwen_chat_response",
                        lambda **_kwargs: "Edi area check cheyyali?\n" + bullets)
    localized = localize_response(payload, analysis)
    assert localized["answer"] == "Edi area check cheyyali?\n" + bullets
    assert localized["quick_replies"] == payload["quick_replies"]
    # A translation that renames an area is rejected, never shown.
    monkeypatch.setattr(main_orchestrator, "generate_qwen_chat_response",
                        lambda **_kwargs: "Edi area?\n- Aundh\n- Hinjewadi\n- Thane\n- Vakad")
    assert localize_response(payload, analysis)["answer"] == payload["answer"]


# -----------------------------------
# discovery_prompt GUARD + DRAFT PASS-THROUGH
# -----------------------------------

def test_discovery_prompt_is_returned_untouched_with_zero_calls(cs):
    # This copy would trip the prose detector ("share ... flat") without the guard.
    copy_text = "What's your approximate budget? Please share your budget for the flat."
    assert clarification.clarification_entity({"answer": copy_text}) == "flat"
    payload = {"answer": copy_text, "route": "property", "discovery_prompt": "budget"}
    result = clarification.apply_clarification_contract(payload, "1.5 crore")
    assert result is payload and "pending_project_lookup" not in result
    assert cs.calls == []


@pytest.mark.parametrize("turns", [
    [("Show me 3 BHK", None)],                                                      # locality question
    [("Wakad", {"config": ["3"], "awaiting": "locality", "origin_issue": "Show me 3 BHK"})],   # budget question
    [("1.5 crore", {"config": ["3"], "locality": "Wakad", "awaiting": "budget"})],             # results
    [("Kharadi", {"config": ["3"], "awaiting": "locality", "origin_issue": "Show me 3 BHK"})],  # not found
])
def test_discovery_drafts_pass_through_unchanged_with_zero_calls(cs, monkeypatch, turns):
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", "true")
    issue, slots = turns[0]
    draft = discovery.build_discovery_answer(issue, slots, None, [p["projectName"] for p in PROJECTS])
    before = copy.deepcopy(draft)
    cs.calls.clear()
    result = clarification.apply_clarification_contract(draft, issue, [])
    assert result is draft and result == before
    assert cs.calls == []


# -----------------------------------
# REPEATED FAILURES
# -----------------------------------

def test_repeated_failures_keep_the_request_without_a_retry_cap(cs):
    original = "Show me 3 BHK homes, ideally near a school"
    cs.fail["/api/cs/projects"] = RuntimeError("CS API request timed out.")
    expected = {"kind": "selection", "original_issue": original, "entity": "locality", "options": [],
                "scope": {}, "purpose": "discovery"}
    restored = None
    for _ in range(3):
        result = clarification.apply_clarification_contract(dict(LOCALITY_PAYLOAD), original)
        assert result["source_status"] == "failed"
        assert result["answer"].startswith("I could not fetch the live selection options right now.")
        assert result["pending_project_lookup"] == expected
        restored = get_pending_project_lookup(build_pending_project_lookup_marker(result["pending_project_lookup"]))
        assert restored == expected
    for _ in range(3):
        restored = get_pending_project_lookup(assist._project_lookup_marker({"source_status": "failed"},
                                                                          restored, "retry"))
        assert restored == expected
        assert clarification.resume_selection(restored, "retry") == original
    del cs.fail["/api/cs/projects"]
    retried = clarification.apply_clarification_contract(dict(LOCALITY_PAYLOAD),
                                                         clarification.resume_selection(restored, "retry"))
    assert retried["pending_project_lookup"]["options"] == AREAS_3BHK


def test_unmatched_re_ask_failure_raises_like_other_entities(cs):
    cs.fail["/api/cs/projects"] = RuntimeError("CS API request timed out.")
    state = {"kind": "selection", "original_issue": "Show me 3 BHK", "entity": "locality",
             "options": AREAS_3BHK, "scope": {}, "purpose": "discovery"}
    with pytest.raises(RuntimeError):
        clarification.build_unmatched_selection_answer(state)


# -----------------------------------
# CONSISTENCY WITH THE DISCOVERY DRAFT
# -----------------------------------

def test_contract_options_equal_discovery_question_options(cs, monkeypatch):
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", "true")
    names = [p["projectName"] for p in PROJECTS]
    draft = discovery.build_discovery_answer("Show me 3 BHK", None, None, names)
    assert draft["discovery_kind"] == "locality_question"
    assert clarification.live_options("locality", "Show me 3 BHK", [])[1] == draft["options"]
    assert draft["pending_project_lookup"]["options"] == draft["options"]
    not_found = discovery.build_discovery_answer(
        "Kharadi", {"config": ["3"], "awaiting": "locality", "origin_issue": "Show me 3 BHK"}, None, names)
    assert not_found["options"] == draft["options"]


@pytest.mark.parametrize("config,issue", [(["2"], "Show me 2 BHK"), (["1"], "1bhk"), ([], "Show me homes"),
                                           (["3"], "3bhks please")])
def test_contract_options_equal_discovery_display_values(cs, config, issue):
    items = tools.search_projects(config, "any")["data"]["items"]
    assert clarification.live_options("locality", issue, [])[1] == discovery._display_localities(items)


# -----------------------------------
# EXISTING ENTITIES KEEP THEIR SHAPE
# -----------------------------------

def test_existing_entity_states_gain_no_new_keys(cs):
    project = clarification.apply_clarification_contract({"clarification_entity": "project", "answer": ""},
                                                         "Check possession date")
    assert set(project["pending_project_lookup"]) == {"kind", "original_issue", "entity", "options", "scope"}
    assert project["answer"].splitlines()[0] == "Which project should I check?"
    wing = clarification.apply_clarification_contract({"clarification_entity": "wing", "answer": ""},
                                                      "Construction status in Alpha Heights")
    assert wing["pending_project_lookup"] == {"kind": "selection", "original_issue": "Construction status in Alpha Heights",
                                              "entity": "wing", "options": ["IRIS", "TULIP"],
                                              "scope": {"project": "Alpha Heights"}}
    assert wing["answer"] == "Which wing should I check in Alpha Heights?\n- IRIS\n- TULIP"


def test_existing_entity_failure_state_unchanged(cs):
    cs.fail["/api/cs/projects"] = RuntimeError("offline")
    result = clarification.apply_clarification_contract({"clarification_entity": "project", "answer": ""}, "q")
    assert result["pending_project_lookup"] == {"kind": "selection", "original_issue": "q", "entity": "project",
                                                "options": [], "scope": {}}


# -----------------------------------
# IMPORT-CYCLE GUARD
# -----------------------------------

def test_contract_never_imports_the_discovery_module():
    tree = ast.parse(Path(clarification.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported.add(module)
            imported.update(f"{module}.{alias.name}" for alias in node.names)
    assert not any("discovery_slot_service" in name for name in imported)


@pytest.mark.parametrize("order", [
    ("services.property_clarification_service", "services.discovery_slot_service"),
    ("services.discovery_slot_service", "services.property_clarification_service"),
    ("services.project_home_type_service", "services.discovery_slot_service"),
])
def test_modules_import_cleanly_in_a_fresh_interpreter(order):
    code = "import importlib\n" + "\n".join(f"importlib.import_module({name!r})" for name in order)
    completed = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stderr[-2000:]
