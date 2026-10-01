"""AMN-003: generic detail follow-ups keep a reverse-amenity shortlist."""

import pytest
from fastapi.testclient import TestClient

from app import api
from routers import assist
from services.conversation_store_service import get_current_project_context, get_pending_project_lookup
from test_unsupported_capability_endpoints import ENDPOINTS, ask, support_env  # noqa: F401


ORIGINAL = "Which projects have Badminton?"
OPTIONS = ["Vishwajeet Prime", "Vishwajeet Town"]
DETAIL_FOLLOWUPS = (
    "what about the details?",
    "tell me more",
    "show me the details",
    "what details do you have?",
    "can you give me more information?",
    "what about them?",
)


@pytest.fixture
def amenity_env(support_env, monkeypatch):
    """Keep the live-shaped CS fake; make the unrelated fallback deterministic."""
    fallback = {"answer": "Please tell me what you need.", "route": "general",
                "source_status": "workspace", "used_llm": False}
    monkeypatch.setattr(assist, "run_support_orchestration", lambda **_kwargs: dict(fallback))
    monkeypatch.setattr(assist, "stream_support_orchestration_events",
                        lambda **_kwargs: iter([{"type": "done", "response": dict(fallback)}]))
    return support_env


def shortlist(client, endpoint, history):
    first, conversation_id = ask(client, endpoint, ORIGINAL)
    assert first["route"] == "property"
    assert first["source_status"] == "live_api"
    assert first["clarification_entity"] == "project"
    assert first["pending_project_lookup"]["options"] == OPTIONS
    assert first["pending_project_lookup"]["original_issue"] == ORIGINAL
    assert first["pending_project_lookup"]["purpose"] == "amenity_search"
    assert [reply["value"] for reply in first["quick_replies"]] == OPTIONS
    assert get_pending_project_lookup(history[conversation_id][-1]["text"]) == first["pending_project_lookup"]
    return conversation_id


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("followup", DETAIL_FOLLOWUPS)
def test_generic_details_preserves_amenity_shortlist(amenity_env, endpoint, followup):
    history = amenity_env
    client = TestClient(api)
    conversation_id = shortlist(client, endpoint, history)
    response, _ = ask(client, endpoint, followup, conversation_id)
    assert response["route"] == "property"
    assert response["source_status"] == "live_api"
    assert response["clarification_entity"] == "project"
    assert response["pending_project_lookup"]["options"] == OPTIONS
    assert response["pending_project_lookup"]["original_issue"] == ORIGINAL
    assert response["pending_project_lookup"]["purpose"] == "amenity_search"
    assert [reply["value"] for reply in response["quick_replies"]] == OPTIONS
    assert not any("/amenities" in call["endpoint"] for call in response["data_api_calls"])
    assert get_pending_project_lookup(history[conversation_id][-1]["text"]) == response["pending_project_lookup"]
    assert (get_current_project_context(history[conversation_id][-1]["text"]) or {}).get("project") != "Vishwajeet Prime"
    assert all(term not in response["answer"].lower() for term in (
        "floor plan", "brochure", "document", "offer", "nearby distance",
    ))

    restored = client.get(f"/api/support/conversations/{conversation_id}/history")
    assert restored.status_code == 200
    assert [reply["value"] for reply in restored.json()["quick_replies"]] == OPTIONS

    selected, _ = ask(client, endpoint, "Vishwajeet Prime", conversation_id)
    assert selected["route"] == "property"
    assert selected["source_status"] == "live_api"
    assert "Badminton" in selected["answer"]
    assert "Vishwajeet Prime" in selected["answer"]
    assert get_pending_project_lookup(history[conversation_id][-1]["text"]) is None


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_direct_selection_and_invalid_choice(amenity_env, endpoint):
    history = amenity_env
    client = TestClient(api)
    conversation_id = shortlist(client, endpoint, history)
    invalid, _ = ask(client, endpoint, "Imaginary Project", conversation_id)
    assert invalid["pending_project_lookup"]["options"] == OPTIONS
    assert invalid["pending_project_lookup"]["original_issue"] == ORIGINAL
    selected, _ = ask(client, endpoint, "Vishwajeet Town", conversation_id)
    assert "Badminton" in selected["answer"]
    assert "Vishwajeet Town" in selected["answer"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_no_pending_shortlist_is_not_invented(amenity_env, endpoint):
    history = amenity_env
    response, conversation_id = ask(TestClient(api), endpoint, "what about the details?")
    assert response.get("pending_project_lookup") is None
    assert not response.get("quick_replies")
    assert get_pending_project_lookup(history[conversation_id][-1]["text"]) is None


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_explicit_new_intent_replaces_shortlist(amenity_env, endpoint):
    history = amenity_env
    client = TestClient(api)
    conversation_id = shortlist(client, endpoint, history)
    response, _ = ask(client, endpoint, "What's the weather today?", conversation_id)
    assert response.get("pending_project_lookup") is None
    assert get_pending_project_lookup(history[conversation_id][-1]["text"]) is None
