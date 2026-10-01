"""CS API diagnostics stay internal across customer-facing response paths."""

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import api
from graph.main_orchestrator import TurnContext
from routers import assist, properties
from services.internal_api_log_service import (
    begin_data_api_trace,
    end_data_api_trace,
    get_current_data_api_logs,
    get_data_api_logs,
    log_data_api_call,
    public_data_api_calls,
)
from services.turn_analysis_service import TurnAnalysis

HOSTILE_ERROR = (
    "ProviderException https://internal.example.invalid/api/cs/projects?apiKey="
    "LONG_CREDENTIAL_SENTINEL_abcdefghijklmnopqrstuvwxyz0123456789&debug=true response body: secret"
)
PUBLIC_ERROR = "Live data request failed; details are in the server log."


def _assert_public(payload):
    serialized = json.dumps(payload)
    for fragment in ("ProviderException", "internal.example.invalid", "apiKey=", "LONG_CREDENTIAL_SENTINEL_",
                     "debug=true", "response body: secret"):
        assert fragment not in serialized
    assert payload["data_api_calls"][0]["error"] == PUBLIC_ERROR


def test_public_trace_copy_preserves_metadata_and_internal_error(caplog):
    conversation_id = uuid4().hex
    token = begin_data_api_trace(conversation_id, "Question")
    try:
        log_data_api_call(provider="Acrobuild CS API", endpoint="/api/cs/projects", status="failed",
                          params={"availableOnly": True}, response_summary={"record_count": 0}, error=HOSTILE_ERROR)
        log_data_api_call(provider="Acrobuild CS API", endpoint="/api/cs/company", error="")
        raw = get_current_data_api_logs()
        public = public_data_api_calls(raw)
        _assert_public({"data_api_calls": public})
        assert public[0]["params"] == {"availableOnly": True}
        assert public[0]["response_summary"] == {"record_count": 0}
        assert public[0]["endpoint"] == raw[0]["endpoint"]
        assert public[1]["error"] == ""
        assert public[0] is not raw[0]
        public[0]["params"]["availableOnly"] = False
        assert raw[0]["params"]["availableOnly"] is True
        assert raw[0]["error"] == HOSTILE_ERROR
        assert get_current_data_api_logs()[0]["error"] == HOSTILE_ERROR
        assert any(call["error"] == HOSTILE_ERROR for call in get_data_api_logs(conversation_id))
        assert HOSTILE_ERROR in caplog.text
    finally:
        end_data_api_trace(token)


@pytest.fixture
def assist_env(monkeypatch):
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", "false")
    conversation_id = uuid4().hex
    turn = TurnContext(
        conversation_messages=[], resolved_issue="Where is the project?",
        analysis=TurnAnalysis("property", "English", "latin", "test"),
        property_issue="Where is the project?",
    )

    class Session:
        def __init__(self, *_args):
            pass

        def set_cookie(self, *_args):
            pass

        def load(self):
            return []

        def append(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr(assist, "ConversationSession", Session)
    monkeypatch.setattr(assist, "_prepare_lookup_turn", lambda request, issue, slots=None: (None, request, issue, turn))
    monkeypatch.setattr(assist, "apply_clarification_contract", lambda payload, *_args: payload)
    monkeypatch.setattr(assist, "localize_response", lambda payload, *_args: payload)

    def failed_shortcut(*_args, **_kwargs):
        log_data_api_call(provider="Acrobuild CS API", endpoint="/api/cs/projects", status="failed",
                          error=HOSTILE_ERROR)
        return {"answer": "Live property data is unavailable right now.", "route": "property",
                "source_status": "failed", "matched_chunks": [], "articles": [], "knowledge_documents": []}

    monkeypatch.setattr(assist, "_grounded_property_shortcut", failed_shortcut)
    return conversation_id


@pytest.mark.parametrize("endpoint", ["/api/support/assist", "/api/support/assist/stream"])
@pytest.mark.parametrize("kind", ["ordinary", "discovery", "clarification"])
def test_assist_public_telemetry_is_sanitized(assist_env, monkeypatch, endpoint, kind):
    if kind != "ordinary":
        def special_shortcut(*_args, **_kwargs):
            log_data_api_call(provider="Acrobuild CS API", endpoint="/api/cs/projects", status="failed",
                              error=HOSTILE_ERROR)
            payload = {"answer": "Live property data is unavailable right now.", "route": "property",
                       "source_status": "failed", "matched_chunks": [], "articles": [], "knowledge_documents": []}
            if kind == "discovery":
                payload["discovery_kind"] = "locality_question"
            else:
                payload["clarification_entity"] = "project"
                payload["pending_project_lookup"] = {
                    "kind": "selection", "original_issue": "Where is the project?", "entity": "project",
                    "options": [], "scope": {},
                }
            return payload
        monkeypatch.setattr(assist, "_grounded_property_shortcut", special_shortcut)
    response = TestClient(api).post(endpoint, json={"issue": "Where is the project?", "conversation_id": assist_env})
    assert response.status_code == 200
    if endpoint.endswith("stream"):
        events = [json.loads(line) for line in response.text.splitlines()]
        payload = events[-1]["response"]
        assert events[-1]["type"] == "done"
        assert HOSTILE_ERROR not in response.text
    else:
        payload = response.json()
    _assert_public(payload)
    if kind == "clarification":
        assert payload["clarification_entity"] == "project"
        assert payload["pending_project_lookup"]["original_issue"] == "Where is the project?"
    assert get_data_api_logs(assist_env)[0]["error"] == HOSTILE_ERROR
    assert payload["source_status"] == "failed"


def test_streaming_error_event_sanitizes_trace(assist_env, monkeypatch):
    def broken_turn(*_args, **_kwargs):
        log_data_api_call(provider="Acrobuild CS API", endpoint="/api/cs/projects", status="failed",
                          error=HOSTILE_ERROR)
        raise RuntimeError("orchestration failed")

    monkeypatch.setattr(assist, "_prepare_lookup_turn", broken_turn)
    response = TestClient(api).post("/api/support/assist/stream",
                                    json={"issue": "Where is the project?", "conversation_id": assist_env})
    assert response.status_code == 200
    event = json.loads(response.text.splitlines()[-1])
    assert event["type"] == "error"
    _assert_public(event["response"])
    assert HOSTILE_ERROR not in response.text
    assert get_data_api_logs(assist_env)[0]["error"] == HOSTILE_ERROR


def test_streaming_orchestrator_completion_sanitizes_trace(assist_env, monkeypatch):
    monkeypatch.setattr(assist, "_grounded_property_shortcut", lambda *_args, **_kwargs: None)

    def events(**_kwargs):
        log_data_api_call(provider="Acrobuild CS API", endpoint="/api/cs/projects", status="failed",
                          error=HOSTILE_ERROR)
        yield {"type": "done", "response": {"answer": "Live property data is unavailable right now.",
                                         "route": "property", "source_status": "failed", "matched_chunks": [],
                                         "articles": [], "knowledge_documents": []}}

    monkeypatch.setattr(assist, "stream_support_orchestration_events", events)
    response = TestClient(api).post("/api/support/assist/stream",
                                    json={"issue": "Where is the project?", "conversation_id": assist_env})
    assert response.status_code == 200
    event = json.loads(response.text.splitlines()[-1])
    assert event["type"] == "done"
    _assert_public(event["response"])
    assert HOSTILE_ERROR not in response.text


@pytest.mark.parametrize("path,loader", [
    ("/api/property-flow/projects", "get_company_projects"),
    ("/api/property-flow/projects/1/wings", "get_project_wings"),
    ("/api/property-flow/wings/2/typologies", "get_wing_typologies"),
    ("/api/property-flow/wings/2/inventory", "get_wing_inventory"),
])
def test_property_flow_response_and_failure_detail_are_sanitized(monkeypatch, path, loader):
    def successful_loader(*_args):
        log_data_api_call(provider="Acrobuild CS API", endpoint="/api/cs/projects", status="failed",
                          error=HOSTILE_ERROR)
        return []

    monkeypatch.setattr(properties, loader, successful_loader)
    response = TestClient(api).get(path)
    assert response.status_code == 200
    _assert_public(response.json())

    def failing_loader(*_args):
        log_data_api_call(provider="Acrobuild CS API", endpoint="/api/cs/projects", status="failed",
                          error=HOSTILE_ERROR)
        raise RuntimeError(HOSTILE_ERROR)

    monkeypatch.setattr(properties, loader, failing_loader)
    response = TestClient(api).get(path)
    assert response.status_code == 503
    assert HOSTILE_ERROR not in response.text
    assert response.json()["detail"] == PUBLIC_ERROR
