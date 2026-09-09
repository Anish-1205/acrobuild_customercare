import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from services.migration_service import apply_migrations


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    from services import database_service as database, admin_settings_service as settings
    import services.auth_service as auth
    path = str(tmp_path / "support.db")
    monkeypatch.setattr(database, "DB_PATH", path)
    monkeypatch.setattr(settings, "DB_PATH", path)
    monkeypatch.setattr(settings, "ADMIN_SETTINGS_READY", False)
    monkeypatch.setattr(auth, "SECRET_KEY", "test-only-secret-" * 4)
    database.initialize_database()
    apply_migrations(path)
    with closing(database.open_database_connection()) as conn, conn:
        conn.execute("DELETE FROM support_users")
        conn.execute("INSERT INTO support_users(id,name,email,role,status,password) VALUES(1,'Agent One','agent@example.com','agent','Active',?)", (auth.hash_password("correct-password"),))
    return path


def test_migrations_idempotent(workspace):
    apply_migrations(workspace)
    with closing(sqlite3.connect(workspace)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 3


def test_cookie_login_csrf_logout_and_revocation(workspace):
    import app
    client = TestClient(app.api)
    response = client.post("/auth/login", json={"email": "agent@example.com", "password": "correct-password"})
    assert response.status_code == 200
    assert "access_token" not in response.json()
    assert "HttpOnly" in response.headers["set-cookie"]
    token = client.cookies["workspace_session"]
    assert client.get("/auth/me").status_code == 200
    assert client.post("/auth/logout").status_code == 403
    response = client.post("/auth/logout", headers={"X-CSRF-Token": client.cookies["workspace_csrf"]})
    assert response.status_code == 200
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_refresh_replay_revokes_session(workspace):
    from services.session_service import issue_session, rotate_session, active_session
    from services.auth_service import decode_access_token
    access, refresh = issue_session({"id": 1, "role": "agent"})
    _, (next_access, _) = rotate_session(refresh)
    with pytest.raises(ValueError):
        rotate_session(refresh)
    with pytest.raises(ValueError):
        active_session(decode_access_token(next_access))


def test_agent_cannot_read_another_agents_ticket(workspace):
    import app
    from services.database_service import open_database_connection
    with closing(open_database_connection()) as conn, conn:
        conn.execute("INSERT INTO tickets(ticket_id,assigned_agent) VALUES('T-OTHER','Someone Else')")
    client = TestClient(app.api)
    client.post("/auth/login", json={"email": "agent@example.com", "password": "correct-password"})
    assert client.get("/api/admin/tickets/T-OTHER/detail").status_code == 404
    assert client.get("/api/admin/tickets").json()["total"] == 0


def test_rate_limit_is_durable(workspace):
    from services.request_security_service import consume_limit
    assert consume_limit("ip", "login", 2)
    assert consume_limit("ip", "login", 2)
    assert not consume_limit("ip", "login", 2)
