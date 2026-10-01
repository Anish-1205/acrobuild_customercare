"""Step 7b: the two defects found by the live acceptance run (Step 7), both endpoints.

Defect 1 (live T7): with a project in context, "3 BHK in Thane" was answered as
"Home types in <that project>" and the discovery search never ran.
Defect 2 (live T8): a bare "start over" went to the general LLM, which invented a
place from stale history.

Offline: acrobuild_company_service._cached_request is a fake that logs like the
real client, the turn analyzer is stubbed, orchestration is canned, and any
general-LLM call or network request fails the test.
"""
import copy
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_context
from app import api
from graph import haystack_conversation_pipeline as pipeline
from graph import main_orchestrator as orchestrator
from routers import assist
from services import acrobuild_company_service as company_service
from services import discovery_slot_service as discovery
from services.conversation_store_service import (
    build_current_project_marker,
    build_discovery_slots_marker,
    get_current_project_context,
    get_discovery_slots,
    latest_discovery_slots,
)
from services.internal_api_log_service import log_data_api_call
from services.turn_analysis_service import TurnAnalysis

ENDPOINTS = ["/api/support/assist", "/api/support/assist/stream"]
REPO = Path(__file__).resolve().parents[1]
SQFT = "Rate Per Sq.Ft."
PROJECTS = [
    {"id": 1, "projectName": "Alpha Heights", "locality": "Wakad", "city": "Pune"},
    {"id": 2, "projectName": "Beta Residency", "locality": "", "city": "Thane"},
    {"id": 3, "projectName": "Gamma Park", "locality": "Hinjewadi", "city": "Pune"},
    {"id": 4, "projectName": "Delta Towers", "locality": "Wakad", "city": "Pune"},
    {"id": 5, "projectName": "Epsilon Homes", "locality": "Kalyan", "city": "Thane"},
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
PLACES = ["Wakad", "Pune", "Hinjewadi", "Thane", "Kalyan"]
PROPERTY = TurnAnalysis("property", "English", "latin", "test")
GENERAL = TurnAnalysis("general", "English", "latin", "test")
# The live analyzer called a bare "start over" general (Step 7, T8); a property label must work too.
ANALYSES = pytest.mark.parametrize("analysis", [GENERAL, PROPERTY], ids=["general", "property"])
CANNED = {"answer": "canned orchestration answer", "route": "general", "source_status": "live",
          "agent_mode": "live_remote_llm", "used_llm": True, "matched_chunks": [], "articles": [],
          "knowledge_documents": []}
VOLATILE_HISTORY_FREE = ("answer", "route", "source_status", "agent_mode", "quick_replies",
                         "clarification_entity", "pending_project_lookup", "used_llm", "offer_action_menu")


class FakeCS:
    def __init__(self):
        self.calls = []

    def _route(self, path):
        if path == "/api/cs/company":
            return {"id": 16, "companyName": "Acme Builders"}
        if path == "/api/cs/projects":
            return PROJECTS
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
        log_data_api_call(provider="Acrobuild CS API", endpoint=path, params=params, status="completed")
        return copy.deepcopy(self._route(path))


class Chat:
    """A conversation driven through one endpoint with server-side history."""

    def __init__(self, client, endpoint, history):
        self.client = client
        self.endpoint = endpoint
        self.history = history

    def ask(self, question):
        response = self.client.post(self.endpoint, json={"issue": question, "conversation_id": "live-fixes"})
        assert response.status_code == 200, response.text
        if not self.endpoint.endswith("stream"):
            return response.json()
        events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        return next(event["response"] for event in events if event["type"] == "done")

    @property
    def last_bot(self):
        return self.history[-1]["text"]

    @property
    def slots(self):
        return latest_discovery_slots(self.history)


def _install_session(monkeypatch, module, history):
    class Session:
        def __init__(self, *_a):
            pass

        def set_cookie(self, *_a):
            pass

        def load(self):
            return list(history)

        def append(self, question, answer, marker=""):
            history.extend([{"sender": "customer", "text": question}, {"sender": "bot", "text": answer + marker}])

    monkeypatch.setattr(module, "ConversationSession", Session)


def _install_orchestration(monkeypatch, module, calls):
    def canned(**kw):
        calls.append(kw.get("issue"))
        return dict(CANNED)

    monkeypatch.setattr(module, "run_support_orchestration", canned)
    monkeypatch.setattr(module, "stream_support_orchestration_events",
                        lambda **kw: iter([{"type": "done", "response": canned(**kw)}]))


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", "true")
    fake = FakeCS()
    monkeypatch.setattr(company_service, "_cached_request", fake)
    monkeypatch.setattr(company_service, "_request_json",
                        lambda *a, **k: pytest.fail("no network calls in these tests"))
    monkeypatch.setattr(orchestrator, "generate_qwen_chat_response",
                        lambda *a, **k: pytest.fail("the general LLM must not be called"))
    monkeypatch.setattr(pipeline, "get_live_project_names", lambda: [p["projectName"] for p in PROJECTS])
    analysis = {"value": PROPERTY}
    monkeypatch.setattr(orchestrator, "analyze_turn", lambda *_a: analysis["value"])
    fake.orchestration_calls = []
    fake.history = []
    fake.analysis = analysis
    _install_orchestration(monkeypatch, assist, fake.orchestration_calls)
    _install_session(monkeypatch, assist, fake.history)
    return fake


@pytest.fixture
def chat(env):
    def make(endpoint):
        return Chat(TestClient(api), endpoint, env.history)
    return make


def _on_project(env, project="Alpha Heights"):
    """A project already in context, as an earlier project turn would leave it."""
    env.history.extend([
        {"sender": "customer", "text": f"Tell me about {project}"},
        {"sender": "bot", "text": f"{project} overview" + build_current_project_marker(project)},
    ])


def _to_results(c):
    c.ask("Show me 3 BHK")
    c.ask("Wakad")
    return c.ask("1.5 crore")


def _is_catalogue_discovery(payload):
    return (payload.get("discovery_kind") in {"locality_question", "budget_question", "results"}
            and payload.get("catalogue_home_type_search") is True
            and "Home types in" not in payload["answer"])


# -----------------------------------
# DEFECT 1: an explicit live place beats the project in context
# -----------------------------------

@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("question,place", [("3 BHK in Thane", "Thane"), ("3 bhk in Pune", "Pune"),
                                            ("Show me 3 BHK homes in Wakad", "Wakad")])
def test_explicit_live_place_is_a_catalogue_search(chat, env, endpoint, question, place):
    """Includes "Pune"/"Wakad": the place the project in context is itself in."""
    _on_project(env, "Alpha Heights")
    c = chat(endpoint)
    payload = c.ask(question)
    assert _is_catalogue_discovery(payload), payload["answer"]
    assert c.slots["locality"] == place and c.slots["config"] == ["3"]
    assert get_current_project_context(c.last_bot) == {"project": ""}
    assert env.orchestration_calls == []


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_explicit_place_after_project_turn_keeps_slots_and_overrides_locality(chat, env, endpoint):
    """The live T7 sequence: shortlist, then a question about a project, then a new area."""
    c = chat(endpoint)
    _to_results(c)
    amenities = c.ask("What amenities does Alpha Heights have?")
    assert "Swimming Pool" in amenities["answer"]
    assert get_current_project_context(c.last_bot) == {"project": "Alpha Heights"}
    payload = c.ask("3 BHK in Thane")
    assert _is_catalogue_discovery(payload), payload["answer"]
    assert payload["discovery_kind"] == "results"
    assert "Beta Residency" in payload["answer"]
    assert c.slots["locality"] == "Thane" and c.slots["budget_max_inr"] == 15 * 10**6
    assert get_current_project_context(c.last_bot) == {"project": ""}


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("question,project", [("3 BHK in Beta Residency", "Beta Residency"),
                                              ("3 BHK in Thane at Beta Residency", "Beta Residency"),
                                              ("3 BHK in Wakad at Delta Towers", "Delta Towers")])
def test_project_named_by_the_customer_still_wins(chat, env, endpoint, question, project):
    _on_project(env, "Alpha Heights")
    payload = chat(endpoint).ask(question)
    assert "discovery_kind" not in payload
    assert f"Home types in {project}" in payload["answer"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("question", ["2 BHK?", "Show me 2 BHK", "and 3 BHK?"])
def test_bare_followup_stays_on_the_project_in_context(chat, env, endpoint, question):
    _on_project(env, "Alpha Heights")
    payload = chat(endpoint).ask(question)
    assert "discovery_kind" not in payload
    assert "Home types in Alpha Heights" in payload["answer"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_reference_to_this_project_is_not_overridden(chat, env, endpoint):
    _on_project(env, "Alpha Heights")
    payload = chat(endpoint).ask("3 BHK in this project in Thane")
    assert "discovery_kind" not in payload


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_place_that_is_not_live_keeps_todays_behaviour(chat, env, endpoint):
    """"3 BHK in Kharadi" (no such live place) is unchanged: the project in context answers."""
    _on_project(env, "Alpha Heights")
    payload = chat(endpoint).ask("3 BHK in Kharadi")
    assert "discovery_kind" not in payload
    assert "Home types in Alpha Heights" in payload["answer"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_flag_off_explicit_place_is_unchanged(chat, env, monkeypatch, endpoint):
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", "false")
    _on_project(env, "Alpha Heights")
    payload = chat(endpoint).ask("3 BHK in Thane")
    assert "discovery_kind" not in payload and "discovery_slots" not in payload
    assert "Home types in Alpha Heights" in payload["answer"]


def test_explicit_locality_search_text_unit(monkeypatch):
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", "true")
    places = lambda: PLACES  # noqa: E731
    names = [p["projectName"] for p in PROJECTS]
    suffix = "\nRequested project: Alpha Heights"
    find = discovery.explicit_locality_search_text
    assert find("3BHK in Thane" + suffix, places, names) == "3BHK in Thane"
    assert find("3BHK in Thane", places, names) is None                        # nothing injected
    assert find("3BHK in Kharadi" + suffix, places, names) is None             # not a live place
    assert find("2BHK" + suffix, places, names) is None                        # no place at all
    assert find("3BHK in Thane at Beta Residency" + suffix, places, names) is None
    assert find("3BHK in this project in Thane" + suffix, places, names) is None
    assert find("amenities in Thane 3BHK" + suffix, places, names) is None     # specific request
    # Only the injected LAST line is removed: a place that appears only in the suffix never counts.
    assert find("3BHK\nRequested project: Beta Residency Thane", places, names) is None
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", "false")
    assert find("3BHK in Thane" + suffix, places, names) is None


# -----------------------------------
# DEFECT 2: a bare reset is a fixed acknowledgement
# -----------------------------------

@pytest.mark.parametrize("endpoint", ENDPOINTS)
@ANALYSES
@pytest.mark.parametrize("phrase", ["start over", "Start over.", "reset", "new search", "clear my preferences",
                                    "please start over", "start over please"])
def test_bare_reset_is_deterministic(chat, env, endpoint, phrase, analysis):
    c = chat(endpoint)
    _to_results(c)
    env.analysis["value"] = analysis
    turns_before = len(env.history)
    payload = c.ask(phrase)
    assert env.orchestration_calls == []                       # no LLM-backed orchestration
    assert payload["answer"] == discovery.RESET_ANSWER
    assert payload["route"] == "general" and payload["used_llm"] is False
    assert payload["source_status"] not in {"failed", "unavailable", "error"}
    # No place or configuration from history, no property claim, no figure.
    for word in [*PLACES, "BHK", "INR", "lakh", "crore", "Alpha", "Beta", "Delta", "Gamma", "Epsilon"]:
        assert word.lower() not in payload["answer"].lower(), word
    assert not re.search(r"\d", payload["answer"])
    assert not payload["matched_chunks"]
    # Stored state: slots cleared; the browse action is one the UI already handles.
    assert c.slots == {} and get_discovery_slots(c.last_bot) == {}
    assert len(env.history) == turns_before + 2
    assert payload["quick_replies"] == [{"label": "Browse all projects", "value": "Show me all projects",
                                         "action": "browse_projects"}]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@ANALYSES
def test_bare_reset_reads_no_amenity_or_inventory_data(chat, env, monkeypatch, endpoint, analysis):
    """The pending project choice left by the shortlist must not trigger the live amenity
    index (or any per-project read) for a reset. The one catalogue read that remains is
    turn preparation's project-name check (graph/main_orchestrator.py), not this branch."""
    c = chat(endpoint)
    _to_results(c)
    env.analysis["value"] = analysis
    reads = []
    real = company_service._cached_request

    def spy(path, *a, **k):
        reads.append(path)
        return real(path, *a, **k)

    monkeypatch.setattr(company_service, "_cached_request", spy)
    payload = c.ask("start over")
    assert payload["answer"] == discovery.RESET_ANSWER
    assert set(reads) <= {"/api/cs/projects"}, reads


def test_general_route_is_what_keeps_the_reset_reply_out_of_the_live_data_guard():
    """route="property" with no live CS read is downgraded to failed (the no-call trap);
    route="general" is not. The reset reply must therefore be "general"."""
    payload = discovery.build_reset_answer()
    assert payload["route"] == "general"
    assert api_context._enforce_live_property_data(dict(payload), "start over", []) == payload
    trapped = api_context._enforce_live_property_data({**payload, "route": "property"}, "start over", [])
    assert trapped["answer"] != payload["answer"] and trapped.get("source_status") == "failed"


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_reset_with_a_new_request_stores_the_new_slots_only(chat, env, endpoint):
    c = chat(endpoint)
    _to_results(c)                                             # Wakad, 3BHK, 1.5 crore stored
    payload = c.ask("start over, show me 2 BHK")
    assert payload["answer"] != discovery.RESET_ANSWER
    assert payload["discovery_kind"] in {"locality_question", "budget_question"}
    assert c.slots["config"] == ["2"]
    assert "budget_max_inr" not in c.slots and "budget_label" not in c.slots
    assert env.orchestration_calls == []


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("phrase", ["reset my password", "start over with the ticket", "new search results please"])
def test_reset_lookalikes_are_not_intercepted(chat, env, endpoint, phrase):
    c = chat(endpoint)
    _to_results(c)
    env.analysis["value"] = GENERAL
    payload = c.ask(phrase)
    assert payload["answer"] != discovery.RESET_ANSWER


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_reset_without_stored_slots_is_unchanged(chat, env, endpoint):
    env.analysis["value"] = GENERAL
    payload = chat(endpoint).ask("start over")
    assert payload["answer"] == CANNED["answer"]
    assert env.orchestration_calls == ["start over"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_reset_keeps_the_project_in_context_untouched(chat, env, endpoint):
    """Only search preferences are cleared; a bare follow-up still reaches the project."""
    c = chat(endpoint)
    _to_results(c)
    c.ask("What amenities does Alpha Heights have?")
    env.analysis["value"] = GENERAL
    c.ask("start over")
    env.analysis["value"] = PROPERTY
    assert c.slots == {}
    assert "Home types in Alpha Heights" in c.ask("2 BHK?")["answer"]


# -----------------------------------
# FLAG OFF == git HEAD
# -----------------------------------

def _load_head_assist(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git is not available")
    source = subprocess.run(["git", "show", "HEAD:routers/assist.py"], cwd=REPO, capture_output=True)
    if source.returncode != 0:
        pytest.skip("routers/assist.py is not readable at HEAD")
    path = tmp_path / "assist_at_head.py"
    path.write_bytes(source.stdout)
    spec = importlib.util.spec_from_file_location("assist_at_head", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _transcript(module, monkeypatch, endpoint, questions, seeded_history):
    history = list(seeded_history)
    calls = []
    _install_session(monkeypatch, module, history)
    _install_orchestration(monkeypatch, module, calls)
    app = FastAPI()
    app.include_router(module.router)
    client = TestClient(app)
    out = []
    for question in questions:
        response = client.post(endpoint, json={"issue": question, "conversation_id": "flag-off-head"})
        assert response.status_code == 200, response.text
        if endpoint.endswith("stream"):
            events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
            payload = next(event["response"] for event in events if event["type"] == "done")
        else:
            payload = response.json()
        out.append({key: payload.get(key) for key in VOLATILE_HISTORY_FREE} | {"stored": history[-1]["text"]})
    return out, calls


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("flag", ["off", "false"])
def test_flag_off_matches_git_head(env, monkeypatch, tmp_path, endpoint, flag):
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", flag)
    head = _load_head_assist(tmp_path)
    seeded = [
        {"sender": "customer", "text": "Show me 3 BHK"},
        {"sender": "bot", "text": "What's your budget?" + build_discovery_slots_marker(
            {"config": ["3"], "locality": "Wakad", "awaiting": "budget"})},
        {"sender": "customer", "text": "Tell me about Alpha Heights"},
        {"sender": "bot", "text": "Alpha Heights overview" + build_current_project_marker("Alpha Heights")},
    ]
    questions = ["start over", "reset", "3 BHK in Thane", "Show me 3 BHK", "2 BHK?", "start over, show me 2 BHK"]
    current, current_calls = _transcript(assist, monkeypatch, endpoint, questions, seeded)
    at_head, head_calls = _transcript(head, monkeypatch, endpoint, questions, seeded)
    assert current == at_head
    assert current_calls == head_calls
    assert get_discovery_slots(current[-1]["stored"]) is None       # no discovery marker written
