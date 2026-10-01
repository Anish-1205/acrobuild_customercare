"""ERR-006: an API outage keeps retry state without capturing a new intent."""

import pytest
from fastapi.testclient import TestClient

from app import api
from graph import main_orchestrator
from routers import assist
from services import acrobuild_company_service as company
from services.conversation_store_service import get_pending_project_lookup
from services.internal_api_log_service import log_data_api_call
from services.property_clarification_service import continues_selection, resume_selection
from services.turn_analysis_service import TurnAnalysis
from test_unsupported_capability_endpoints import ENDPOINTS, ask, support_env  # noqa: F401


@pytest.fixture
def failed_lookup_env(support_env, monkeypatch):
    original_request = company._cached_request
    unavailable = {"value": True}
    calls = []

    def controlled_request(path, params=None, ttl_seconds=None):
        if unavailable["value"]:
            log_data_api_call(provider="Acrobuild CS API", endpoint=path,
                              params=params, status="failed", error="private-CS-token-ERR006")
            raise RuntimeError("private-CS-token-ERR006")
        return original_request(path, params=params, ttl_seconds=ttl_seconds)

    def analyze(issue, *_args):
        lowered = issue.lower()
        if lowered in {"hi", "hello", "good morning", "thanks", "how are you?"}:
            intent = "general"
        elif "callback" in lowered:
            intent = "call_booking"
        elif "representative" in lowered:
            intent = "human_contact"
        else:
            intent = "property"
        return TurnAnalysis(intent, "English", "latin", "test", english=issue)

    def fallback(*, issue, turn, **_kwargs):
        calls.append(issue)
        if turn.analysis.intent == "general":
            return {"answer": "Hello! How can I help?", "route": "general",
                    "source_status": "workspace", "used_llm": False}
        if turn.analysis.intent in {"call_booking", "human_contact"}:
            return {"answer": "I can help connect you.", "route": turn.analysis.intent,
                    "source_status": "workspace", "used_llm": False}
        return {"answer": "Live property data is unavailable right now. Please try again.",
                "route": "property", "source_status": "failed", "used_llm": False}

    def stream_fallback(*, issue, turn, **kwargs):
        payload = fallback(issue=issue, turn=turn, **kwargs)
        yield {"type": "delta", "text": payload["answer"]}
        yield {"type": "done", "response": payload}

    monkeypatch.setattr(company, "_cached_request", controlled_request)
    monkeypatch.setattr(main_orchestrator, "analyze_turn", analyze)
    monkeypatch.setattr(assist, "run_support_orchestration", fallback)
    monkeypatch.setattr(assist, "stream_support_orchestration_events", stream_fallback)
    return support_env, unavailable, calls


def failed_request(client, endpoint, env):
    history, unavailable, _calls = env
    first, conversation_id = ask(client, endpoint, "What amenities does Vishwajeet Prime have?")
    assert first["route"] == "property"
    assert first["source_status"] == "failed"
    assert "private-CS-token-ERR006" not in str(first)
    pending = get_pending_project_lookup(history[conversation_id][-1]["text"])
    assert pending and pending["options"] == []
    assert pending["original_issue"] == "What amenities does Vishwajeet Prime have?"
    unavailable["value"] = False
    return conversation_id


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("greeting", ["Hi", "Hello", "Good morning", "Thanks"])
def test_new_social_intent_replaces_failed_lookup(failed_lookup_env, endpoint, greeting):
    history, _unavailable, calls = failed_lookup_env
    client = TestClient(api)
    conversation_id = failed_request(client, endpoint, failed_lookup_env)
    response, _ = ask(client, endpoint, greeting, conversation_id)
    assert response["route"] == "general"
    assert response["source_status"] == "workspace"
    assert "amenit" not in response["answer"].lower()
    assert calls[-1] == greeting
    assert get_pending_project_lookup(history[conversation_id][-1]["text"]) is None

    followup, _ = ask(client, endpoint, "How are you?", conversation_id)
    assert followup["route"] == "general"
    assert calls[-1] == "How are you?"
    assert get_pending_project_lookup(history[conversation_id][-1]["text"]) is None


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("retry", ["retry", "try again"])
def test_explicit_retry_recovers_failed_lookup(failed_lookup_env, endpoint, retry):
    client = TestClient(api)
    conversation_id = failed_request(client, endpoint, failed_lookup_env)
    response, _ = ask(client, endpoint, retry, conversation_id)
    assert response["route"] == "property"
    assert response["source_status"] == "live_api"
    assert "Badminton" in response["answer"]
    assert "Vishwajeet Prime" in response["answer"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_new_property_question_replaces_failed_lookup(failed_lookup_env, endpoint):
    history, _unavailable, _calls = failed_lookup_env
    client = TestClient(api)
    conversation_id = failed_request(client, endpoint, failed_lookup_env)
    response, _ = ask(client, endpoint, "What amenities does Vishwajeet Town have?", conversation_id)
    assert response["route"] == "property"
    assert response["source_status"] == "live_api"
    assert "Vishwajeet Town" in response["answer"]
    assert "Vishwajeet Prime" not in response["answer"]
    assert get_pending_project_lookup(history[conversation_id][-1]["text"]) is None


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize(("issue", "route"), [
    ("Please arrange a callback", "call_booking"),
    ("I want to talk to a representative", "human_contact"),
])
def test_action_replaces_failed_lookup(failed_lookup_env, endpoint, issue, route):
    history, _unavailable, calls = failed_lookup_env
    client = TestClient(api)
    conversation_id = failed_request(client, endpoint, failed_lookup_env)
    response, _ = ask(client, endpoint, issue, conversation_id)
    assert response["route"] == route
    assert calls[-1] == issue
    assert get_pending_project_lookup(history[conversation_id][-1]["text"]) is None


def test_empty_option_state_keeps_explicit_retry_and_selector():
    state = {"kind": "selection", "original_issue": "Show amenities", "entity": "project",
             "options": [], "scope": {}}
    assert not continues_selection(state, "Hi", starts_new_intent=True)
    assert continues_selection(state, "retry", starts_new_intent=True)
    assert continues_selection(state, "Prime")
    assert resume_selection(dict(state), "retry") == "Show amenities"


@pytest.mark.parametrize(("entity", "options", "reply"), [
    ("project", ["Vishwajeet Prime", "Vishwajeet Town"], "Prime"),
    ("wing", ["A", "B"], "A"),
    ("floor", ["1", "2"], "1"),
    ("flat", ["101", "201"], "101"),
    ("home_type", ["2BHK", "3BHK"], "2BHK"),
    ("locality", ["Pune", "Thane"], "Thane"),
])
def test_real_short_options_still_select(entity, options, reply):
    state = {"kind": "selection", "original_issue": "Show available flats", "entity": entity,
             "options": options, "scope": {}}
    assert continues_selection(state, reply, starts_new_intent=True)
    assert resume_selection(state, reply) != "Show available flats"
