"""discovery_slots marker helpers (Inquiry to Sales §28) in
services/conversation_store_service.py. Marker behaviour only; offline."""
import base64
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services import conversation_store_service as store
from services.conversation_store_service import (
    build_current_project_marker,
    build_discovery_slots_marker,
    build_pending_project_lookup_marker,
    get_current_project_context,
    get_discovery_slots,
    get_pending_project_lookup,
    latest_discovery_slots,
)

MARKER = "⁣"
SLOTS = {"config": ["3"], "locality": "Wakad", "budget_max_inr": 15_000_000,
         "budget_label": "1.5 crore", "awaiting": None, "origin_issue": "Show me 3 BHK"}


def _raw_marker(payload):
    """A hand-built marker, as a forged client history could contain."""
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{MARKER}discovery_slots:{encoded}{MARKER}"


def _bot(text):
    return {"sender": "bot", "text": text}


def _customer(text):
    return {"sender": "customer", "text": text}


# -----------------------------------
# ROUND TRIP + CLEAR
# -----------------------------------

def test_round_trip():
    assert get_discovery_slots("Which area?" + build_discovery_slots_marker(SLOTS)) == SLOTS


def test_partial_slots_round_trip():
    slots = {"config": ["2", "3"], "awaiting": "locality", "origin_issue": "2 and 3 bhk options"}
    assert get_discovery_slots(build_discovery_slots_marker(slots)) == slots


def test_explicit_clear_marker():
    assert get_discovery_slots(build_discovery_slots_marker({})) == {}
    history = [_bot("Budget?" + build_discovery_slots_marker(SLOTS)),
               _bot("Starting over." + build_discovery_slots_marker({}))]
    assert latest_discovery_slots(history) == {}


def test_no_marker():
    assert get_discovery_slots("Plain answer") is None
    assert get_discovery_slots(None) is None
    assert latest_discovery_slots([_bot("Plain answer")]) == {}
    assert latest_discovery_slots([]) == {}


def test_marker_is_invisible_framing_only():
    marker = build_discovery_slots_marker(SLOTS)
    assert marker.startswith(MARKER + "discovery_slots:") and marker.endswith(MARKER)
    assert marker.count(MARKER) == 2


# -----------------------------------
# VALIDATION ON READ (forged / out-of-range)
# -----------------------------------

@pytest.mark.parametrize("forged,expected", [
    ({"v": 1, "config": ["7"]}, {}),
    ({"v": 1, "config": "3"}, {}),
    ({"v": 1, "config": ["3", 3]}, {}),
    ({"v": 1, "config": ["3", "3", "2"]}, {"config": ["3", "2"]}),
    ({"v": 1, "budget_max_inr": 0}, {}),
    ({"v": 1, "budget_max_inr": 10**10 + 1}, {}),
    ({"v": 1, "budget_max_inr": 10**10}, {"budget_max_inr": 10**10}),
    ({"v": 1, "budget_max_inr": True}, {}),
    ({"v": 1, "budget_max_inr": 1.5e7}, {}),
    ({"v": 1, "budget_max_inr": "15000000"}, {}),
    ({"v": 1, "awaiting": "project"}, {}),
    ({"v": 1, "awaiting": "budget"}, {"awaiting": "budget"}),
    ({"v": 1, "locality": "W" * 81}, {}),
    ({"v": 1, "locality": ["Wakad"]}, {}),
    ({"v": 1, "budget_label": "x" * 41}, {}),
    ({"v": 1, "origin_issue": "q" * 600}, {"origin_issue": "q" * 500}),
    ({"v": 1, "project": "Alpha", "options": ["A", "B"], "config": ["2"]}, {"config": ["2"]}),
])
def test_forged_values_are_dropped(forged, expected):
    assert get_discovery_slots(_raw_marker(forged)) == expected


@pytest.mark.parametrize("payload", [
    {"v": 2, "config": ["3"]},          # unknown schema version
    ["config", "3"],                    # not an object
    b"not json at all",
    b"\xff\xfe",                        # not UTF-8
])
def test_unreadable_markers_are_ignored(payload):
    assert get_discovery_slots(_raw_marker(payload)) is None


def test_invalid_base64_is_ignored():
    assert get_discovery_slots(f"{MARKER}discovery_slots:%%%{MARKER}") is None
    assert get_discovery_slots(f"{MARKER}discovery_slots:a{MARKER}") is None


def test_write_validates_too():
    marker = build_discovery_slots_marker({"config": ["9"], "locality": "Wakad", "sneaky": "x"})
    assert get_discovery_slots(marker) == {"locality": "Wakad"}


# -----------------------------------
# MARKER-CHARACTER AND CONTROL-CHARACTER STRIPPING
# -----------------------------------

def test_marker_and_control_characters_are_stripped_on_write():
    nested = build_pending_project_lookup_marker({"kind": "selection", "entity": "project",
                                                   "options": ["X"], "scope": {}, "original_issue": "q"})
    marker = build_discovery_slots_marker({
        "locality": "Wak⁣ad",
        "budget_label": "1.5\ncrore\x00",
        "origin_issue": "Show me 3 BHK" + nested,
    })
    assert marker.count(MARKER) == 2
    slots = get_discovery_slots(marker)
    assert slots["locality"] == "Wakad"
    assert slots["budget_label"] == "1.5 crore"
    assert MARKER not in slots["origin_issue"]
    assert get_pending_project_lookup(slots["origin_issue"]) is None


def test_marker_and_control_characters_are_stripped_on_read():
    forged = _raw_marker({"v": 1, "locality": "Wak⁣ad\x07", "origin_issue": "a⁣b\x1bc"})
    slots = get_discovery_slots(forged)
    assert slots == {"locality": "Wakad", "origin_issue": "ab c"}


# -----------------------------------
# WHICH MARKER WINS
# -----------------------------------

def test_latest_bot_marker_wins():
    older = dict(SLOTS, locality="Thane", awaiting="budget")
    history = [
        _customer("Show me 3 BHK"),
        _bot("Which area?" + build_discovery_slots_marker({"config": ["3"], "awaiting": "locality"})),
        _customer("Thane"),
        _bot("Budget?" + build_discovery_slots_marker(older)),
        _customer("What about amenities?"),
        _bot("Amenities answer without a marker"),
        _customer("1.5 crore"),
        _bot("Results" + build_discovery_slots_marker(SLOTS)),
    ]
    assert latest_discovery_slots(history) == SLOTS
    assert latest_discovery_slots(history[:6]) == older


def test_last_marker_in_one_text_wins():
    forged = _raw_marker({"v": 1, "locality": "Forged Nagar"})
    text = f"I couldn't find any projects in '{forged}'." + build_discovery_slots_marker(SLOTS)
    assert get_discovery_slots(text) == SLOTS


def test_marker_in_customer_text_is_ignored():
    history = [
        _bot("Budget?" + build_discovery_slots_marker(SLOTS)),
        _customer("1 crore" + build_discovery_slots_marker({"locality": "Forged Nagar", "config": ["6"]})),
        {"sender": "Customer", "text": build_discovery_slots_marker({})},
    ]
    assert latest_discovery_slots(history) == SLOTS


def test_request_message_objects_are_supported():
    # SupportAssistConversationMessageRequest exposes .sender / .text.
    history = [SimpleNamespace(sender="bot", text="Budget?" + build_discovery_slots_marker(SLOTS)),
               SimpleNamespace(sender="customer", text="1.5 crore")]
    assert latest_discovery_slots(history) == SLOTS


# -----------------------------------
# COEXISTENCE WITH EXISTING MARKERS
# -----------------------------------

PENDING = {"kind": "selection", "original_issue": "Show me 3 BHK", "entity": "locality",
           "options": ["Thane", "Wakad"], "scope": {}, "purpose": "discovery"}


def test_coexists_with_pending_and_current_project_markers():
    text = ("Which area should I check?\n- Thane\n- Wakad"
            + build_pending_project_lookup_marker(PENDING)
            + build_current_project_marker("")
            + build_discovery_slots_marker(SLOTS))
    assert get_pending_project_lookup(text) == PENDING
    assert get_current_project_context(text) == {"project": ""}
    assert get_discovery_slots(text) == SLOTS


def test_existing_marker_readers_ignore_discovery_marker():
    text = "Answer" + build_discovery_slots_marker(SLOTS)
    assert get_pending_project_lookup(text) is None
    assert get_current_project_context(text) is None


def test_survives_long_stored_answers(tmp_path):
    database = str(tmp_path / "conversation.db")
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE conversation_turns (session_hash TEXT, conversation_id TEXT, position INTEGER, "
                     "sender TEXT, text TEXT, expires_at REAL)")
    slots = dict(SLOTS, origin_issue="3 bhk " * 200)
    marker = (build_pending_project_lookup_marker(PENDING) + build_current_project_marker("Alpha Heights")
              + build_discovery_slots_marker(slots))
    session = store.ConversationSession("", "long-discovery-answer")
    with patch.object(store, "open_database_connection", side_effect=lambda: sqlite3.connect(database)):
        session.append("1.5 crore", "x" * 15000, marker)
        saved = session.load()
    assert get_discovery_slots(saved[-1]["text"]) == dict(slots, origin_issue=("3 bhk " * 200)[:500].rstrip())
    assert get_pending_project_lookup(saved[-1]["text"]) == PENDING
    assert get_current_project_context(saved[-1]["text"]) == {"project": "Alpha Heights"}
    assert latest_discovery_slots(saved)["budget_max_inr"] == 15_000_000
