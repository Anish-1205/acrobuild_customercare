"""Forward-only, transactional SQLite migrations for existing installations."""
import sqlite3
from contextlib import closing


MIGRATIONS = {
    1: (
        "CREATE INDEX IF NOT EXISTS idx_tickets_customer ON tickets(customer_email)",
        "CREATE INDEX IF NOT EXISTS idx_tickets_queue ON tickets(assigned_agent,status,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_messages_ticket ON messages(ticket_id,id)",
        "CREATE INDEX IF NOT EXISTS idx_notes_ticket ON ticket_notes(ticket_id,id)",
    ),
    2: (
        "CREATE TABLE IF NOT EXISTS security_sessions (jti TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires_at REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)",
        "CREATE TABLE IF NOT EXISTS refresh_sessions (digest TEXT PRIMARY KEY, user_id INTEGER NOT NULL, family TEXT NOT NULL, expires_at REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0)",
        "CREATE TABLE IF NOT EXISTS request_limits (bucket TEXT PRIMARY KEY, window_start INTEGER NOT NULL, count INTEGER NOT NULL)",
        "CREATE TABLE IF NOT EXISTS audit_events (id INTEGER PRIMARY KEY, request_id TEXT, event TEXT NOT NULL, actor TEXT, subject TEXT, metadata TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL)",
        "CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at)",
    ),
    3: (
        "CREATE TABLE IF NOT EXISTS action_proposals (id TEXT PRIMARY KEY, actor INTEGER NOT NULL, ticket_id TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, expires_at REAL NOT NULL, completed INTEGER NOT NULL DEFAULT 0)",
        "CREATE TABLE IF NOT EXISTS ticket_feedback (ticket_id TEXT NOT NULL, email_hash TEXT NOT NULL, rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5), created_at REAL NOT NULL, PRIMARY KEY(ticket_id,email_hash))",
        "CREATE TABLE IF NOT EXISTS conversation_turns (session_hash TEXT NOT NULL, conversation_id TEXT NOT NULL, position INTEGER NOT NULL, sender TEXT NOT NULL, text TEXT NOT NULL, expires_at REAL NOT NULL, PRIMARY KEY(session_hash,conversation_id,position))",
        "CREATE INDEX IF NOT EXISTS idx_conversation_expiry ON conversation_turns(expires_at)",
    ),
}


def apply_migrations(database_path):
    with closing(sqlite3.connect(database_path, timeout=30)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            versions = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
            for version, statements in sorted(MIGRATIONS.items()):
                if version in versions:
                    continue
                for statement in statements:
                    conn.execute(statement)
                conn.execute("INSERT INTO schema_migrations(version) VALUES(?)", (version,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
