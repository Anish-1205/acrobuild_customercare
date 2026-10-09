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
_CURRENT_PROJECT_PREFIX = f"{_MARKER_CHAR}current_project:"
_DISCOVERY_SLOTS_PREFIX = f"{_MARKER_CHAR}discovery_slots:"
_HOME_TYPE_SCOPE_PREFIX = f"{_MARKER_CHAR}home_type_scope:"


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


def build_current_project_marker(project_name=""):
    """Persist project scope independently of visible answer wording.

    An empty value explicitly resets scope for a new catalogue search.
    """
    payload = json.dumps({"project": str(project_name or "").strip()}, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return f"{_CURRENT_PROJECT_PREFIX}{encoded}{_MARKER_CHAR}"


def get_current_project_context(message_text):
    text = str(message_text or "")
    match = re.search(re.escape(_CURRENT_PROJECT_PREFIX) + r"([A-Za-z0-9_-]+)" + re.escape(_MARKER_CHAR), text)
    if not match:
        return None
    try:
        encoded = match.group(1)
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        return {"project": str(payload.get("project") or "").strip()}
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _validated_home_type_scope(scope):
    """Small, server-owned scope used by contextual subtype and price turns."""
    if not isinstance(scope, dict):
        return {}
    project = _clean_slot_text(scope.get("project"), 160, False)
    config = scope.get("config")
    if not project or not isinstance(config, list):
        return {}
    numbers = list(dict.fromkeys(
        value for value in config
        if isinstance(value, str) and re.fullmatch(r"[1-6]", value)
    ))
    if not numbers:
        return {}
    result = {"project": project, "config": numbers}
    subtype = str(scope.get("subtype") or "").strip().lower()
    if subtype == "duplex":
        result["subtype"] = subtype
    return result


def build_home_type_scope_marker(scope):
    """Persist verified BHK/subtype scope without parsing localized bot copy."""
    clean = _validated_home_type_scope(scope)
    payload = json.dumps(clean, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return f"{_HOME_TYPE_SCOPE_PREFIX}{encoded}{_MARKER_CHAR}"


def get_home_type_scope(message_text):
    pattern = re.escape(_HOME_TYPE_SCOPE_PREFIX) + r"([A-Za-z0-9_-]*)" + re.escape(_MARKER_CHAR)
    for encoded in reversed(re.findall(pattern, str(message_text or ""))):
        try:
            payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
        if payload == {}:
            return {}
        clean = _validated_home_type_scope(payload)
        if clean:
            return clean
    return None


def latest_home_type_scope(messages):
    """Newest trusted bot marker; customer-authored marker text is ignored."""
    for message in reversed(list(messages or [])):
        if str(_message_field(message, "sender") or "").lower() != "bot":
            continue
        scope = get_home_type_scope(_message_field(message, "text"))
        if scope is not None:
            return scope
    return {}


# -----------------------------------
# DISCOVERY SLOTS (Inquiry to Sales §28)
# -----------------------------------
# What a customer said while discovering homes (configuration, locality,
# budget), so "Show me 3 BHK" -> "Wakad" -> "1.5 crore" never has to be
# repeated. The project is deliberately not a slot: current_project above is
# its single source of truth. Values are validated on write and on read,
# because a marker can come back from client-supplied history.

_DISCOVERY_SLOTS_VERSION = 1
_DISCOVERY_AWAITING = frozenset({"locality", "budget"})
_MAX_DISCOVERY_BUDGET_INR = 10**10
_MAX_LOCALITY_CHARS = 80
_MAX_BUDGET_LABEL_CHARS = 40
_MAX_ORIGIN_ISSUE_CHARS = 500
# C0/C1 control characters become spaces; the (invisible) marker character is
# removed outright, so a forged or echoed value can never carry a nested marker.
_CONTROL_CHARS_RE = re.compile("[\\x00-\\x1f\\x7f-\\x9f]")


def _clean_slot_text(value, max_chars, truncate=False):
    """Safe single-line text, or None when the value is not usable."""
    if not isinstance(value, str):
        return None
    text = " ".join(_CONTROL_CHARS_RE.sub(" ", value.replace(_MARKER_CHAR, "")).split())
    if len(text) > max_chars:
        if not truncate:
            return None
        text = text[:max_chars].rstrip()
    return text


def _validated_discovery_slots(slots):
    """Known, well-formed slot values only; anything else is dropped, never raised.

    ``locality`` and ``budget_label`` over their caps are discarded (a partial
    place name must never look like a real one); ``origin_issue`` is truncated
    to 500 characters so a long question still keeps its intent."""
    if not isinstance(slots, dict):
        return {}
    clean = {}
    config = slots.get("config")
    if isinstance(config, list) and all(isinstance(value, str) and re.fullmatch(r"[1-6]", value) for value in config):
        clean["config"] = list(dict.fromkeys(config))
    budget = slots.get("budget_max_inr")
    if isinstance(budget, int) and not isinstance(budget, bool) and 1 <= budget <= _MAX_DISCOVERY_BUDGET_INR:
        clean["budget_max_inr"] = budget
    elif "budget_max_inr" in slots and budget is None:
        clean["budget_max_inr"] = None
    if "awaiting" in slots and (slots["awaiting"] is None or slots["awaiting"] in _DISCOVERY_AWAITING):
        clean["awaiting"] = slots["awaiting"]
    for key, limit, truncate in (("locality", _MAX_LOCALITY_CHARS, False),
                                 ("budget_label", _MAX_BUDGET_LABEL_CHARS, False),
                                 ("origin_issue", _MAX_ORIGIN_ISSUE_CHARS, True)):
        text = _clean_slot_text(slots.get(key), limit, truncate)
        if text:
            clean[key] = text
    return clean


def build_discovery_slots_marker(slots):
    """Server-only discovery slot state. ``{}`` (or slots that validate to
    nothing) writes an explicit clear marker."""
    clean = _validated_discovery_slots(slots)
    state = {"v": _DISCOVERY_SLOTS_VERSION, **clean} if clean else {}
    payload = json.dumps(state, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return f"{_DISCOVERY_SLOTS_PREFIX}{encoded}{_MARKER_CHAR}"


def get_discovery_slots(message_text):
    """Validated slots from the last discovery marker in ``message_text``.

    Returns None when there is no readable marker, ``{}`` for an explicit
    clear. The last marker wins because the real one is always appended after
    the visible answer, which may echo customer text."""
    pattern = re.escape(_DISCOVERY_SLOTS_PREFIX) + r"([A-Za-z0-9_-]*)" + re.escape(_MARKER_CHAR)
    for encoded in reversed(re.findall(pattern, str(message_text or ""))):
        try:
            payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if payload and payload.get("v") != _DISCOVERY_SLOTS_VERSION:
            continue
        return _validated_discovery_slots(payload)
    return None


def _message_field(message, name):
    if isinstance(message, dict):
        return message.get(name, "")
    return getattr(message, name, "")


def latest_discovery_slots(messages):
    """Newest discovery slots from stored bot messages; ``{}`` when none or cleared.

    Customer-authored text is never read, so a typed marker has no effect."""
    for message in reversed(list(messages or [])):
        if str(_message_field(message, "sender") or "").lower() != "bot":
            continue
        slots = get_discovery_slots(_message_field(message, "text"))
        if slots is not None:
            return slots
    return {}


def customer_visible_history(messages):
    """Return only displayable turns; server state stays in stored bot rows."""
    visible = []
    for message in messages:
        sender = str(_message_field(message, "sender") or "").lower()
        if sender not in {"customer", "bot"}:
            continue
        text = str(_message_field(message, "text") or "")
        text = text.split(_MARKER_CHAR, 1)[0]
        visible.append({"sender": sender, "text": text})
    return visible


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
