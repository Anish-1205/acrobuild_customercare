from importlib.util import MAGIC_NUMBER

import pytest

from test_upgrade_security import workspace  # noqa: F401
from services.conversation_store_service import ConversationSession
from services.runtime_compatibility_service import validate_runtime_header


def test_history_survives_new_instance_and_isolates_browser(workspace):
    first = ConversationSession("", "conversation-1")
    first.append("Show projects", "Project A")
    restored = ConversationSession(first.token, "conversation-1")
    assert restored.load()[-1]["text"] == "Project A"
    assert ConversationSession("", "conversation-1").load() == []
    assert ConversationSession(first.token, "conversation-2").load() == []


def test_history_bounded_and_can_be_deleted(workspace):
    session = ConversationSession("", "c")
    for index in range(40):
        session.append(str(index), "answer")
    assert len(session.load()) == 60
    assert session.load()[0]["text"] == "10"
    session.clear()
    assert session.load() == []


def test_history_expires(workspace, monkeypatch):
    import services.conversation_store_service as store
    session = ConversationSession("", "c")
    session.append("hello", "hi")
    now = store.time.time()
    monkeypatch.setattr(store.time, "time", lambda: now + 7201)
    assert session.load() == []


def test_runtime_header_fails_before_unmarshalling():
    validate_runtime_header(MAGIC_NUMBER + bytes(12))
    with pytest.raises(RuntimeError, match="matching Python"):
        validate_runtime_header(b"wrong-version!!!")


def test_scanner_requires_engine_in_production(monkeypatch):
    from services.upload_security_service import scan_upload, validate_knowledge_upload
    monkeypatch.setenv("ACROBUILD_ENV", "production")
    monkeypatch.delenv("CLAMSCAN_PATH", raising=False)
    with pytest.raises(ValueError, match="unavailable"):
        scan_upload(b"data")
    with pytest.raises(ValueError, match="PDF content"):
        validate_knowledge_upload(b"not a PDF", "document.pdf")


def test_confirmation_rejects_stale_or_replayed_action(workspace):
    from services.database_service import open_database_connection
    from services.workflow_automation_service import propose_action, confirm_action
    from contextlib import closing
    with closing(open_database_connection()) as conn, conn:
        conn.execute("INSERT INTO tickets(ticket_id,assigned_agent,status) VALUES('T1','Agent One','Open')")
    proposal = propose_action(1, "T1", "status", {"status": "Resolved"})
    assert confirm_action(1, proposal["proposal_id"])["completed"]
    with pytest.raises(ValueError):
        confirm_action(1, proposal["proposal_id"])
    stale = propose_action(1, "T1", "status", {"status": "Closed"})
    with closing(open_database_connection()) as conn, conn:
        conn.execute("UPDATE tickets SET status='Open' WHERE ticket_id='T1'")
    with pytest.raises(ValueError, match="Ticket changed"):
        confirm_action(1, stale["proposal_id"])


def test_assist_restores_history(workspace, monkeypatch):
    from fastapi.testclient import TestClient
    import app
    import routers.assist as assist
    captured = []
    for name in ("build_grounded_site_visit_document_assist", "build_grounded_project_amenities_assist", "build_grounded_project_location_assist"):
        monkeypatch.setattr(assist, name, lambda request: None)
    def answer(**kwargs):
        captured.append(kwargs["conversation_messages"])
        return {"answer": "Hello", "matched_chunks": [], "confidence_label": "medium"}
    monkeypatch.setattr(assist, "run_support_orchestration", answer)
    monkeypatch.setattr(assist, "_enforce_live_property_data", lambda payload, *args: payload)
    from graph.main_orchestrator import TurnContext
    from services.turn_analysis_service import TurnAnalysis
    monkeypatch.setattr(assist, "prepare_turn", lambda issue, *args, **kwargs: TurnContext(
        [], issue, TurnAnalysis("general", "English", "latin", "test"), issue))
    client = TestClient(app.api)
    for issue in ("Hi", "What did I say?"):
        assert client.post("/api/support/assist", json={"issue": issue, "conversation_id": "c"}).status_code == 200
    assert captured[1] == [{"sender": "customer", "text": "Hi"}, {"sender": "bot", "text": "Hello"}]
    assert client.delete("/api/support/conversations/c").status_code == 200
