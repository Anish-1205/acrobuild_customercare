"""Review fixes for the discovery wiring (Inquiry to Sales §28, §32).

A. CS API error text never reaches the client or the stored marker.
B. The awaiting-locality backup works when the pending selection was dropped.
C. "start over, <new request>" starts from empty slots and stores the new ones.
D. Flag off: call-booking / human-contact markers are byte-identical to git HEAD.

Offline: the CS client is a logging fake, the analyzer is stubbed, orchestration
is canned unless a test needs the real call-booking flow (then run_workflow is
stubbed), and _request_json fails the test if reached.
"""
import copy
import importlib.util
import json
import logging
import re
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import api
from graph import haystack_conversation_pipeline as pipeline
from graph import main_orchestrator as orchestrator
from routers import assist
from services import acrobuild_company_service as company_service
from services.conversation_store_service import (
    build_discovery_slots_marker,
    build_pending_project_lookup_marker,
    get_discovery_slots,
    latest_discovery_slots,
)
from services.internal_api_log_service import log_data_api_call
from services.turn_analysis_service import TurnAnalysis

ROOT = Path(__file__).resolve().parent.parent
ENDPOINTS = ["/api/support/assist", "/api/support/assist/stream"]
SQFT = "Rate Per Sq.Ft."
PROJECTS = [
    {"id": 1, "projectName": "Alpha Heights", "locality": "Wakad", "city": "Pune"},
    {"id": 2, "projectName": "Beta Residency", "locality": "", "city": "Thane"},
    {"id": 3, "projectName": "Gamma Park", "locality": "Hinjewadi", "city": "Pune"},
    {"id": 4, "projectName": "Delta Towers", "locality": "Wakad", "city": "Pune"},
]
TYPOLOGIES = {
    1: [{"id": 11, "typologyName": "3BHK", "rateType": SQFT, "minBasePrice": 10000, "saleableArea": 1200}],
    2: [{"id": 21, "typologyName": "3BHK", "rateType": SQFT, "minBasePrice": 15000, "saleableArea": 1300}],
    3: [{"id": 31, "typologyName": "3BHK", "rateType": SQFT, "minBasePrice": 9000, "saleableArea": 1100}],
    4: [{"id": 41, "typologyName": "3BHK", "rateType": SQFT, "minBasePrice": 11000, "saleableArea": 1500}],
}
AREAS_3BHK = ["Hinjewadi", "Thane", "Wakad"]
SECRET_URL = "https://cs-internal.example.invalid/api/cs/16/projects/4/typologies"
SECRET_KEY = "sk_live_9f8e7d6c5b4a39281706f5e4d3c2b1a0"
SECRET_ERROR = f"Could not reach the CS API: {SECRET_URL}?apiKey={SECRET_KEY}"
PROPERTY = TurnAnalysis("property", "English", "latin", "test")
GENERAL = TurnAnalysis("general", "English", "latin", "test")
CANNED = {"answer": "canned orchestration answer", "route": "general", "source_status": "live",
          "agent_mode": "live_remote_llm", "used_llm": True, "matched_chunks": [], "articles": [],
          "knowledge_documents": []}


class FakeCS:
    def __init__(self):
        self.fail = {}

    def __call__(self, path, params=None, ttl_seconds=None):
        error = self.fail.get(path)
        if error is not None:
            log_data_api_call(provider="Acrobuild CS API", endpoint=path, params=params, status="failed",
                              error=str(error))
            raise error
        log_data_api_call(provider="Acrobuild CS API", endpoint=path, params=params, status="completed")
        if path == "/api/cs/projects":
            return copy.deepcopy(PROJECTS)
        match = re.fullmatch(r"/api/cs/projects/(\d+)/typologies", path)
        if match:
            return copy.deepcopy(TYPOLOGIES.get(int(match.group(1)), []))
        if re.fullmatch(r"/api/cs/projects/\d+/(wings|amenities)", path):
            return []
        raise AssertionError(f"unexpected CS path {path}")


class Recorder:
    """Fake ConversationSession store shared by every session instance."""

    def __init__(self):
        self.history = []

    def session_class(self):
        history = self.history

        class Session:
            def __init__(self, *_a):
                pass

            def set_cookie(self, *_a):
                pass

            def load(self):
                return list(history)

            def append(self, question, answer, marker=""):
                history.extend([{"sender": "customer", "text": question},
                                {"sender": "bot", "text": answer + marker}])

        return Session


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", "true")
    fake = FakeCS()
    monkeypatch.setattr(company_service, "_cached_request", fake)
    monkeypatch.setattr(company_service, "_request_json", lambda *a, **k: pytest.fail("no network in tests"))
    monkeypatch.setattr(pipeline, "get_live_project_names", lambda: [p["projectName"] for p in PROJECTS])
    analysis = {"value": PROPERTY}
    monkeypatch.setattr(orchestrator, "analyze_turn", lambda *_a: analysis["value"])
    calls = []

    def canned(**kw):
        calls.append(kw.get("issue"))
        return dict(CANNED)

    monkeypatch.setattr(assist, "run_support_orchestration", canned)
    monkeypatch.setattr(assist, "stream_support_orchestration_events",
                        lambda **kw: iter([{"type": "done", "response": canned(**kw)}]))
    recorder = Recorder()
    monkeypatch.setattr(assist, "ConversationSession", recorder.session_class())
    fake.analysis, fake.orchestration_calls, fake.history = analysis, calls, recorder.history
    return fake


def ask(client, endpoint, question):
    """(final payload, full raw response text)."""
    response = client.post(endpoint, json={"issue": question, "conversation_id": "review-fixes"})
    assert response.status_code == 200, response.text
    if not endpoint.endswith("stream"):
        return response.json(), response.text
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    return next(event["response"] for event in events if event["type"] == "done"), response.text


def _stored(history):
    return "\n".join(message["text"] for message in history)


# -----------------------------------
# A. NO CS API ERROR TEXT REACHES THE CLIENT
# -----------------------------------

@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("failing_path", ["/api/cs/projects/4/typologies", "/api/cs/projects"])
def test_cs_error_text_never_reaches_the_client(env, caplog, endpoint, failing_path):
    env.fail[failing_path] = RuntimeError(SECRET_ERROR)
    client = TestClient(api)
    with caplog.at_level(logging.WARNING):
        payload, raw = ask(client, endpoint, "3 BHK in Wakad under 1.5 crore")
    assert payload.get("discovery_kind") or payload.get("pending_project_lookup")
    for leaked in (SECRET_URL, SECRET_KEY, "apiKey=", "Could not reach the CS API"):
        assert leaked not in raw, leaked
        assert leaked not in json.dumps(payload), leaked
        assert leaked not in _stored(env.history), leaked
    if payload.get("skipped"):
        assert all(set(entry) == {"project"} for entry in payload["skipped"])
    # The full text stays available to operators in the server log.
    assert any(SECRET_KEY in record.getMessage() for record in caplog.records)


# -----------------------------------
# B. AWAITING-LOCALITY BACKUP WITHOUT A PENDING SELECTION
# -----------------------------------

def _locality_question_history(env):
    """A stored area question whose pending selection the next reply will drop."""
    pending = {"kind": "selection", "entity": "locality", "options": AREAS_3BHK, "scope": {},
               "original_issue": "Show me 3BHK", "purpose": "discovery", "source": "discovery"}
    env.history.extend([
        {"sender": "customer", "text": "Show me 3 BHK"},
        {"sender": "bot", "text": "Which area should I check for 3BHK homes?\n- Hinjewadi\n- Thane\n- Wakad"
         + build_pending_project_lookup_marker(pending)
         + build_discovery_slots_marker({"config": ["3"], "awaiting": "locality", "origin_issue": "Show me 3BHK"})},
    ])


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_locality_reply_with_dropped_pending_and_general_label(env, endpoint):
    _locality_question_history(env)
    env.analysis["value"] = GENERAL
    payload, _ = ask(TestClient(api), endpoint, "Wakad lo")
    assert payload.get("discovery_kind") == "budget_question", payload.get("answer")
    assert latest_discovery_slots(env.history)["locality"] == "Wakad"
    assert env.orchestration_calls == []


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("message", ["What's the weather like today?", "hello", "tell me a joke"])
def test_unrelated_general_message_is_not_forced_while_awaiting_locality(env, endpoint, message):
    _locality_question_history(env)
    env.analysis["value"] = GENERAL
    payload, _ = ask(TestClient(api), endpoint, message)
    assert payload["answer"] == CANNED["answer"]
    assert "discovery_kind" not in payload
    assert env.orchestration_calls


# -----------------------------------
# C. RESET PLUS A NEW REQUEST
# -----------------------------------

def _budget_question_history(env):
    env.history.extend([
        {"sender": "customer", "text": "Wakad"},
        {"sender": "bot", "text": "What's your approximate budget for a 3BHK in Wakad?" + build_discovery_slots_marker(
            {"config": ["2"], "locality": "Wakad", "awaiting": "budget", "budget_max_inr": 10**7,
             "budget_label": "1 crore", "origin_issue": "Show me 2BHK"})},
    ])


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_start_over_with_new_request_stores_the_new_slots(env, endpoint):
    _budget_question_history(env)
    payload, _ = ask(TestClient(api), endpoint, "start over, show me 3 BHK")
    assert payload["discovery_kind"] == "locality_question"          # old locality not reused
    stored = get_discovery_slots(env.history[-1]["text"])
    assert stored["config"] == ["3"] and stored["awaiting"] == "locality"
    assert "locality" not in stored and "budget_max_inr" not in stored


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_plain_start_over_still_clears(env, endpoint):
    _budget_question_history(env)
    ask(TestClient(api), endpoint, "start over")
    assert get_discovery_slots(env.history[-1]["text"]) == {}
    assert latest_discovery_slots(env.history) == {}


# -----------------------------------
# D. FLAG OFF: CALL-BOOKING / HUMAN-CONTACT MARKERS == GIT HEAD
# -----------------------------------

def _head_app(tmp_path):
    try:
        source = subprocess.run(["git", "show", "HEAD:routers/assist.py"], cwd=ROOT, capture_output=True,
                                text=True, check=True, encoding="utf-8").stdout
    except (OSError, subprocess.CalledProcessError) as error:
        pytest.skip(f"git HEAD not available: {error}")
    path = tmp_path / "assist_head.py"     # pytest temp dir, never inside the repo
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("assist_head_for_marker_identity", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    app = FastAPI()
    app.include_router(module.router)
    return module, app


FLOWS = {
    "call_booking": (TurnAnalysis("call_booking", "English", "latin", "test"),
                     ["Please arrange a callback", "9876543210 tomorrow morning", "thanks"]),
    "human_contact": (TurnAnalysis("human_contact", "English", "latin", "test"),
                      ["I want to talk to a representative", "Anish Kumar 9876543210", "thanks"]),
}


def _run_flow(monkeypatch, module, app, analysis, turns):
    recorder = Recorder()
    monkeypatch.setattr(module, "ConversationSession", recorder.session_class())
    client = TestClient(app)
    for turn in turns:
        response = client.post("/api/support/assist", json={"issue": turn, "conversation_id": "identity"})
        assert response.status_code == 200, response.text
    return [message["text"] for message in recorder.history]


@pytest.mark.parametrize("flow", sorted(FLOWS))
@pytest.mark.parametrize("flag", [None, "false"])
def test_flag_off_call_markers_are_identical_to_head(monkeypatch, tmp_path, flow, flag):
    if flag is None:
        monkeypatch.delenv("ACROBUILD_DISCOVERY_SLOTS", raising=False)
    else:
        monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", flag)
    monkeypatch.setattr(company_service, "_request_json", lambda *a, **k: pytest.fail("no network in tests"))
    monkeypatch.setattr(pipeline, "get_live_project_names", lambda: [])
    analysis, turns = FLOWS[flow]
    monkeypatch.setattr(orchestrator, "analyze_turn", lambda *_a: analysis)
    monkeypatch.setattr(orchestrator, "run_workflow", lambda *_a, **_k: {"ticket_id": "ACB-TEST-1"})
    head_module, head_app = _head_app(tmp_path)
    current_app = FastAPI()
    current_app.include_router(assist.router)
    head = _run_flow(monkeypatch, head_module, head_app, analysis, turns)
    current = _run_flow(monkeypatch, assist, current_app, analysis, turns)
    assert current == head
    assert any("⁣pending_" in text for text in head)   # the flows really stored call/contact markers
