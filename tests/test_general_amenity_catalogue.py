import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_context
from graph.main_orchestrator import TurnContext
from routers import assist
from services import acrobuild_company_service as cs
from services.internal_api_log_service import log_data_api_call
from services.turn_analysis_service import TurnAnalysis


PROJECTS = [
    {"id": 1, "projectName": "Vishwajeet Prime"},
    {"id": 2, "projectName": "Vishwajeet Precious"},
    {"id": 3, "projectName": "Vishwajeet Precious Phase-V"},
    {"id": 4, "projectName": "Vishwajeet Myspace"},
]
AMENITIES = {1: ["Swimming Pool"], 2: ["Swimming Pool", "Gym"], 3: [], 4: []}
TRANSLATIONS = {
    "swimming pool kontya projects madhe aahe?": "Which projects have a swimming pool?",
    "purna amenity list ani location sanga": "Give me the full amenity list and location",
    "konse projects me amenities hai?": "Which projects have amenities?",
    "amenities kay tar projects madhe aahe?": "Which projects have amenities?",
    "mala swimming pool pahije": "I want a swimming pool",
    "kya amenities hai ismein?": "What amenities does it have?",
}


@pytest.fixture
def chat(monkeypatch):
    history = []
    state = {"offline": False}

    def request(path, params=None):
        if state["offline"]:
            log_data_api_call(provider="Acrobuild CS API", endpoint=path, method="GET", status="failed", error="offline")
            raise RuntimeError("offline")
        value = PROJECTS if path == "/api/cs/projects" else [
            {"iconName": name} for name in AMENITIES[int(path.split("/")[-2])]
        ]
        log_data_api_call(provider="Acrobuild CS API", endpoint=path, method="GET", status="completed")
        return value

    def prepare(issue, conversation_id, messages, language_hint):
        english = TRANSLATIONS.get(issue, issue)
        return TurnContext(messages, english, TurnAnalysis(
            intent="property", reply_language="Hindi", script="latin", english=english, source="test",
        ), english)

    def append(issue, answer, marker=""):
        history.extend([{"sender": "customer", "text": issue}, {"sender": "bot", "text": answer + marker}])

    monkeypatch.setattr(cs, "CS_API_LIVE_ONLY", True)
    monkeypatch.setattr(cs, "_request_json", request)
    monkeypatch.setattr(assist, "prepare_turn", prepare)
    monkeypatch.setattr(assist, "localize_response", lambda payload, analysis: payload)
    monkeypatch.setattr(assist.ConversationSession, "load", lambda self: list(history))
    monkeypatch.setattr(assist.ConversationSession, "append", lambda self, *args, **kwargs: append(*args, **kwargs))
    failure = {"route": "property", "source_status": "failed", "answer": "Temporarily unavailable"}
    monkeypatch.setattr(assist, "run_support_orchestration", lambda **kwargs: dict(failure))
    monkeypatch.setattr(assist, "stream_support_orchestration_events", lambda **kwargs: iter([{"type": "done", "response": dict(failure)}]))
    app = FastAPI()
    app.include_router(assist.router)
    with TestClient(app) as client:
        def ask(endpoint, issue):
            result = client.post(endpoint, json={"issue": issue, "conversation_id": "amenities-test"})
            assert result.status_code == 200
            if endpoint.endswith("stream"):
                return next(json.loads(line)["response"] for line in result.text.splitlines() if json.loads(line)["type"] == "done")
            return result.json()
        yield ask, state, history


@pytest.mark.parametrize("endpoint", ["/api/support/assist", "/api/support/assist/stream"])
@pytest.mark.parametrize("question", ["konse projects me amenities hai?", "amenities kay tar projects madhe aahe?"])
def test_general_amenities_shortlist_narrow_and_select(chat, endpoint, question):
    ask, _, _ = chat
    first = ask(endpoint, question)
    assert first["pending_project_lookup"]["options"] == ["Vishwajeet Prime", "Vishwajeet Precious"]
    assert "Myspace" not in first["answer"]
    narrowed = ask(endpoint, "mala swimming pool pahije")
    assert narrowed["pending_project_lookup"]["options"] == first["pending_project_lookup"]["options"]
    assert narrowed["pending_project_lookup"]["original_issue"] == "Which projects have amenities?"
    selected = ask(endpoint, "precious")
    assert "Swimming Pool" in selected["answer"] and "Gym" in selected["answer"]
    assert "does not currently list amenities" not in selected["answer"]


@pytest.mark.parametrize("endpoint", ["/api/support/assist", "/api/support/assist/stream"])
def test_contextual_project_and_new_catalogue_question(chat, endpoint):
    ask, _, history = chat
    history.append({"sender": "customer", "text": "Vishwajeet Precious Phase-V"})
    project = ask(endpoint, "kya amenities hai ismein?")
    assert "does not currently list amenities for Vishwajeet Precious Phase-V" in project["answer"]
    broad = ask(endpoint, "konse projects me amenities hai?")
    assert broad["pending_project_lookup"]["options"] == ["Vishwajeet Prime", "Vishwajeet Precious"]


@pytest.mark.parametrize("endpoint", ["/api/support/assist", "/api/support/assist/stream"])
def test_retries_keep_original_amenity_request(chat, endpoint):
    ask, state, history = chat
    first = ask(endpoint, "Which projects have amenities?")
    state["offline"] = True
    for _ in range(3):
        ask(endpoint, "retry")
        pending = assist.get_pending_project_lookup(history[-1]["text"])
        assert pending["original_issue"] == first["pending_project_lookup"]["original_issue"]
        assert pending["options"] == first["pending_project_lookup"]["options"]
        assert pending["scope"] == first["pending_project_lookup"]["scope"]
    state["offline"] = False
    result = ask(endpoint, "retry")
    assert result["pending_project_lookup"]["options"] == first["pending_project_lookup"]["options"]


def test_empty_amenity_catalogue_does_not_offer_projects(chat):
    ask, _, _ = chat
    from unittest.mock import patch
    with patch.dict(AMENITIES, {key: [] for key in AMENITIES}):
        result = ask("/api/support/assist", "What amenities are available?")
    assert result["quick_replies"] == []
    assert "does not mean they have no amenities" in result["answer"]


@pytest.mark.parametrize("endpoint", ["/api/support/assist", "/api/support/assist/stream"])
def test_filtered_details_keep_scope_and_complete_intent(chat, endpoint):
    ask, state, history = chat
    first = ask(endpoint, "swimming pool kontya projects madhe aahe?")
    names = ["Vishwajeet Prime", "Vishwajeet Precious"]
    assert [reply["value"] for reply in first["quick_replies"]] == names
    details = ask(endpoint, "purna amenity list ani location sanga")
    assert details["pending_project_lookup"]["options"] == names
    assert [reply["value"] for reply in details["quick_replies"]] == names
    state["offline"] = True
    for _ in range(3):
        ask(endpoint, "precious")
        pending = assist.get_pending_project_lookup(history[-1]["text"])
        assert pending["options"] == names
        assert "location" in pending["original_issue"]
    state["offline"] = False
    selected = ask(endpoint, "retry")
    assert "Gym" in selected["answer"] and "Swimming Pool" in selected["answer"]
    assert "Location:" in selected["answer"]


@pytest.mark.parametrize("endpoint", ["/api/support/assist", "/api/support/assist/stream"])
def test_standalone_filter_selection_and_explicit_new_project(chat, endpoint):
    ask, _, _ = chat
    ask(endpoint, "Which projects have a swimming pool?")
    selected = ask(endpoint, "precious")
    assert "Gym" in selected["answer"]
    ask(endpoint, "Which projects have a swimming pool?")
    changed = ask(endpoint, "Show amenities for Vishwajeet Precious Phase-V")
    assert "does not currently list amenities for Vishwajeet Precious Phase-V" in changed["answer"]


@pytest.mark.parametrize("endpoint", ["/api/support/assist", "/api/support/assist/stream"])
def test_detail_scope_can_be_narrowed_again(chat, endpoint):
    ask, _, _ = chat
    ask(endpoint, "Which projects have a swimming pool?")
    ask(endpoint, "Give me the full amenity list and location")
    narrowed = ask(endpoint, "one with a gym")
    assert narrowed["pending_project_lookup"]["options"] == ["Vishwajeet Precious"]
    selected = ask(endpoint, "precious")
    assert "Gym" in selected["answer"] and "Location:" in selected["answer"]
