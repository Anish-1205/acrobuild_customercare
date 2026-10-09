from fastapi.testclient import TestClient

from test_upgrade_security import workspace  # noqa: F401
from services.conversation_store_service import (
    COOKIE_NAME,
    ConversationSession,
    PENDING_CALL_BOOKING_MARKER,
    build_current_project_marker,
    build_discovery_slots_marker,
    build_pending_project_lookup_marker,
    get_current_project_context,
    get_discovery_slots,
    get_pending_project_lookup,
    has_pending_call_booking_marker,
)


def _client(token):
    import app

    client = TestClient(app.api)
    client.cookies.set(COOKIE_NAME, token)
    return client


def test_history_is_cookie_and_conversation_scoped_and_visible_only(workspace):
    session = ConversationSession("", "one")
    marker = (
        PENDING_CALL_BOOKING_MARKER
        + build_current_project_marker("AcroBuild A")
        + build_discovery_slots_marker({"config": ["3"], "awaiting": "budget"})
        + build_pending_project_lookup_marker({
            "kind": "selection", "entity": "project", "options": ["AcroBuild A", "AcroBuild B"],
            "original_issue": "घर दिखाओ", "scope": {},
        })
    )
    session.append("घर दिखाओ", "Choose a project", marker=marker)
    session.append("AcroBuild A", "घर उपलब्ध है", marker=build_current_project_marker("AcroBuild A"))

    result = _client(session.token).get("/api/support/conversations/one/history")
    assert result.status_code == 200
    assert "no-store" in result.headers["cache-control"]
    assert result.json() == {
        "exists": True,
        "messages": [
            {"sender": "customer", "text": "घर दिखाओ"},
            {"sender": "bot", "text": "Choose a project"},
            {"sender": "customer", "text": "AcroBuild A"},
            {"sender": "bot", "text": "घर उपलब्ध है"},
        ],
        "quick_replies": [],
    }
    assert _client(ConversationSession("", "one").token).get(
        "/api/support/conversations/one/history"
    ).json()["exists"] is False
    assert _client(session.token).get("/api/support/conversations/two/history").json()["exists"] is False


def test_history_restores_pending_choices_without_marker_payload(workspace):
    session = ConversationSession("", "pending")
    marker = build_pending_project_lookup_marker({
        "kind": "selection", "entity": "locality", "purpose": "discovery",
        "options": ["Wakad", "Thane"], "original_issue": "3 BHK", "scope": {},
    })
    session.append("3 BHK", "Which area?", marker=marker)
    payload = _client(session.token).get("/api/support/conversations/pending/history").json()
    assert payload["messages"][-1] == {"sender": "bot", "text": "Which area?"}
    assert payload["quick_replies"] == [
        {"label": "Wakad", "value": "Wakad"},
        {"label": "Thane", "value": "Thane"},
    ]
    assert "pending_project_lookup" not in str(payload)


def test_history_does_not_restore_a_lone_any_budget_reply(workspace):
    session = ConversationSession("", "budget")
    marker = build_discovery_slots_marker({
        "config": ["3"], "locality": "Wakad", "awaiting": "budget",
    })
    session.append("Wakad", "What's your approximate budget?", marker=marker)
    payload = _client(session.token).get("/api/support/conversations/budget/history").json()
    assert payload["messages"][-1] == {"sender": "bot", "text": "What's your approximate budget?"}
    assert payload["quick_replies"] == []


def test_expired_history_is_not_returned(workspace, monkeypatch):
    import services.conversation_store_service as store

    session = ConversationSession("", "expired")
    session.append("hello", "hi")
    now = store.time.time()
    monkeypatch.setattr(store.time, "time", lambda: now + store.RETENTION_SECONDS + 1)
    payload = _client(session.token).get("/api/support/conversations/expired/history").json()
    assert payload == {"exists": False, "messages": [], "quick_replies": []}


def test_history_read_keeps_server_context_for_followup(workspace):
    cases = [
        ("project", build_current_project_marker("AcroBuild A"),
         lambda text: get_current_project_context(text) == {"project": "AcroBuild A"}),
        ("discovery", build_discovery_slots_marker({"config": ["3"], "locality": "Wakad", "awaiting": "budget"}),
         lambda text: get_discovery_slots(text) == {"config": ["3"], "locality": "Wakad", "awaiting": "budget"}),
        ("clarification", build_pending_project_lookup_marker({
            "kind": "selection", "entity": "wing", "options": ["A", "B"],
            "original_issue": "2 BHK?", "scope": {"project": "AcroBuild A"},
        }), lambda text: get_pending_project_lookup(text)["original_issue"] == "2 BHK?"),
        ("callback", PENDING_CALL_BOOKING_MARKER, has_pending_call_booking_marker),
    ]
    for name, marker, check in cases:
        session = ConversationSession("", name)
        session.append("question", "answer", marker=marker)
        before = session.load()
        response = _client(session.token).get(f"/api/support/conversations/{name}/history")
        assert response.status_code == 200
        assert response.json()["messages"][-1]["text"] == "answer"
        assert session.load() == before
        assert check(session.load()[-1]["text"])
