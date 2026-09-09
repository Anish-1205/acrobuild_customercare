import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from services import knowledge_ingestion_service as ingestion
from services import otp_service
from services.auth_service import create_access_token, decode_access_token
from services.database_service import ensure_ticket_counter, generate_next_ticket_id


def test_workspace_token_requires_configured_secret(monkeypatch):
    import services.auth_service as auth
    monkeypatch.setattr(auth, "SECRET_KEY", "")
    with pytest.raises(RuntimeError):
        create_access_token({"sub": "1", "role": "admin"})


def test_workspace_token_round_trip(monkeypatch):
    import services.auth_service as auth
    monkeypatch.setattr(auth, "SECRET_KEY", "x" * 40)
    token = create_access_token({"sub": "1", "role": "admin"})
    assert decode_access_token(token)["role"] == "admin"


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
def test_ssrf_blocks_non_public_addresses(monkeypatch, address):
    monkeypatch.setattr(ingestion.socket, "getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, (address, 80))])
    with pytest.raises(ValueError, match="not allowed"):
        ingestion.validate_public_remote_url("http://example.invalid/private")


def test_ssrf_blocks_url_credentials():
    with pytest.raises(ValueError):
        ingestion.validate_public_remote_url("https://user:password@example.com/")


def test_remote_download_content_length_limit(monkeypatch):
    monkeypatch.setattr(ingestion.socket, "getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, ("8.8.8.8", 443))])

    class Response:
        headers = {"content-length": str(ingestion.MAX_REMOTE_DOWNLOAD_BYTES + 1)}
        is_redirect = False
        is_permanent_redirect = False
        def raise_for_status(self): pass
        def close(self): pass

    monkeypatch.setattr(ingestion.requests, "get", lambda *args, **kwargs: Response())
    with pytest.raises(ValueError, match="10 MB"):
        ingestion.fetch_remote_knowledge_source("https://example.com/file.pdf")


def test_ticket_counter_is_atomic(tmp_path):
    database_path = tmp_path / "counter.db"

    def allocate(_):
        conn = sqlite3.connect(database_path, timeout=10)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS tickets(ticket_id TEXT PRIMARY KEY)")
        ensure_ticket_counter(cursor)
        ticket_id = generate_next_ticket_id(cursor)
        conn.commit()
        conn.close()
        return ticket_id

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(allocate, range(40)))
    assert len(set(ids)) == 40


def test_otp_store_survives_module_state_and_enforces_email_binding(tmp_path, monkeypatch):
    import services.database_service as database
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "otp.db"))
    monkeypatch.setenv("OTP_SECRET", "test-secret-long-enough")
    conn = database.open_database_connection()
    otp_service._ensure_store(conn)
    token = "opaque-token"
    conn.execute(
        "INSERT INTO email_access_tokens(token_hash,email,expires_at) VALUES(?,?,?)",
        (otp_service._digest(token), "owner@example.com", otp_service.time.time() + 60),
    )
    conn.commit()
    conn.close()
    assert otp_service.validate_email_access_token("owner@example.com", token)
    assert not otp_service.validate_email_access_token("other@example.com", token)
