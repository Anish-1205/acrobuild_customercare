"""Cookie-scoped, bounded conversation history shared across backend workers."""
import hashlib
import base64
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

# Session state that must survive into the next turn but must not depend on the
# (localized, any-language) visible answer text. U+2063 INVISIBLE SEPARATOR
# never appears in natural language or model output, so appending it to the
# stored bot text is an unambiguous, language-independent flag — invisible in
# the text actually shown to the customer, since callers pass it only to the
# stored copy, never to the API response.
_MARKER_CHAR = "⁣"
PENDING_CALL_BOOKING_MARKER = f"{_MARKER_CHAR}pending_call_booking{_MARKER_CHAR}"
PENDING_HUMAN_CONTACT_MARKER = f"{_MARKER_CHAR}pending_human_contact{_MARKER_CHAR}"
_PENDING_PROJECT_LOOKUP_PREFIX = f"{_MARKER_CHAR}pending_project_lookup:"


def has_pending_call_booking_marker(message_text):
    return PENDING_CALL_BOOKING_MARKER in str(message_text or "")


def has_pending_human_contact_marker(message_text):
    return PENDING_HUMAN_CONTACT_MARKER in str(message_text or "")


def build_pending_project_lookup_marker(kind, selector="", retry_count=0):
    state = kind if isinstance(kind, dict) else {
        "kind": str(kind or ""), "selector": str(selector or ""),
        "retry_count": int(retry_count or 0),
    }
    payload = json.dumps(state, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return f"{_PENDING_PROJECT_LOOKUP_PREFIX}{encoded}{_MARKER_CHAR}"


def get_pending_project_lookup(message_text):
    text = str(message_text or "")
    match = re.search(re.escape(_PENDING_PROJECT_LOOKUP_PREFIX) + r"([A-Za-z0-9_-]+)" + re.escape(_MARKER_CHAR), text)
    if not match:
        return None
    try:
        encoded = match.group(1)
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if payload.get("kind") not in {"amenities", "pricing", "location", "selection"}:
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


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

    def append(self, issue, answer, marker=""):
        if not self.conversation_id or not answer:
            return
        stored_answer = f"{str(answer)[:10000]}{marker}" if marker else str(answer)[:10000]
        with closing(open_database_connection()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM conversation_turns WHERE expires_at<=?", (time.time(),))
            position = conn.execute("SELECT COALESCE(MAX(position),0) FROM conversation_turns WHERE session_hash=? AND conversation_id=?", (self.owner, self.conversation_id)).fetchone()[0]
            expiry = time.time() + RETENTION_SECONDS
            for index, (sender, text) in enumerate((("customer", issue), ("bot", stored_answer)), start=1):
                conn.execute("INSERT INTO conversation_turns VALUES(?,?,?,?,?,?)", (self.owner, self.conversation_id, position + index, sender, str(text) if sender == "bot" else str(text)[:10000], expiry))
            conn.execute("DELETE FROM conversation_turns WHERE session_hash=? AND conversation_id=? AND position<=?", (self.owner, self.conversation_id, position + 2 - MAX_MESSAGES))
            conn.execute("UPDATE conversation_turns SET expires_at=? WHERE session_hash=? AND conversation_id=?", (expiry, self.owner, self.conversation_id))

    def clear(self):
        with closing(open_database_connection()) as conn, conn:
            conn.execute("DELETE FROM conversation_turns WHERE session_hash=? AND conversation_id=?", (self.owner, self.conversation_id))
