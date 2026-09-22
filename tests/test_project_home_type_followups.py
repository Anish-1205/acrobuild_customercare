import json

import pytest
from fastapi.testclient import TestClient

from app import api
from graph import haystack_conversation_pipeline as pipeline
from graph import main_orchestrator as orchestrator
from routers import assist
from services import project_home_type_service as home
from services import property_clarification_service as clarification
from services.acrobuild_company_service import resolve_project_candidates_from_text
from services.turn_analysis_service import TurnAnalysis
from services.conversation_store_service import (
    build_current_project_marker, get_current_project_context, get_pending_project_lookup,
)


PROJECTS = [{"id": 1, "projectName": "Vishwajeet Empire"},
            {"id": 2, "projectName": "Vishwajeet Empire NX"}]


@pytest.fixture
def catalogue(monkeypatch):
    monkeypatch.setattr(pipeline, "get_live_project_names", lambda: [p["projectName"] for p in PROJECTS])
    monkeypatch.setattr(home, "get_company_projects", lambda: PROJECTS)
    monkeypatch.setattr(clarification, "get_company_projects", lambda: PROJECTS)
    monkeypatch.setattr(home, "get_project_typologies", lambda project_id: [
        {"id": 20, "typologyName": "2BHK", "carpetArea": 620, "minBasePrice": 5000, "rateType": "PerSqft"},
        *([{"id": 30, "typologyName": "3BHK", "carpetArea": 900}] if project_id == 1 else []),
    ])
    monkeypatch.setattr(home, "get_project_wings", lambda _id: [{"id": 30}])
    monkeypatch.setattr(home, "get_wing_inventory", lambda _id: [{"typologyId": 20, "typologyName": "2BHK"}])


def test_full_suffix_and_ambiguous_fragment():
    assert resolve_project_candidates_from_text(PROJECTS, "Empire") == PROJECTS
    assert resolve_project_candidates_from_text(PROJECTS, "Vishwajeet Empire NX") == [PROJECTS[1]]
    assert resolve_project_candidates_from_text(PROJECTS, "Vishwajeet Empire") == [PROJECTS[0]]


@pytest.mark.parametrize("question", ["2bhk matrame cheppu", "indhulo 2bk and 3bhk details cheppu", "3bhk levva?"])
def test_followups_keep_nx_and_every_type(catalogue, question):
    history = [{"sender": "customer", "text": "Tell me about Vishwajeet Empire NX"},
               {"sender": "bot", "text": "Home types in Vishwajeet Empire NX: 2BHK"}]
    resolved = pipeline.resolve_contextual_support_issue(question, history)
    assert "Requested project: Vishwajeet Empire NX" in resolved
    assert home.requested_home_types(resolved) == home.requested_home_types(question)


def test_compound_and_absent_types(catalogue):
    result = home.build_project_home_type_answer("2bk and 3bhk details in Vishwajeet Empire NX")
    assert "2BHK: 1 unit(s)" in result["answer"]
    assert "3BHK: Not listed" in result["answer"]
    assert "Vishwajeet Empire NX" in result["answer"]
    assert not pipeline.validate_support_answer("2BHK and 3BHK in Vishwajeet Empire NX", result["answer"])


def test_listed_type_without_available_units(catalogue, monkeypatch):
    monkeypatch.setattr(home, "get_wing_inventory", lambda _id: [])
    result = home.build_project_home_type_answer("2BHK in Vishwajeet Empire NX")
    assert "configuration is listed, but no units" in result["answer"]


def test_catalogue_home_type_filter_lists_only_matching_projects(catalogue):
    for question in ("what properties have 3bhk?", "which project has 3 BHK?"):
        result = home.build_catalogue_home_type_answer(question)
        assert result["pending_project_lookup"]["options"] == ["Vishwajeet Empire"]
        assert "Vishwajeet Empire NX" not in result["answer"]
    state = result["pending_project_lookup"]
    assert clarification.resume_selection(state, "Vishwajeet Empire") == (
        "Show 3BHK details in project Vishwajeet Empire"
    )


def test_catalogue_home_type_filter_has_honest_no_match(catalogue):
    result = home.build_catalogue_home_type_answer("which projects have 4bhk?")
    assert "None of the projects" in result["answer"]
    assert not result.get("pending_project_lookup")
    assert not result.get("quick_replies")


def test_validator_checks_all_types_and_suffix(catalogue):
    failures = pipeline.validate_support_answer("2BHK and 3BHK in Vishwajeet Empire NX", "2BHK in Vishwajeet Empire")
    assert "3 BHK" in failures and "requested project" in failures
    assert "requested project" in pipeline.validate_support_answer(
        "2BHK in Vishwajeet Empire", "2BHK in Vishwajeet Empire NX")


def test_explicit_new_project_and_portfolio_search(catalogue):
    history = [{"sender": "customer", "text": "Vishwajeet Empire NX"}]
    for issue in ["3BHK in Vishwajeet Empire", "Which projects have 3BHK?"]:
        assert pipeline.resolve_contextual_support_issue(issue, history) == issue


def test_durable_current_project_survives_answers_that_omit_its_name(catalogue):
    marker = build_current_project_marker("Vishwajeet Empire NX")
    assert get_current_project_context("Short answer" + marker) == {"project": "Vishwajeet Empire NX"}
    history = [
        {"sender": "bot", "text": "Overview" + marker},
        {"sender": "customer", "text": "is there a 3bhk in this project?"},
        {"sender": "bot", "text": "I could not find a 3 BHK option in the latest project data."},
    ]
    assert pipeline.resolve_contextual_support_issue("2bhk?", history).endswith(
        "Requested project: Vishwajeet Empire NX"
    )


def test_catalogue_marker_explicitly_clears_older_project(catalogue):
    history = [
        {"sender": "bot", "text": "Overview" + build_current_project_marker("Vishwajeet Empire NX")},
        {"sender": "bot", "text": "Choose a matching project" + build_current_project_marker("")},
    ]
    assert pipeline._conversation_project_name(history) == ""


@pytest.mark.parametrize("endpoint", ["/api/support/assist", "/api/support/assist/stream"])
def test_endpoint_followups_and_handoff(endpoint, catalogue, monkeypatch):
    monkeypatch.setattr(orchestrator, "analyze_turn", lambda *_a: TurnAnalysis("property", "English", "latin", "test"))
    monkeypatch.setattr(assist, "_enforce_live_property_data", lambda payload, *_a: payload)
    monkeypatch.setattr(assist, "evaluate_rag_response", lambda *_a: {})
    history = [{"sender": "customer", "text": "Tell me about Vishwajeet Empire NX"},
               {"sender": "bot", "text": "Vishwajeet Empire NX overview"}]

    class Session:
        def __init__(self, *_a): pass
        def set_cookie(self, *_a): pass
        def load(self): return history
        def append(self, question, answer, marker="", **_kw):
            history.extend([{"sender": "customer", "text": question}, {"sender": "bot", "text": answer + marker}])

    monkeypatch.setattr(assist, "ConversationSession", Session)
    with TestClient(api) as client:
        for question in ["2bhk matrame cheppu", "indhulo 2bk and 3bhk details cheppu", "3bhk levva?"]:
            response = client.post(endpoint, json={"issue": question})
            assert response.status_code == 200
            payload = response.json() if not endpoint.endswith("stream") else next(
                e["response"] for e in map(json.loads, response.text.splitlines()) if e["type"] == "done")
            assert "Vishwajeet Empire NX" in payload["answer"]
            assert not payload.get("pending_project_lookup")
            assert {o["action"] for o in payload["quick_replies"]} == {"ticket", "site_visit", "browse_projects"}
            assert next(o for o in payload["quick_replies"] if o["action"] == "site_visit")["project_name"] == "Vishwajeet Empire NX"
            for number in home.requested_home_types(question):
                assert f"{number}BHK:" in payload["answer"]


@pytest.mark.parametrize("endpoint", ["/api/support/assist", "/api/support/assist/stream"])
def test_real_selection_sequence_and_bare_followup(endpoint, catalogue, monkeypatch):
    history = []
    monkeypatch.setattr(orchestrator, "analyze_turn", lambda *_a: TurnAnalysis("property", "English", "latin", "test"))
    monkeypatch.setattr(assist, "_enforce_live_property_data", lambda payload, *_a: payload)
    monkeypatch.setattr(assist, "evaluate_rag_response", lambda *_a: {})

    overview = {
        "answer": "Full overview for Vishwajeet Empire NX", "route": "property",
        "source_status": "live_api", "agent_mode": "knowledge_retrieval", "used_llm": False,
        "matched_chunks": [{"record_kind": "company_api", "project": PROJECTS[1], "body_text": "overview"}],
    }
    monkeypatch.setattr(assist, "run_support_orchestration", lambda **_kw: dict(overview))
    monkeypatch.setattr(assist, "stream_support_orchestration_events",
                        lambda **_kw: iter([{"type": "done", "response": dict(overview)}]))

    class Session:
        def __init__(self, *_a): pass
        def set_cookie(self, *_a): pass
        def load(self): return list(history)
        def append(self, question, answer, marker=""):
            # Reproduce the clean response that omitted the project name while
            # retaining server-only state.
            visible = ("I could not find a 3 BHK option in the latest project data."
                       if question == "is there a 3bhk in this project?" else answer)
            history.extend([{"sender": "customer", "text": question},
                            {"sender": "bot", "text": visible + marker}])

    monkeypatch.setattr(assist, "ConversationSession", Session)

    def ask(client, question):
        response = client.post(endpoint, json={"issue": question, "conversation_id": "selection-sequence"})
        assert response.status_code == 200
        return response.json() if not endpoint.endswith("stream") else next(
            event["response"] for event in map(json.loads, response.text.splitlines()) if event["type"] == "done")

    with TestClient(api) as client:
        choices = ask(client, "what projects do you have?")
        selected_name = next(choice["value"] for choice in choices["quick_replies"]
                             if choice["value"] == "Vishwajeet Empire NX")
        selected = ask(client, selected_name)
        assert not selected.get("pending_project_lookup")
        assert get_current_project_context(history[-1]["text"]) == {"project": selected_name}
        ask(client, "is there a 3bhk in this project?")
        assert "Vishwajeet Empire NX" not in history[-1]["text"].split("\u2063", 1)[0]
        bare = ask(client, "2bhk?")
        assert "Home types in Vishwajeet Empire NX" in bare["answer"]
        assert not bare.get("pending_project_lookup")


@pytest.mark.parametrize("endpoint", ["/api/support/assist", "/api/support/assist/stream"])
def test_catalogue_filter_then_selection_over_http(endpoint, catalogue, monkeypatch):
    history = []
    monkeypatch.setattr(orchestrator, "analyze_turn", lambda *_a: TurnAnalysis("property", "English", "latin", "test"))
    monkeypatch.setattr(assist, "_enforce_live_property_data", lambda payload, *_a: payload)
    monkeypatch.setattr(assist, "evaluate_rag_response", lambda *_a: {})

    class Session:
        def __init__(self, *_a): pass
        def set_cookie(self, *_a): pass
        def load(self): return list(history)
        def append(self, question, answer, marker=""):
            history.extend([{"sender": "customer", "text": question},
                            {"sender": "bot", "text": answer + marker}])

    monkeypatch.setattr(assist, "ConversationSession", Session)
    with TestClient(api) as client:
        def ask(question):
            response = client.post(endpoint, json={"issue": question, "conversation_id": "type-filter"})
            payload = response.json() if not endpoint.endswith("stream") else next(
                event["response"] for event in map(json.loads, response.text.splitlines()) if event["type"] == "done")
            return payload

        filtered = ask("what properties have 3bhk?")
        assert [choice["value"] for choice in filtered["quick_replies"]] == ["Vishwajeet Empire"]
        assert get_current_project_context(history[-1]["text"]) == {"project": ""}
        selected = ask("Vishwajeet Empire")
        assert "3BHK:" in selected["answer"]
        assert "could not verify one live answer" not in selected["answer"].lower()
        assert not selected.get("pending_project_lookup")


def test_detail_dispatch_does_not_erase_home_types(monkeypatch):
    from services import ai_agent_service as agent
    chunk = {"source_key": "acrobuild-cs-project-2", "project_name": "Vishwajeet Empire NX"}
    received = []
    monkeypatch.setattr(agent, "_legacy_build_company_api_direct_answer",
                        lambda issue, *_a, **_kw: received.append(issue) or "answer")
    issue = "2BHK and 3BHK details in Vishwajeet Empire NX"
    agent.build_company_api_direct_answer(issue, [chunk])
    assert received == [issue]


def test_compound_scope_survives_repeated_inventory_failures(catalogue, monkeypatch):
    from services import property_clarification_service as clarification
    original = "Show 2BHK and 3BHK details"
    state = {"kind": "selection", "entity": "project", "original_issue": original,
             "options": [p["projectName"] for p in PROJECTS], "scope": {}}
    effective = clarification.resume_selection(state, "Vishwajeet Empire NX")

    def unavailable(_id):
        raise RuntimeError("temporarily unavailable")

    monkeypatch.setattr(home, "get_wing_inventory", unavailable)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            home.build_project_home_type_answer(effective)
        state = get_pending_project_lookup(assist._project_lookup_marker(
            {"source_status": "failed"}, state, original, shortcut_failed=True))
        assert state["original_issue"] == original
        assert state["scope"]["project"] == "Vishwajeet Empire NX"
        assert clarification.resume_selection(state, "retry") == effective
    monkeypatch.setattr(home, "get_wing_inventory", lambda _id: [])
    answer = home.build_project_home_type_answer(effective)["answer"]
    assert "2BHK:" in answer and "3BHK:" in answer


# -----------------------------------
# NUMBERLESS "WHAT BHKS ARE AVAILABLE" FOLLOW-UPS
# -----------------------------------
# A BHK question with no specific number ("what bhks are available") named no
# type, so requested_home_types() found nothing and the query fell through
# every numbered builder straight to the general pipeline -- which could
# re-ask "which project?" (offering only the one project already in scope)
# instead of the missing wing.


@pytest.mark.parametrize("issue,expected", [
    ("what bhks are available in this project ?", True),
    ("which home types are available?", True),
    ("what configurations does it have?", True),
    ("what bhk options are there?", True),
    ("what is the price of 2bhk?", False),  # numbered -- existing builders own this
    ("which projects have bhk options available?", False),  # catalogue-wide, not one project
    ("hello", False),
])
def test_generic_home_type_query_detection(issue, expected):
    assert home.is_generic_home_type_query(issue) is expected


def test_generic_home_type_query_asks_for_wing_not_project(catalogue, monkeypatch):
    # Multiple named wings and no wing named in the question or history --
    # the missing piece is the wing, not the (already unambiguous) project.
    # apply_clarification_contract()/live_options() resolve wings through
    # services/property_clarification_service.py's own imported binding, a
    # separate name from project_home_type_service's.
    monkeypatch.setattr(clarification, "get_project_wings", lambda _id: [
        {"id": 30, "name": "Venus A"}, {"id": 31, "name": "Jupiter C"},
    ])
    history = [{"sender": "customer", "text": "Vishwajeet Empire NX"},
               {"sender": "bot", "text": "Choose a wing in Vishwajeet Empire NX."}]
    result = home.build_generic_home_type_answer(
        "what bhks are available in this project ?", history)
    assert result["clarification_entity"] == "wing"
    assert result["answer"].splitlines()[0] == "Which wing should I check in Vishwajeet Empire NX?"
    assert [choice["value"] for choice in result["quick_replies"]] == ["Venus A", "Jupiter C"]


def test_generic_home_type_query_resolves_directly_with_one_wing(catalogue, monkeypatch):
    # A single wing is auto-selected, so the question resolves straight to
    # the live home types instead of asking to choose a wing.
    monkeypatch.setattr(clarification, "get_project_wings", lambda _id: [{"id": 30, "name": "Only Wing"}])
    monkeypatch.setattr(clarification, "get_wing_inventory", lambda _id: [
        {"unitNumber": "101", "floorNumber": 1, "typologyName": "1BHK"},
        {"unitNumber": "102", "floorNumber": 1, "typologyName": "2BHK"},
    ])
    history = [{"sender": "customer", "text": "Vishwajeet Empire NX"}]
    result = home.build_generic_home_type_answer(
        "what bhks are available in this project ?", history)
    assert result["clarification_entity"] == "home_type"
    assert "2BHK" in result["answer"]


@pytest.mark.parametrize("endpoint", ["/api/support/assist", "/api/support/assist/stream"])
def test_generic_bhk_followup_over_http_asks_for_wing(endpoint, catalogue, monkeypatch):
    monkeypatch.setattr(orchestrator, "analyze_turn", lambda *_a: TurnAnalysis("property", "English", "latin", "test"))
    monkeypatch.setattr(assist, "_enforce_live_property_data", lambda payload, *_a: payload)
    monkeypatch.setattr(assist, "evaluate_rag_response", lambda *_a: {})
    monkeypatch.setattr(assist, "get_current_data_api_logs", lambda: [])
    monkeypatch.setattr(clarification, "get_project_wings", lambda _id: [
        {"id": 30, "name": "Venus A"}, {"id": 31, "name": "Jupiter C"},
    ])
    # The general pipeline must never be reached: this question is fully
    # resolved by the grounded shortcut chain.
    monkeypatch.setattr(assist, "run_support_orchestration",
                        lambda **_kw: (_ for _ in ()).throw(AssertionError("fell through to general pipeline")))
    monkeypatch.setattr(assist, "stream_support_orchestration_events",
                        lambda **_kw: (_ for _ in ()).throw(AssertionError("fell through to general pipeline")))

    marker = build_current_project_marker("Vishwajeet Empire NX")
    history = [{"sender": "customer", "text": "Vishwajeet Empire NX"},
               {"sender": "bot", "text": "Choose a wing in Vishwajeet Empire NX." + marker}]

    class Session:
        def __init__(self, *_a): pass
        def set_cookie(self, *_a): pass
        def load(self): return list(history)
        def append(self, *_a, **_kw): pass

    monkeypatch.setattr(assist, "ConversationSession", Session)
    with TestClient(api) as client:
        response = client.post(endpoint, json={
            "issue": "what bhks are available in this project ?",
            "conversation_id": "generic-bhk-followup", "conversation_messages": history,
        })
        assert response.status_code == 200
        payload = response.json() if not endpoint.endswith("stream") else next(
            event["response"] for event in map(json.loads, response.text.splitlines()) if event["type"] == "done")

    assert payload["clarification_entity"] == "wing"
    assert payload["answer"].splitlines()[0] == "Which wing should I check in Vishwajeet Empire NX?"
    assert [choice["value"] for choice in payload["quick_replies"]] == ["Venus A", "Jupiter C"]
