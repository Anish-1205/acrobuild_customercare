"""Discovery slot memory over HTTP (Inquiry to Sales §28, §32), both assist endpoints.

Offline: acrobuild_company_service._cached_request is a fake that logs like the
real client (so the real live-data guard sees a real source_status), the turn
analyzer is stubbed, orchestration is canned (no LLM), and _request_json fails
the test if anything reaches the network.
"""
import copy
import json
import re

import pytest
from fastapi.testclient import TestClient

from app import api
from graph import haystack_conversation_pipeline as pipeline
from graph import main_orchestrator as orchestrator
from routers import assist
from services import acrobuild_company_service as company_service
from services import discovery_slot_service as discovery
from services import property_clarification_service as clarification
from services.conversation_store_service import (
    build_current_project_marker,
    build_discovery_slots_marker,
    get_current_project_context,
    get_discovery_slots,
    get_pending_project_lookup,
    latest_discovery_slots,
)
from services.internal_api_log_service import log_data_api_call
from services.turn_analysis_service import TurnAnalysis

ENDPOINTS = ["/api/support/assist", "/api/support/assist/stream"]
SQFT = "Rate Per Sq.Ft."
PROJECTS = [
    {"id": 1, "projectName": "Alpha Heights", "locality": "Wakad", "city": "Pune"},
    {"id": 2, "projectName": "Beta Residency", "locality": "", "city": "Thane"},
    {"id": 3, "projectName": "Gamma Park", "locality": "Hinjewadi", "city": "Pune"},
    {"id": 4, "projectName": "Delta Towers", "locality": "Wakad", "city": "Pune"},
    {"id": 5, "projectName": "Epsilon Homes", "locality": "Kalyan", "city": "Thane"},
    {"id": 55, "projectName": "GBK Group", "address": "someone@example.invalid"},
]
TYPOLOGIES = {
    1: [{"id": 11, "typologyName": "3BHK", "rateType": SQFT, "minBasePrice": 10000, "maxBasePrice": 12000,
         "saleableArea": 1200, "carpetArea": 900},
        {"id": 12, "typologyName": "2BHK", "rateType": SQFT, "minBasePrice": 9000, "maxBasePrice": 9500,
         "saleableArea": 800, "carpetArea": 600}],
    2: [{"id": 21, "typologyName": "3 BHK", "rateType": SQFT, "minBasePrice": 15000, "maxBasePrice": 16000,
         "saleableArea": 1300}],
    3: [{"id": 31, "typologyName": "3BHK", "rateType": "Lump sum", "minBasePrice": 9000000,
         "maxBasePrice": 9500000, "saleableArea": 1100}],
    4: [{"id": 41, "typologyName": "3BHK", "rateType": SQFT, "minBasePrice": 11000, "maxBasePrice": 11500,
         "saleableArea": 1500}],
    5: [{"id": 51, "typologyName": "1BHK", "rateType": SQFT, "minBasePrice": 8000, "maxBasePrice": 8500,
         "saleableArea": 600}],
}
WINGS = {1: [{"id": 101, "name": "A"}], 4: [{"id": 401, "name": "B"}]}
INVENTORY = {101: [{"unitNumber": 1501, "floorNumber": 15, "typologyName": "3BHK", "typologyId": 11,
                    "statusLabel": "Available"}]}
AMENITIES = {1: [{"iconName": "Swimming Pool", "type": "Amenities"}]}
AREAS_3BHK = ["Hinjewadi", "Thane", "Wakad"]
PROPERTY = TurnAnalysis("property", "English", "latin", "test")
CANNED = {"answer": "canned orchestration answer", "route": "general", "source_status": "live",
          "agent_mode": "live_remote_llm", "used_llm": True, "matched_chunks": [], "articles": [],
          "knowledge_documents": []}


class FakeCS:
    def __init__(self):
        self.calls = []
        self.fail = {}
        self.projects = PROJECTS

    def _route(self, path):
        if path == "/api/cs/company":
            return {"id": 16, "companyName": "Acme Builders"}
        if path == "/api/cs/projects":
            return self.projects
        match = re.fullmatch(r"/api/cs/projects/(\d+)/(typologies|wings|amenities)", path)
        if match:
            table = {"typologies": TYPOLOGIES, "wings": WINGS, "amenities": AMENITIES}[match.group(2)]
            return table.get(int(match.group(1)), [])
        match = re.fullmatch(r"/api/cs/wings/(\d+)/(inventory|typologies)", path)
        if match:
            if match.group(2) == "typologies":
                return [t for records in TYPOLOGIES.values() for t in records]
            return INVENTORY.get(int(match.group(1)), [])
        raise AssertionError(f"unexpected CS path {path}")

    def __call__(self, path, params=None, ttl_seconds=None):
        self.calls.append(path)
        error = self.fail.get(path)
        if error is not None:
            log_data_api_call(provider="Acrobuild CS API", endpoint=path, params=params, status="failed",
                              error=str(error))
            raise error
        log_data_api_call(provider="Acrobuild CS API", endpoint=path, params=params, status="completed")
        return copy.deepcopy(self._route(path))


class Chat:
    """A conversation driven through one endpoint with server-side history."""

    def __init__(self, client, endpoint, history):
        self.client = client
        self.endpoint = endpoint
        self.history = history

    def ask(self, question):
        response = self.client.post(self.endpoint, json={"issue": question, "conversation_id": "discovery-flow"})
        assert response.status_code == 200, response.text
        if not self.endpoint.endswith("stream"):
            return response.json()
        events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        if events[-1].get("response", {}).get("route") == "property":
            # Property answers are buffered: exactly one delta, then done.
            assert [event["type"] for event in events] == ["delta", "done"]
        return next(event["response"] for event in events if event["type"] == "done")

    @property
    def last_bot(self):
        return self.history[-1]["text"]

    @property
    def slots(self):
        return latest_discovery_slots(self.history)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", "true")
    fake = FakeCS()
    monkeypatch.setattr(company_service, "_cached_request", fake)
    monkeypatch.setattr(company_service, "_request_json",
                        lambda *a, **k: pytest.fail("no network calls in discovery flow tests"))
    monkeypatch.setattr(pipeline, "get_live_project_names",
                        lambda: [p["projectName"] for p in PROJECTS if p["id"] != 55])
    analysis = {"value": PROPERTY}
    monkeypatch.setattr(orchestrator, "analyze_turn", lambda *_a: analysis["value"])
    orchestration_calls = []

    def canned(**_kw):
        orchestration_calls.append(_kw.get("issue"))
        return dict(CANNED)

    monkeypatch.setattr(assist, "run_support_orchestration", canned)
    monkeypatch.setattr(assist, "stream_support_orchestration_events",
                        lambda **kw: iter([{"type": "done", "response": canned(**kw)}]))
    history = []

    class Session:
        def __init__(self, *_a):
            pass

        def set_cookie(self, *_a):
            pass

        def load(self):
            return list(history)

        def append(self, question, answer, marker=""):
            history.extend([{"sender": "customer", "text": question}, {"sender": "bot", "text": answer + marker}])

    monkeypatch.setattr(assist, "ConversationSession", Session)
    fake.analysis = analysis
    fake.orchestration_calls = orchestration_calls
    fake.history = history
    return fake


@pytest.fixture
def chat(env):
    def make(endpoint):
        return Chat(TestClient(api), endpoint, env.history)
    return make


def _labels(payload):
    return [reply["label"] for reply in payload.get("quick_replies") or []]


def _assert_live(payload):
    """Every discovery payload read live data and carries company_api evidence."""
    assert payload["source_status"] == "live_api"
    assert payload["matched_chunks"] and all(c["record_kind"] == "company_api" for c in payload["matched_chunks"])
    assert any(call["status"] == "completed" for call in payload["data_api_calls"])


def _to_budget_question(chat, locality="Wakad"):
    chat.ask("Show me 3 BHK")
    return chat.ask(locality)


def _to_results(chat):
    _to_budget_question(chat)
    return chat.ask("1.5 crore")


# -----------------------------------
# NAMED OPTIONS
# -----------------------------------

@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_locality_question_lists_live_options_and_any_area(chat, endpoint):
    c = chat(endpoint)
    payload = c.ask("Show me 3 BHK")
    assert payload["discovery_kind"] == "locality_question"
    assert payload["clarification_entity"] == "locality"
    assert payload["answer"] == "\n".join([
        "I found 3BHK projects in these areas:",
        *[f"- {area}" for area in AREAS_3BHK],
        "Which area would you like to explore?",
    ])
    assert _labels(payload) == AREAS_3BHK + ["Any area"]
    pending = get_pending_project_lookup(c.last_bot)
    assert pending["options"] == AREAS_3BHK and "Any area" not in pending["options"]
    assert pending["entity"] == "locality" and pending["purpose"] == "discovery" and pending["source"] == "discovery"
    assert c.slots == {"config": ["3"], "awaiting": "locality", "origin_issue": "Show me 3BHK"}
    assert get_current_project_context(c.last_bot) == {"project": ""}
    _assert_live(payload)


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_locality_question_reflects_current_eligible_projects(chat, env, endpoint):
    env.projects = [copy.deepcopy(PROJECTS[index]) for index in (0, 1, 4)]
    env.projects[0]["locality"] = "Baner"
    env.projects[1]["city"] = "Panvel"
    c = chat(endpoint)
    payload = c.ask("Show me 3 BHK")
    assert payload["answer"] == (
        "I found 3BHK projects in these areas:\n"
        "- Baner\n- Panvel\n"
        "Which area would you like to explore?"
    )
    assert payload["options"] == ["Baner", "Panvel"]
    assert _labels(payload) == ["Baner", "Panvel", "Any area"]
    assert get_pending_project_lookup(c.last_bot)["options"] == ["Baner", "Panvel"]
    _assert_live(payload)
    budget = c.ask("Baner")
    assert budget["discovery_kind"] == "budget_question"
    assert budget["answer"].startswith("What's your approximate budget for a 3BHK in Baner?")
    assert c.slots["locality"] == "Baner" and c.slots["awaiting"] == "budget"


# -----------------------------------
# SHORT FOLLOW-UPS
# -----------------------------------

@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("flag", [None, "true"], ids=["default-on", "explicit-on"])
def test_locality_budget_shortlist_and_project_tap(chat, monkeypatch, endpoint, flag):
    if flag is None:
        monkeypatch.delenv("ACROBUILD_DISCOVERY_SLOTS", raising=False)
    else:
        monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", flag)
    c = chat(endpoint)
    c.ask("Show me 3 BHK")
    budget = c.ask("Wakad")
    assert budget["discovery_kind"] == "budget_question"
    assert budget["answer"].startswith("What's your approximate budget for a 3BHK in Wakad?")
    assert budget["quick_replies"] == [{"label": "Any budget", "value": "any budget"}]
    assert c.slots["locality"] == "Wakad" and c.slots["awaiting"] == "budget"
    assert get_pending_project_lookup(c.last_bot) is None
    _assert_live(budget)

    results = c.ask("1.5 crore")
    assert results["discovery_kind"] == "results"
    assert "- Alpha Heights: estimated base amount from INR 1.20 crore" in results["answer"]
    assert discovery.DISCLAIMER in results["answer"]
    assert not re.search(r"\bprices?\b", results["answer"], re.I)
    assert _labels(results) == ["Alpha Heights"]
    pending = get_pending_project_lookup(c.last_bot)
    assert pending["purpose"] == "home_type_search" and pending["source"] == "discovery"
    assert c.slots["budget_max_inr"] == 15 * 10**6 and c.slots["awaiting"] is None
    _assert_live(results)

    tapped = c.ask("Alpha Heights")
    assert "Home types in Alpha Heights" in tapped["answer"]
    assert "discovery_kind" not in tapped
    assert c.slots["locality"] == "Wakad"  # slots survive a project selection


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_one_shot_query(chat, endpoint):
    c = chat(endpoint)
    payload = c.ask("3 BHK in Thane under 1.5 crore")
    assert payload["discovery_kind"] == "results"
    assert "No current 3BHK projects in Thane have an estimated base amount within about INR 1.50 crore." \
        in payload["answer"]
    assert _labels(payload) == ["Beta Residency"]
    assert c.slots["locality"] == "Thane" and c.slots["budget_max_inr"] == 15 * 10**6
    _assert_live(payload)


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_any_budget(chat, endpoint):
    c = chat(endpoint)
    _to_budget_question(c)
    payload = c.ask("any budget")
    assert _labels(payload) == ["Alpha Heights", "Delta Towers"]
    assert "Above your budget" not in payload["answer"]
    assert c.slots["budget_label"] == "any budget" and c.slots["budget_max_inr"] is None


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("reply", ["Any area", "anywhere"])
def test_any_area_goes_to_budget_question(chat, endpoint, reply):
    c = chat(endpoint)
    c.ask("Show me 3 BHK")
    payload = c.ask(reply)
    assert payload["discovery_kind"] == "budget_question"
    assert payload["answer"].startswith("What's your approximate budget for a 3BHK?")
    assert c.slots["locality"] == "any" and c.slots["awaiting"] == "budget"
    _assert_live(payload)


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_typed_city_that_is_not_an_option(chat, endpoint):
    c = chat(endpoint)
    first = c.ask("Show me 3 BHK")
    assert "Pune" not in first["options"]
    payload = c.ask("Pune")
    assert payload["discovery_kind"] == "budget_question"
    assert c.slots["locality"] == "Pune"


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_unknown_locality_is_honest_and_never_stored(chat, endpoint):
    c = chat(endpoint)
    c.ask("Show me 3 BHK")
    payload = c.ask("Kharadi")
    assert payload["discovery_kind"] == "locality_not_found"
    assert payload["answer"].startswith("I couldn't find any current 3BHK projects in 'Kharadi'.")
    assert payload["answer"].endswith("\n".join([
        "I found 3BHK projects in these areas:",
        *[f"- {area}" for area in AREAS_3BHK],
        "Which area would you like to explore?",
    ]))
    assert _labels(payload) == AREAS_3BHK + ["Any area"]
    assert get_pending_project_lookup(c.last_bot)["options"] == AREAS_3BHK
    stored = get_discovery_slots(c.last_bot)
    assert "Kharadi" not in json.dumps(stored) and "locality" not in stored
    assert "Kharadi" not in json.dumps(get_pending_project_lookup(c.last_bot))


# -----------------------------------
# REPEATED FAILURES
# -----------------------------------

@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_repeated_failures_at_locality_step(chat, env, endpoint):
    c = chat(endpoint)
    env.fail["/api/cs/projects"] = RuntimeError("CS API request timed out.")
    for question in ("Show me 3 BHK", "retry", "retry"):
        payload = c.ask(question)
        assert payload["source_status"] == "failed"
        assert "Live property data is unavailable" in payload["answer"]
        pending = get_pending_project_lookup(c.last_bot)
        assert pending["entity"] == "locality" and pending["options"] == []
        assert pending["original_issue"] == "Show me 3BHK"
        assert c.slots["config"] == ["3"]
    del env.fail["/api/cs/projects"]
    recovered = c.ask("retry")
    assert recovered["discovery_kind"] == "locality_question"
    assert recovered["options"] == AREAS_3BHK


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_repeated_failures_at_search_step(chat, env, endpoint):
    c = chat(endpoint)
    _to_budget_question(c)
    env.fail["/api/cs/projects"] = RuntimeError("CS API request timed out.")
    for question in ("1.5 crore", "retry", "retry"):
        payload = c.ask(question)
        assert payload["source_status"] == "failed"
        pending = get_pending_project_lookup(c.last_bot)
        assert pending["entity"] == "project" and pending["options"] == []
        assert pending["original_issue"] == "Show me 3BHK in Wakad within about INR 1.50 crore"
        assert c.slots["locality"] == "Wakad" and c.slots["budget_max_inr"] == 15 * 10**6
    del env.fail["/api/cs/projects"]
    recovered = c.ask("retry")
    assert recovered["discovery_kind"] == "results" and _labels(recovered) == ["Alpha Heights"]


# -----------------------------------
# INTENT PRESERVATION
# -----------------------------------

@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_new_configuration_reuses_locality_and_budget(chat, endpoint):
    c = chat(endpoint)
    _to_results(c)
    payload = c.ask("2 BHK?")
    assert payload["discovery_kind"] == "results"
    assert _labels(payload) == ["Alpha Heights"]
    assert "- Alpha Heights: estimated base amount from INR 72.00 lakh" in payload["answer"]
    assert c.slots["config"] == ["2"] and c.slots["locality"] == "Wakad"
    assert c.slots["budget_max_inr"] == 15 * 10**6


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_new_locality_overrides(chat, endpoint):
    c = chat(endpoint)
    _to_results(c)
    payload = c.ask("3 BHK in Pune")
    assert payload["discovery_kind"] == "results"
    assert _labels(payload) == ["Alpha Heights", "Gamma Park"]
    assert c.slots["locality"] == "Pune"


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_amenities_digression_keeps_slots(chat, endpoint):
    c = chat(endpoint)
    _to_budget_question(c)
    payload = c.ask("What amenities does Alpha Heights have?")
    assert "Swimming Pool" in payload["answer"]
    assert c.slots == {"config": ["3"], "locality": "Wakad", "awaiting": None, "origin_issue": "Show me 3BHK"}


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_current_project_bypasses_discovery(chat, env, endpoint):
    env.history.extend([
        {"sender": "customer", "text": "Tell me about Alpha Heights"},
        {"sender": "bot", "text": "Alpha Heights overview" + build_current_project_marker("Alpha Heights")},
    ])
    c = chat(endpoint)
    payload = c.ask("Show me 2 BHK")
    assert "discovery_kind" not in payload
    assert "Home types in Alpha Heights" in payload["answer"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_named_project_bypasses_discovery(chat, endpoint):
    payload = chat(endpoint).ask("Show me 3 BHK in Alpha Heights")
    assert "discovery_kind" not in payload
    assert "Home types in Alpha Heights" in payload["answer"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("label", [TurnAnalysis("general", "English", "latin", "test"),
                                   TurnAnalysis("general", "English", "latin", "test", unsure=True),
                                   TurnAnalysis("property", "English", "latin", "test", unsure=True)])
def test_budget_reply_is_forced_to_property(chat, env, endpoint, label):
    c = chat(endpoint)
    _to_budget_question(c)
    env.analysis["value"] = label
    payload = c.ask("1.5 crore")
    assert payload["discovery_kind"] == "results"
    assert env.orchestration_calls == []


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_non_budget_reply_is_not_forced(chat, env, endpoint):
    c = chat(endpoint)
    _to_budget_question(c)
    env.analysis["value"] = TurnAnalysis("general", "English", "latin", "test")
    payload = c.ask("hi there")
    assert payload["answer"] == CANNED["answer"]
    assert c.slots["awaiting"] is None and c.slots["locality"] == "Wakad"  # the question lapses, slots stay


# -----------------------------------
# CURRENT PROJECT NEVER SET BY DISCOVERY
# -----------------------------------

@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_one_match_result_does_not_set_current_project(chat, endpoint):
    c = chat(endpoint)
    budget = c.ask("Show me 2 BHK")   # only Alpha Heights lists 2BHK
    assert budget["discovery_kind"] == "budget_question"
    assert {chunk["project"]["projectName"] for chunk in budget["matched_chunks"]} == {"Alpha Heights"}
    assert budget["catalogue_home_type_search"] is True
    assert get_current_project_context(c.last_bot) == {"project": ""}
    results = c.ask("any budget")
    assert _labels(results) == ["Alpha Heights"]
    assert get_current_project_context(c.last_bot) == {"project": ""}


# -----------------------------------
# RESET + BROWSE
# -----------------------------------

@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("phrase", ["start over", "reset", "new search", "clear my preferences"])
def test_reset_phrases_clear_slots(chat, endpoint, phrase):
    c = chat(endpoint)
    _to_budget_question(c)
    c.ask(phrase)
    assert c.slots == {}
    assert get_discovery_slots(c.last_bot) == {}


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_browse_all_projects_starts_empty(chat, endpoint):
    c = chat(endpoint)
    _to_budget_question(c)
    payload = c.ask("Show me all projects")
    assert "Which one would you like to explore?" in payload["answer"]
    assert c.slots == {}


# -----------------------------------
# FLAG OFF = TODAY'S BEHAVIOUR
# -----------------------------------

@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("flag", ["false", "0", "off", ""])
def test_flag_off_keeps_the_project_list(chat, env, monkeypatch, endpoint, flag):
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", flag)
    c = chat(endpoint)
    payload = c.ask("Show me 3 BHK")
    names = [p["projectName"] for p in PROJECTS if p["id"] != 55]
    assert payload["answer"] == "Which project should I check?\n" + "\n".join(f"- {n}" for n in names)
    assert payload["pending_project_lookup"] == {"kind": "selection", "original_issue": "Show me 3BHK",
                                                 "entity": "project", "options": names, "scope": {}}
    assert "discovery_kind" not in payload and "discovery_slots" not in payload
    assert "catalogue_home_type_search" not in payload
    assert get_discovery_slots(c.last_bot) is None
    # Slots stored while the flag was on are ignored once it is off: a
    # budget-shaped reply is not forced to property and no marker is written.
    env.history.clear()
    env.history.extend([
        {"sender": "customer", "text": "Wakad"},
        {"sender": "bot", "text": "What's your approximate budget?" + build_discovery_slots_marker(
            {"config": ["3"], "locality": "Wakad", "awaiting": "budget"})},
    ])
    env.analysis["value"] = TurnAnalysis("general", "English", "latin", "test")
    payload = c.ask("1.5 crore")
    assert payload["answer"] == CANNED["answer"]
    assert env.orchestration_calls
    assert get_discovery_slots(c.last_bot) is None


# -----------------------------------
# LOCALIZATION
# -----------------------------------

@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_localized_locality_question_keeps_names_verbatim(chat, env, monkeypatch, endpoint):
    env.analysis["value"] = TurnAnalysis("property", "Telugu", "latin", "test")
    bullets = "\n".join(f"- {area}" for area in AREAS_3BHK)
    monkeypatch.setattr(orchestrator, "generate_qwen_chat_response",
                        lambda **_kw: "3BHK kosam edi area check cheyyali?\n" + bullets)
    payload = chat(endpoint).ask("Show me 3 BHK")
    assert payload["answer"] == "3BHK kosam edi area check cheyyali?\n" + bullets
    assert _labels(payload) == AREAS_3BHK + ["Any area"]
    monkeypatch.setattr(orchestrator, "generate_qwen_chat_response",
                        lambda **_kw: "3BHK kosam edi area?\n- Hinjevadi\n- Thane\n- Vakad")
    rejected = chat(endpoint).ask("Show me 3 BHK")
    assert "- Wakad" in rejected["answer"] and "Vakad" not in rejected["answer"]


# -----------------------------------
# SANITISE CONSISTENCY
# -----------------------------------

def test_dirty_locality_is_shown_identically_by_question_and_contract(env):
    env.projects = [
        {"id": 1, "projectName": "Alpha Heights", "locality": "Wa⁣kad", "city": "Pune"},
        {"id": 3, "projectName": "Gamma Park", "locality": "Hinje\x07wadi\n", "city": "Pune"},
        {"id": 2, "projectName": "Beta Residency", "locality": "\t", "city": "Tha\x00ne"},
    ]
    draft = discovery.build_discovery_answer("Show me 3 BHK", {}, None, [])
    assert draft["options"] == clarification.locality_options("Show me 3 BHK")
    assert draft["options"] == ["Hinje wadi", "Tha ne", "Wakad"]
    assert not any(re.search(r"[\x00-\x1f⁣]", option) for option in draft["options"])
    assert all(f"- {option}" in draft["answer"] for option in draft["options"])
