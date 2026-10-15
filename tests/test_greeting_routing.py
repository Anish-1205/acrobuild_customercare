"""Exploratory greetings must stay "general", not get flipped to "property".

Regression for a confirmed Stage 5 independent-QA defect: "Hi, I'm exploring
homes. What can you help me with?" was answered with a live project/RERA
dump. The turn analyzer (services/turn_analysis_service.py) correctly labels
this "general"; routers/assist.py:_prepare_lookup_turn then overrode it back
to "property" because is_reverse_amenity_query() is a shape-only test
("which/what ... homes/projects") that also matches a plain greeting
containing the words "homes" and "what". The fix requires a live amenity name
to actually be present too, matching how build_grounded_amenity_search_assist
itself already gates (api_context.py:1256-1270).
"""
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

import api_context
from app import api
from graph import main_orchestrator
from graph.main_orchestrator import TurnContext
from routers import assist
from services import amenity_search_service as amenity
from services import property_clarification_service as clarification
from services.conversation_store_service import build_pending_project_lookup_marker
from services.turn_analysis_service import TurnAnalysis

_PROJECTS = [{"id": 1, "projectName": "Vishwajeet Prime", "city": "Thane", "locality": ""}]
_AMENITIES = {1: [{"iconName": "Gym", "type": "Amenities"}]}


@pytest.fixture
def fixed_catalogue(monkeypatch):
    monkeypatch.setattr(amenity, "get_company_projects", lambda: list(_PROJECTS))
    monkeypatch.setattr(amenity, "get_project_amenities", lambda pid: list(_AMENITIES.get(pid, [])))
    monkeypatch.setattr(main_orchestrator, "get_live_project_names", lambda: [project["projectName"] for project in _PROJECTS])


def _analyze_as(intent, english=None):
    def analyze(issue, *_args, **_kwargs):
        return TurnAnalysis(intent, "English", "latin", "test", english=english or issue)
    return analyze


@pytest.mark.parametrize("issue", [
    "Hi, I'm exploring homes. What can you help me with?",
    "Hi there!",
    "What can you do?",
])
def test_exploratory_greetings_stay_general(issue, fixed_catalogue, monkeypatch):
    monkeypatch.setattr(main_orchestrator, "analyze_turn", _analyze_as("general"))
    request = assist.SupportAssistRequest(issue=issue, conversation_id="greet-1")
    _pending, _req, _processing_issue, turn = assist._prepare_lookup_turn(request, issue, slots=None)
    assert turn.analysis.intent == "general"


def test_reverse_amenity_query_still_routes_to_property(fixed_catalogue, monkeypatch):
    issue = "Which projects have a gym?"
    monkeypatch.setattr(main_orchestrator, "analyze_turn", _analyze_as("general"))
    request = assist.SupportAssistRequest(issue=issue, conversation_id="greet-2")
    _pending, _req, _processing_issue, turn = assist._prepare_lookup_turn(request, issue, slots=None)
    assert turn.analysis.intent == "property"


def test_unknown_amenity_shape_without_a_live_amenity_name_stays_general(fixed_catalogue, monkeypatch):
    # Same "which ... homes/projects" shape as a reverse amenity query, but no
    # live amenity is named -- must not be promoted to "property" on shape alone.
    issue = "Which projects do you personally like best?"
    monkeypatch.setattr(main_orchestrator, "analyze_turn", _analyze_as("general"))
    request = assist.SupportAssistRequest(issue=issue, conversation_id="greet-3")
    _pending, _req, _processing_issue, turn = assist._prepare_lookup_turn(request, issue, slots=None)
    assert turn.analysis.intent == "general"


def test_explicit_property_request_is_unaffected(fixed_catalogue, monkeypatch):
    issue = "What is the price of a 2 BHK in Vishwajeet Prime?"
    monkeypatch.setattr(main_orchestrator, "analyze_turn", _analyze_as("property"))
    request = assist.SupportAssistRequest(issue=issue, conversation_id="greet-4")
    _pending, _req, _processing_issue, turn = assist._prepare_lookup_turn(request, issue, slots=None)
    assert turn.analysis.intent == "property"


def test_greeting_combined_with_a_real_property_request_routes_to_property(fixed_catalogue, monkeypatch):
    issue = "Hi! I'm exploring homes -- what 2 BHK options do you have in Thane?"
    monkeypatch.setattr(main_orchestrator, "analyze_turn", _analyze_as("property"))
    request = assist.SupportAssistRequest(issue=issue, conversation_id="greet-5")
    _pending, _req, _processing_issue, turn = assist._prepare_lookup_turn(request, issue, slots=None)
    assert turn.analysis.intent == "property"


@pytest.mark.parametrize("intent", ["property", "general"])
def test_broad_project_request_does_not_read_amenities(intent, fixed_catalogue, monkeypatch):
    issue = "What projects do you have?"
    monkeypatch.setattr(main_orchestrator, "analyze_turn", _analyze_as(intent))

    def unexpected_read():
        pytest.fail("A catalogue browse must not read the amenity index")

    monkeypatch.setattr(assist, "live_amenity_index", unexpected_read)
    request = assist.SupportAssistRequest(issue=issue, conversation_id="browse-no-amenities")
    _pending, _req, processing_issue, turn = assist._prepare_lookup_turn(request, issue, slots=None)
    assert assist._is_broad_project_request(processing_issue, turn.property_issue)
    assert turn.analysis.intent == intent


def test_property_amenity_question_defers_live_read_to_grounded_builder(fixed_catalogue, monkeypatch):
    issue = "Which projects have a gym?"
    monkeypatch.setattr(main_orchestrator, "analyze_turn", _analyze_as("property"))

    def unexpected_early_read():
        pytest.fail("Property intent is already known before the grounded amenity builder")

    monkeypatch.setattr(assist, "live_amenity_index", unexpected_early_read)
    request = assist.SupportAssistRequest(issue=issue, conversation_id="property-amenity")
    _pending, _req, _processing_issue, turn = assist._prepare_lookup_turn(request, issue, slots=None)
    assert turn.analysis.intent == "property"


@pytest.fixture
def stateless_assist(monkeypatch):
    class Session:
        def __init__(self, *_args):
            pass

        def set_cookie(self, _response):
            pass

        def load(self):
            return []

        def append(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr(assist, "ConversationSession", Session)
    monkeypatch.setattr(assist, "_complete_payload", lambda payload, *_args: payload)


def _response_payload(response, path):
    assert response.status_code == 200
    if path.endswith("/stream"):
        return [json.loads(line) for line in response.text.splitlines() if line][-1]["response"]
    return response.json()


@pytest.mark.parametrize("path", ["/api/support/assist", "/api/support/assist/stream"])
@pytest.mark.parametrize("intent", ["property", "general"])
def test_browse_endpoint_survives_unrelated_amenity_failure(path, intent, fixed_catalogue, stateless_assist,
                                                            monkeypatch):
    monkeypatch.setattr(main_orchestrator, "analyze_turn", _analyze_as(intent))
    monkeypatch.setattr(clarification, "get_company_projects", lambda: list(_PROJECTS))

    def unavailable_amenities():
        pytest.fail("The unrelated amenity API must not run for a catalogue browse")

    monkeypatch.setattr(assist, "live_amenity_index", unavailable_amenities)
    response = TestClient(api).post(path, json={"issue": "What projects do you have?"})
    payload = _response_payload(response, path)
    assert payload["route"] == "property"
    assert [reply["value"] for reply in payload["quick_replies"]] == ["Vishwajeet Prime"]


@pytest.mark.parametrize("path", ["/api/support/assist", "/api/support/assist/stream"])
@pytest.mark.parametrize("intent,expected_reads", [("property", 1), ("general", 2)])
def test_amenity_endpoint_uses_grounded_index(path, intent, expected_reads, fixed_catalogue, stateless_assist,
                                              monkeypatch):
    monkeypatch.setattr(main_orchestrator, "analyze_turn", _analyze_as(intent))
    reads = []

    def tracked_index():
        reads.append(True)
        return amenity.live_amenity_index()

    monkeypatch.setattr(assist, "live_amenity_index", tracked_index)
    monkeypatch.setattr(api_context, "live_amenity_index", tracked_index)
    response = TestClient(api).post(path, json={"issue": "Which projects in Thane have a gym?"})
    payload = _response_payload(response, path)
    assert payload["route"] == "property"
    assert "Vishwajeet Prime" in payload["answer"]
    assert len(reads) == expected_reads


def test_pending_project_can_still_be_narrowed_by_amenity(fixed_catalogue, monkeypatch):
    issue = "one with a gym"
    marker = build_pending_project_lookup_marker({
        "kind": "selection", "entity": "project", "options": ["Vishwajeet Prime"],
        "original_issue": "What projects do you have?", "scope": {}, "purpose": "explore_project",
    })
    monkeypatch.setattr(assist, "prepare_turn", lambda text, *_args: TurnContext(
        [], text, TurnAnalysis("property", "English", "latin", "test"), text,
    ))
    reads = []

    def tracked_index():
        reads.append(True)
        return amenity.live_amenity_index()

    monkeypatch.setattr(assist, "live_amenity_index", tracked_index)
    request = assist.SupportAssistRequest(issue=issue, conversation_messages=[
        {"sender": "bot", "text": "Choose a project" + marker},
    ])
    pending, _req, processing_issue, turn = assist._prepare_lookup_turn(request, issue, slots=None)
    assert pending and pending["options"] == ["Vishwajeet Prime"]
    assert processing_issue == issue
    assert turn.analysis.intent == "property"
    assert len(reads) == 1


def test_new_catalogue_question_replaces_pending_choice_without_amenity_read(fixed_catalogue, monkeypatch):
    issue = "What projects do you have?"
    marker = build_pending_project_lookup_marker({
        "kind": "selection", "entity": "project", "options": ["Vishwajeet Prime"],
        "original_issue": "Which project has a gym?", "scope": {}, "purpose": "amenity_search",
    })
    monkeypatch.setattr(assist, "prepare_turn", lambda text, *_args: TurnContext(
        [], text, TurnAnalysis("property", "English", "latin", "test"), text,
    ))

    def unexpected_read():
        pytest.fail("A new catalogue request replaces the old amenity selection")

    monkeypatch.setattr(assist, "live_amenity_index", unexpected_read)
    request = assist.SupportAssistRequest(issue=issue, conversation_messages=[
        {"sender": "bot", "text": "Choose a project" + marker},
    ])
    pending, _req, processing_issue, turn = assist._prepare_lookup_turn(request, issue, slots=None)
    assert pending is None
    assert processing_issue == issue
    assert assist._is_broad_project_request(processing_issue, turn.property_issue)
