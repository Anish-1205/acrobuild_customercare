import json

import pytest
from fastapi.testclient import TestClient

from graph.main_orchestrator import TurnContext, localize_response
from services.turn_analysis_service import TurnAnalysis
from services import property_clarification_service as clarification
from services.conversation_store_service import build_pending_project_lookup_marker
from routers import assist
from app import api


PROJECTS = [
    {"id": 1, "projectName": "Vishwajeet Heights", "city": "Thane", "locality": "Kompally"},
    {"id": 2, "projectName": "Green Acres", "city": "Hyderabad", "locality": "Kompally"},
    {"id": 3, "projectName": "Sunrise Towers", "city": "Pune", "locality": "Hadapsar"},
]


@pytest.mark.parametrize("issue", [
    "What projects do you have?", "What projects are available?",
    "hi mee kada em projects vunnai ?", "Browse all projects",
    "mee kada em projects vunnayi?", "What projects do you have with you?",
])
def test_broad_project_requests_are_neutral(issue, monkeypatch):
    monkeypatch.setattr(clarification, "get_company_projects", lambda: PROJECTS)
    assert assist._is_broad_project_request(issue)
    response = clarification.build_project_browse_response(issue)
    names = [choice["value"] for choice in response["quick_replies"]]
    assert names == [project["projectName"] for project in PROJECTS]
    first_line, *listed = response["answer"].splitlines()
    assert len(first_line) < 90 and "Vishwajeet" not in first_line
    assert [line[2:] for line in listed] == names  # plain-text fallback, API order
    assert response["pending_project_lookup"]["original_issue"] == issue


def test_project_choice_and_new_free_text(monkeypatch):
    monkeypatch.setattr(clarification, "get_company_projects", lambda: PROJECTS)
    state = clarification.build_project_browse_response("What projects do you have?")["pending_project_lookup"]
    assert clarification.continues_selection(state, "Green Acres")
    assert clarification.resume_selection(state, "Green Acres") == "Tell me about project Green Acres"
    assert not clarification.continues_selection(state, "Kompally lo em unnai?")
    assert not clarification.continues_selection(state, "What is the weather today?")
    narrowed = clarification.narrow_project_choice_by_locality(state, "Kompally lo em unnai?")
    assert [choice["value"] for choice in narrowed["quick_replies"]] == [
        "Vishwajeet Heights", "Green Acres",
    ]


def test_live_catalogue_failure_has_no_choices(monkeypatch):
    def unavailable():
        raise RuntimeError("unavailable")
    monkeypatch.setattr(clarification, "get_company_projects", unavailable)
    response = clarification.build_project_browse_response("What projects are available?")
    assert response["source_status"] == "failed"
    assert not response.get("quick_replies")
    assert response["pending_project_lookup"]["original_issue"] == "What projects are available?"


def test_tenglish_choice_keeps_official_names_and_rejects_padding(monkeypatch):
    from graph import main_orchestrator
    monkeypatch.setattr(clarification, "get_company_projects", lambda: PROJECTS)
    payload = clarification.build_project_browse_response("mee kada em projects vunnai?")
    bullets = "\n".join(f"- {project['projectName']}" for project in PROJECTS)
    monkeypatch.setattr(main_orchestrator, "generate_qwen_chat_response", lambda **_kwargs:
                        "Maaku 3 projects unnayi. Meeru edi choodalanukuntunnaru?\n" + bullets)
    analysis = TurnAnalysis("property", "Telugu", "latin", "test")
    localized = localize_response(payload, analysis)
    assert localized["answer"].startswith("Maaku 3 projects unnayi.")
    assert localized["quick_replies"] == payload["quick_replies"]
    # A translation that renames an option is rejected, never shown.
    monkeypatch.setattr(main_orchestrator, "generate_qwen_chat_response", lambda **_kwargs:
                        "Maaku 3 projects unnayi.\n- Vishwajeet Etthulu\n- Green Acres\n- Sunrise Towers")
    assert localize_response(payload, analysis)["answer"] == payload["answer"]
    # A one-line answer padded with invented lines is rejected.
    monkeypatch.setattr(main_orchestrator, "generate_qwen_chat_response", lambda **_kwargs:
                        "Live data ippudu ledu.\n* Malli try cheyandi")
    single = {"answer": "Live property data is unavailable right now. Please try again shortly."}
    assert localize_response(single, analysis)["answer"] == single["answer"]


@pytest.mark.parametrize("path", ["/api/support/assist", "/api/support/assist/stream"])
def test_both_assist_endpoints_return_project_choices(path, monkeypatch):
    monkeypatch.setattr(clarification, "get_company_projects", lambda: PROJECTS)
    monkeypatch.setattr(assist, "prepare_turn", lambda issue, *_args: TurnContext(
        [], issue, TurnAnalysis("property", "English", "latin", "test"), issue,
    ))
    monkeypatch.setattr(assist, "_complete_payload", lambda payload, *_args: payload)

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
    response = TestClient(api).post(path, json={"issue": "What projects do you have?"})
    assert response.status_code == 200
    payload = response.json() if not path.endswith("/stream") else [
        json.loads(line) for line in response.text.splitlines() if line
    ][-1]["response"]
    assert [choice["value"] for choice in payload["quick_replies"]] == [
        project["projectName"] for project in PROJECTS
    ]


def test_selection_marker_survives_and_new_question_replaces_it(monkeypatch):
    monkeypatch.setattr(clarification, "get_company_projects", lambda: PROJECTS)
    state = clarification.build_project_browse_response("What projects do you have?")["pending_project_lookup"]
    marker = build_pending_project_lookup_marker(state)
    monkeypatch.setattr(assist, "prepare_turn", lambda issue, *_args: TurnContext(
        [], issue, TurnAnalysis("property", "English", "latin", "test"), issue,
    ))
    monkeypatch.setattr(assist, "_narrows_selection_by_amenity", lambda *_args: False)
    monkeypatch.setattr(assist, "_narrows_selection_by_locality", lambda *_args: False)

    from api_context import SupportAssistRequest
    history = [{"sender": "bot", "text": "Choose a project" + marker}]
    selected = SupportAssistRequest(issue="Green Acres", conversation_messages=history)
    pending, _, issue, _ = assist._prepare_lookup_turn(selected, selected.issue)
    assert pending and issue == "Tell me about project Green Acres"
    changed = SupportAssistRequest(issue="What is the weather today?", conversation_messages=history)
    pending, _, issue, _ = assist._prepare_lookup_turn(changed, changed.issue)
    assert pending is None and issue == changed.issue


@pytest.mark.parametrize("original", ["mee kada em projects vunnayi ?", "What projects do you have with you?"])
def test_generic_discovery_marker_resumes_as_overview(original, monkeypatch):
    from api_context import SupportAssistRequest
    name = "Vishwajeet Precious Phase-V"
    state = {"kind": "selection", "entity": "project", "options": ["Vishwajeet Precious", name],
             "scope": {}, "original_issue": original}
    monkeypatch.setattr(assist, "prepare_turn", lambda issue, *_args: TurnContext(
        [], issue, TurnAnalysis("property", "Telugu", "latin", "test"), issue))
    request = SupportAssistRequest(issue=name, conversation_messages=[
        {"sender": "bot", "text": "Nenu ae project check cheyali?" + build_pending_project_lookup_marker(state)}])
    pending, _, issue, turn = assist._prepare_lookup_turn(request, name)
    assert issue == f"Tell me about project {name}"
    assert turn.property_issue == issue
    assert pending["scope"]["project"] == name
    assert pending["original_issue"] == original


def test_discovery_translation_cannot_drop_catalogue_framing(monkeypatch):
    from graph import main_orchestrator
    monkeypatch.setattr(clarification, "get_company_projects", lambda: PROJECTS)
    payload = clarification.build_project_browse_response("mee kada em projects vunnayi?")
    monkeypatch.setattr(main_orchestrator, "generate_qwen_chat_response", lambda **kwargs:
                        "Nenu ae project check cheyali?\n" + "\n".join(f"- {p['projectName']}" for p in PROJECTS))
    result = localize_response(payload, TurnAnalysis("property", "Telugu", "latin", "test"))
    assert result["answer"] == payload["answer"]


@pytest.mark.parametrize("entity,options,reply,expected", [
    ("wing", ["A", "B"], "A wing", True),
    ("wing", ["A", "B"], "wing B", True),
    ("floor", ["4", "5"], "5th floor", True),
    ("project", ["Green Acres", "Sunrise Towers"], "go with Green Acres", True),
    ("project", ["Green Acres", "Sunrise Towers"], "a", False),
    ("project", ["Green Acres", "Sunrise Towers"], "Kompally lo em unnai?", False),
    ("project", ["Green Acres", "Sunrise Towers"], "book a site visit tomorrow", False),
])
def test_selection_detection_matches_resume(entity, options, reply, expected):
    state = {"kind": "selection", "original_issue": "q", "entity": entity, "options": options, "scope": {}}
    assert clarification.continues_selection(state, reply) is expected
    if expected:
        assert clarification.resume_selection(dict(state), reply) != "q"


def test_retry_after_catalogue_outage_reoffers_projects(monkeypatch):
    def unavailable():
        raise RuntimeError("unavailable")
    monkeypatch.setattr(clarification, "get_company_projects", unavailable)
    state = clarification.build_project_browse_response("mee kada em projects vunnai?")["pending_project_lookup"]
    marker = build_pending_project_lookup_marker(state)
    monkeypatch.setattr(clarification, "get_company_projects", lambda: PROJECTS)
    monkeypatch.setattr(assist, "prepare_turn", lambda issue, *_args: TurnContext(
        [], issue, TurnAnalysis("property", "English", "latin", "test"), issue,
    ))
    from api_context import SupportAssistRequest
    request = SupportAssistRequest(issue="retry", conversation_messages=[
        {"sender": "bot", "text": "Unavailable" + marker}])
    pending, _, issue, turn = assist._prepare_lookup_turn(request, request.issue)
    assert pending and assist._is_broad_project_request(issue, turn.property_issue)


def test_choice_copy_names_family_only_when_customer_did():
    names = ["Vishwajeet Heights", "Vishwajeet Prime"]
    assert "Vishwajeet" not in clarification.build_project_choice_answer(
        names, "", "How do I book a site visit?").splitlines()[0]
    assert "Vishwajeet" in clarification.build_project_choice_answer(
        names, "", "vishwajeet price").splitlines()[0]


# -----------------------------------
# UNMATCHED SHORT REPLIES, AREA NO-MATCH, BROWSE PARITY
# -----------------------------------
WING_STATE = {"kind": "selection", "original_issue": "What wings are available in Vishwajeet Heights?",
              "entity": "wing", "options": ["IRIS", "TULIP"], "scope": {"project": "Vishwajeet Heights"}}


@pytest.mark.parametrize("reply,expected", [
    ("A", True), ("C wing", True), ("first one", True),
    ("IRIS", False), ("site visit", False), ("2bhk price", False),
    ("Kompally lo em unnai?", False), ("What is the weather today?", False), ("cancel", False),
])
def test_unmatched_short_reply_detection(reply, expected):
    assert clarification.is_unmatched_selection_reply(WING_STATE, reply) is expected


def _live_wings(monkeypatch, wings=("IRIS", "TULIP")):
    monkeypatch.setattr(clarification, "live_options", lambda entity, *_args: (entity, list(wings), {}))


def test_unmatched_reply_reasks_same_choice(monkeypatch):
    _live_wings(monkeypatch)
    payload = clarification.build_unmatched_selection_answer(dict(WING_STATE, effective_issue="x"))
    first, *listed = payload["answer"].splitlines()
    assert first == "That doesn't match any wing option. Which wing should I check in Vishwajeet Heights?"
    assert listed == ["- IRIS", "- TULIP"]
    assert [choice["value"] for choice in payload["quick_replies"]] == ["IRIS", "TULIP"]
    assert "effective_issue" not in payload["pending_project_lookup"]
    assert payload["pending_project_lookup"]["options"] == ["IRIS", "TULIP"]


def _english_turn(monkeypatch, intent="general"):
    monkeypatch.setattr(assist, "prepare_turn", lambda issue, *_args: TurnContext(
        [], issue, TurnAnalysis(intent, "English", "latin", "test", english=issue), issue,
    ))
    monkeypatch.setattr(assist, "_narrows_selection_by_amenity", lambda *_args: False)
    monkeypatch.setattr(assist, "_narrows_selection_by_locality", lambda *_args: False)


@pytest.mark.parametrize("reply,keeps_pending", [("A", True), ("thanks", False), ("ok", False),
                                                  ("How do I book a site visit?", False)])
def test_prepare_turn_keeps_choice_only_for_unmatched_short_reply(reply, keeps_pending, monkeypatch):
    from api_context import SupportAssistRequest
    _english_turn(monkeypatch)
    history = [{"sender": "bot", "text": "Which wing?" + build_pending_project_lookup_marker(WING_STATE)}]
    request = SupportAssistRequest(issue=reply, conversation_messages=history)
    pending, _, issue, turn = assist._prepare_lookup_turn(request, reply)
    assert bool(pending) is keeps_pending
    assert issue == reply  # never rewritten into the old question
    if keeps_pending:
        assert turn.analysis.is_property  # reaches the grounded re-ask, not general chat


@pytest.mark.parametrize("path", ["/api/support/assist", "/api/support/assist/stream"])
def test_both_endpoints_reask_on_unmatched_reply(path, monkeypatch):
    _english_turn(monkeypatch)
    _live_wings(monkeypatch)
    monkeypatch.setattr(assist, "build_grounded_amenity_search_assist", lambda *_args: None)
    monkeypatch.setattr(assist, "_complete_payload", lambda payload, *_args: payload)

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
    history = [{"sender": "bot", "text": "Which wing?" + build_pending_project_lookup_marker(WING_STATE)}]
    response = TestClient(api).post(path, json={"issue": "A", "conversation_messages": history})
    payload = response.json() if not path.endswith("/stream") else [
        json.loads(line) for line in response.text.splitlines() if line
    ][-1]["response"]
    assert payload["answer"].startswith("That doesn't match any wing option.")
    assert [choice["value"] for choice in payload["quick_replies"]] == ["IRIS", "TULIP"]


def _location(issue, monkeypatch):
    import api_context
    monkeypatch.setattr(api_context, "get_company_projects", lambda: PROJECTS)
    return api_context.build_grounded_project_location_assist(api_context.SupportAssistRequest(issue=issue))


@pytest.mark.parametrize("issue", ["What is there in Wakanda?", "What is available in Wakanda?",
                                   "Are there projects in Wakanda?", "What do you have in Wakanda?"])
def test_area_without_live_projects_is_one_line_plus_choices(issue, monkeypatch):
    response = _location(issue, monkeypatch)
    first = response["answer"].splitlines()[0]
    assert first == ("I couldn't find a project in that area. Our projects are in Thane, Hyderabad and Pune. "
                     "Which one would you like to explore?")
    assert "Wakanda" not in response["answer"]
    assert [choice["value"] for choice in response["quick_replies"]] == [p["projectName"] for p in PROJECTS]
    assert response["pending_project_lookup"]["purpose"] == "explore_project"


def test_area_question_about_a_named_project_is_not_an_area(monkeypatch):
    assert _location("What is there in Green Acres?", monkeypatch) is None


def test_area_with_live_projects_lists_them(monkeypatch):
    response = _location("What is available in Kompally?", monkeypatch)
    assert "2 projects in Kompally" in response["answer"]
    assert "Sunrise Towers" not in response["answer"]


def test_browse_projects_endpoint_matches_chat_catalogue(monkeypatch):
    import api_context
    from routers import properties
    rows = PROJECTS + [{"id": 55, "projectName": "GBK Group", "address": "sales@example.com"}]
    monkeypatch.setattr(properties, "get_company_projects", lambda: rows)
    monkeypatch.setattr(clarification, "get_company_projects", lambda: rows)
    browsed = TestClient(api).get("/api/property-flow/projects").json()["items"]
    chat = clarification.build_project_browse_response("What projects do you have?")["quick_replies"]
    assert [project["projectName"] for project in browsed] == [choice["value"] for choice in chat]
    assert "GBK Group" not in [choice["value"] for choice in chat]
    assert api_context  # imported for the shared filter


def test_reask_drops_options_no_longer_live(monkeypatch):
    _live_wings(monkeypatch, wings=("TULIP",))
    payload = clarification.build_unmatched_selection_answer(WING_STATE)
    assert [choice["value"] for choice in payload["quick_replies"]] == ["TULIP"]
    _live_wings(monkeypatch, wings=())
    assert clarification.build_unmatched_selection_answer(WING_STATE) is None


@pytest.mark.parametrize("issue", ["What's in Wakanda?", "What is in Wakanda?", "What all is there in Wakanda?",
                                   "Anything available in Wakanda?"])
def test_area_question_renderings(issue, monkeypatch):
    assert _location(issue, monkeypatch)["pending_project_lookup"]["purpose"] == "explore_project"


@pytest.mark.parametrize("issue", ["What is the interest rate in SBI?", "What is the weather in Pune like today"])
def test_non_area_questions_are_not_area_answers(issue, monkeypatch):
    response = _location(issue, monkeypatch)
    assert response is None or "couldn't find a project" not in response["answer"]


def test_locality_narrowing_matches_address_like_location_answer(monkeypatch):
    rows = PROJECTS + [{"id": 4, "projectName": "Lake View", "city": "Thane", "locality": "",
                        "address": "Near station, Kompally East"}]
    monkeypatch.setattr(clarification, "get_company_projects", lambda: rows)
    state = clarification.build_project_browse_response("What projects do you have?")["pending_project_lookup"]
    narrowed = clarification.narrow_project_choice_by_locality(state, "What is there in Kompally?")
    assert [choice["value"] for choice in narrowed["quick_replies"]] == [
        "Vishwajeet Heights", "Green Acres", "Lake View"]


def test_full_catalogue_choice_does_not_claim_a_match():
    names = ["Vishwajeet Heights", "Vishwajeet Prime"]
    site_visit = clarification.build_project_choice_answer(names, "", "How do I book a site visit?")
    pricing = clarification.build_project_choice_answer(names, "pricing", "price?")
    assert site_visit.splitlines()[0] == "Which project should I check?"
    assert pricing.splitlines()[0] == "Which project should I check for the pricing?"
