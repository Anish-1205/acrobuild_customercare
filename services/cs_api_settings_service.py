"""Durable CS API overrides; environment settings remain the initial defaults."""
import sqlite3
from contextlib import closing
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "support_system.db"


def _connect():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS cs_api_settings "
        "(id INTEGER PRIMARY KEY CHECK(id=1), base_url TEXT NOT NULL, "
        "api_key TEXT NOT NULL, company_id TEXT NOT NULL)"
    )
    connection.commit()
    return connection


def get_cs_api_settings(defaults):
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT base_url, api_key, company_id FROM cs_api_settings WHERE id=1"
        ).fetchone()
    return dict(zip(("base_url", "api_key", "company_id"), row)) if row else dict(defaults)


def save_cs_api_settings(base_url, api_key, company_id, defaults):
    with closing(_connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT api_key FROM cs_api_settings WHERE id=1").fetchone()
        key = api_key or (row[0] if row else defaults["api_key"])
        if not key:
            raise ValueError("An API key is required for the first configuration.")
        connection.execute(
            "INSERT INTO cs_api_settings VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "base_url=excluded.base_url, api_key=excluded.api_key, company_id=excluded.company_id",
            (base_url, key, str(company_id)),
        )
    return {"base_url": base_url, "company_id": str(company_id), "api_key_configured": True}
