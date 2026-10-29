"""Cookie-scoped, bounded conversation history shared across backend workers."""
import hashlib
import json
import os
import re
import secrets
import time
from contextlib import closing

from services.database_service import open_database_connection

COOKIE_NAME = "support_conversation_session"
RETENTION_SECONDS = 7200
MAX_MESSAGES = 60


class ConversationSession:
    def __init__(self, cookie, conversation_id):
        self.token = cookie if re.fullmatch(r"[A-Za-z0-9_-]{43}", cookie or "") else secrets.token_urlsafe(32)
        self.owner = hashlib.sha256(self.token.encode()).hexdigest()
        self.conversation_id = str(conversation_id or "")[:128]

    def set_cookie(self, response):
        response.set_cookie(COOKIE_NAME, self.token, httponly=True, samesite="strict",
                            secure=os.getenv("ACROBUILD_ENV") == "production", max_age=RETENTION_SECONDS)

    def load(self):
        if not self.conversation_id:
            return []
        with closing(open_database_connection()) as conn, conn:
            conn.execute("DELETE FROM conversation_turns WHERE expires_at<=?", (time.time(),))
            rows = conn.execute(
                "SELECT sender,text FROM conversation_turns WHERE session_hash=? AND conversation_id=? ORDER BY position",
                (self.owner, self.conversation_id)).fetchall()
        return [{"sender": sender, "text": text} for sender, text in rows]

    def append(self, issue, answer):
        if not self.conversation_id or not answer:
            return
        with closing(open_database_connection()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM conversation_turns WHERE expires_at<=?", (time.time(),))
            position = conn.execute("SELECT COALESCE(MAX(position),0) FROM conversation_turns WHERE session_hash=? AND conversation_id=?", (self.owner, self.conversation_id)).fetchone()[0]
            expiry = time.time() + RETENTION_SECONDS
            for index, (sender, text) in enumerate((("customer", issue), ("bot", answer)), start=1):
                conn.execute("INSERT INTO conversation_turns VALUES(?,?,?,?,?,?)", (self.owner, self.conversation_id, position + index, sender, str(text)[:10000], expiry))
            conn.execute("DELETE FROM conversation_turns WHERE session_hash=? AND conversation_id=? AND position<=?", (self.owner, self.conversation_id, position + 2 - MAX_MESSAGES))
            conn.execute("UPDATE conversation_turns SET expires_at=? WHERE session_hash=? AND conversation_id=?", (expiry, self.owner, self.conversation_id))

    def get_state(self):
        """Small per-conversation JSON state (active booking flow, frustration count)."""
        if not self.conversation_id:
            return {}
        with closing(open_database_connection()) as conn, conn:
            conn.execute("DELETE FROM conversation_state WHERE expires_at<=?", (time.time(),))
            row = conn.execute("SELECT state FROM conversation_state WHERE session_hash=? AND conversation_id=?",
                               (self.owner, self.conversation_id)).fetchone()
        try:
            return json.loads(row[0]) if row else {}
        except ValueError:
            return {}

    def set_state(self, state):
        if not self.conversation_id:
            return
        with closing(open_database_connection()) as conn, conn:
            if state:
                conn.execute("INSERT OR REPLACE INTO conversation_state VALUES(?,?,?,?)",
                             (self.owner, self.conversation_id, json.dumps(state), time.time() + RETENTION_SECONDS))
            else:
                conn.execute("DELETE FROM conversation_state WHERE session_hash=? AND conversation_id=?", (self.owner, self.conversation_id))

    def clear(self):
        with closing(open_database_connection()) as conn, conn:
            conn.execute("DELETE FROM conversation_turns WHERE session_hash=? AND conversation_id=?", (self.owner, self.conversation_id))
            conn.execute("DELETE FROM conversation_state WHERE session_hash=? AND conversation_id=?", (self.owner, self.conversation_id))
