from copy import deepcopy
from unittest.mock import patch

import pytest

import api_context
from routers import assist
from services import property_clarification_service as service
from services.conversation_store_service import (
    build_pending_project_lookup_marker, get_pending_project_lookup,
)

PROJECTS = [
    {"id": 1, "projectName": "Vishwajeet Myspace", "address": "Ambernath"},
    {"id": 2, "projectName": "Vishwajeet Precious", "address": "Thane"},
    {"id": 3, "projectName": "Vishwajeet Precious Phase-V", "address": "Thane"},
]
WINGS = [{"id": 10, "name": "Venus A"}, {"id": 11, "name": "Jupiter C"}]
UNITS = [
    {"unitNumber": "101", "floorNumber": 1, "typologyName": "1BHK", "typologyId": 100},
    {"unitNumber": "102", "floorNumber": 1, "typologyName": "2BHK", "typologyId": 100},
    {"unitNumber": "201", "floorNumber": 2, "typologyName": "2BHK", "typologyId": 100},
]


@pytest.fixture(autouse=True)
def live_records():
    with patch.object(service, "get_company_projects", return_value=PROJECTS), \
            patch.object(service, "get_project_wings", return_value=WINGS), \
            patch.object(service, "get_wing_inventory", return_value=UNITS), \
            patch.object(service, "get_wing_typologies", return_value=[{"id": 100, "minBasePrice": 3400, "maxBasePrice": 4300, "rateType": "Rate Per Sq.Ft."}]), \
            patch.object(api_context, "get_company_projects", return_value=PROJECTS):
        yield


# Every selection-producing legacy string found in source or bytecode is covered.
@pytest.mark.parametrize("prompt,entity", [
    ("Which project would you like me to check?", "project"),
    ("Please share the project or property name and the purpose of your visit.", "project"),
    ("Please share the project name, tower or block, and unit number.", "project"),
    ("Please share the project or property name and what you want to know.", "project"),
    ("Please share the project or property name, your preferred date and time.", "project"),
    ("Which project would you like a detailed price estimate for?", "project"),
    ("Tell me which project you want to explore, and I can check its wings.", "project"),
    ("Choose a wing to continue.", "wing"),
    ("Which wing would you like to explore?", "wing"),
    ("Choose a floor to continue:", "floor"),
    ("Which floor would you like to explore?", "floor"),
    ("Please choose another available home type or floor.", "home_type"),
    ("Which flat did you mean?", "flat"),
    ("Please share the project name, booking or unit reference, and the specific document you need.", "project"),
    ("Please share your preferred project, date, and contact number.", "project"),
    ("Please share your project or unit reference, transaction reference, amount paid.", "project"),
])
def test_all_clarification_locations_list_real_options_and_keep_intent(prompt, entity):
    issue = "Check construction progress and possession date in Vishwajeet Myspace, Venus A wing"
    if entity == "project":
        issue = "Check construction progress and possession date"
    result = service.apply_clarification_contract({"answer": prompt, "route": "property"}, issue)
    state = result["pending_project_lookup"]
    assert state["entity"] == entity
    expected = {"project": [p["projectName"] for p in PROJECTS],
                "wing": [w["name"] for w in WINGS], "floor": ["1", "2"],
                "flat": ["101", "102", "201"], "home_type": ["1BHK", "2BHK"]}[entity]
    assert state["options"] == expected
    assert all("- " + name in result["answer"] for name in expected)
    restored = get_pending_project_lookup(build_pending_project_lookup_marker(state))
    query = service.resume_selection(restored, expected[0])
    assert issue in query
    assert expected[0] in query
    # Repeated transient failures must never discard the selection or intent.
    for _ in range(3):
        marker = assist._project_lookup_marker({"source_status": "failed"}, restored, "retry")
        restored = get_pending_project_lookup(marker)
        assert service.resume_selection(restored, "retry") == query


@pytest.mark.parametrize("builder,question,kind", [
    (api_context.build_grounded_project_amenities_assist, "What amenities are available?", "amenities"),
    (api_context.build_grounded_project_cost_clarification_assist, "What is the cost?", "pricing"),
    (api_context.build_grounded_project_location_assist, "Where is the project located?", "location"),
])
def test_missing_project_in_all_three_shortcuts(builder, question, kind):
    index = {p["id"]: {"project": p, "amenities": ["Gym"] if p["id"] == 2 else []} for p in PROJECTS}
    with patch.object(api_context, "live_amenity_index", return_value=index):
        result = builder(api_context.SupportAssistRequest(issue=question))
    if kind == "amenities":
        assert result["pending_project_lookup"]["options"] == ["Vishwajeet Precious"]
        assert result["pending_project_lookup"]["original_issue"] == question
        assert "Myspace" not in result["answer"]
        return
    assert result["pending_project_lookup"] == kind
    assert all(p["projectName"] in result["answer"] for p in PROJECTS)


def test_precious_fragment_is_ambiguous_but_full_base_name_selects():
    state = service.apply_clarification_contract({"clarification_entity": "project"}, "What amenities in Vishwajeet?")["pending_project_lookup"]
    assert service.resume_selection(dict(state), "precious") == state["original_issue"]
    query = service.resume_selection(state, "Vishwajeet Precious")
    assert "project: Vishwajeet Precious" in query
    assert "Phase-V" not in query


@pytest.mark.parametrize("reply", ["A", "Venus A", "wing Venus A", "lets go with A"])
def test_wing_selection_variants(reply):
    state = service.apply_clarification_contract({"clarification_entity": "wing"}, "Show availability in Vishwajeet Myspace")["pending_project_lookup"]
    assert "wing: Venus A" in service.resume_selection(state, reply)


def test_floor_limits_flat_and_home_type_choices():
    for entity, expected in [("flat", ["101", "102"]), ("home_type", ["1BHK", "2BHK"])]:
        result = service.apply_clarification_contract({"clarification_entity": entity}, "Show availability in Vishwajeet Myspace, Venus A wing, floor 1")
        assert result["pending_project_lookup"]["options"] == expected


def test_ambiguous_and_invalid_wing_do_not_guess():
    state = {"kind": "selection", "entity": "wing", "original_issue": "Show available flats",
             "scope": {"project": "Vishwajeet Myspace"}, "options": ["Venus A", "Jupiter A"]}
    for reply in ["A", "Imaginary Wing"]:
        assert service.resume_selection(deepcopy(state), reply) == "Show available flats"


def test_options_api_failure_keeps_original_request_for_retry():
    with patch.object(service, "get_company_projects", side_effect=TimeoutError("offline")):
        result = service.apply_clarification_contract({"clarification_entity": "project"}, "Which amenities in Vishwajeet?")
    assert result["source_status"] == "failed"
    assert service.resume_selection(result["pending_project_lookup"], "retry") == "Which amenities in Vishwajeet?"


def test_new_question_cancels_old_pending_intent():
    for reply in ["What is the weather?", "Where is Precious located?", "Arrange a callback", "cancel"]:
        assert not service.continues_selection({}, reply)
    assert service.continues_selection({}, "precious")
    assert service.continues_selection({}, "retry")


def test_factual_text_and_non_property_routes_are_unchanged():
    for payload in [{"answer": "Vishwajeet Myspace has four wings."},
                    {"answer": "Which project?", "route": "general"},
                    {"answer": "Which project?", "route": "call_booking"},
                    {"answer": "Which project?", "route": "human_contact"}]:
        assert service.apply_clarification_contract(payload, "hello") == payload


def test_future_explicit_metadata_does_not_depend_on_prompt_wording():
    result = service.apply_clarification_contract({"clarification_entity": "project", "answer": "arbitrary wording"}, "Show amenities")
    assert result["pending_project_lookup"]["options"] == [p["projectName"] for p in PROJECTS]


def test_empty_catalogue_does_not_ask_for_an_unlisted_name():
    with patch.object(service, "get_company_projects", return_value=[]):
        result = service.apply_clarification_contract({"clarification_entity": "project"}, "Show amenities")
    assert "no matching project options" in result["answer"]
    assert "Which" not in result["answer"]


def test_selected_project_pricing_reads_live_typologies():
    with patch("services.acrobuild_company_service.get_project_typologies", return_value=[
        {"typologyName": "2BHK", "minBasePrice": 3400, "maxBasePrice": 4300, "rateType": "Rate Per Sq.Ft."}
    ]) as fetch:
        result = api_context.build_grounded_project_cost_clarification_assist(api_context.SupportAssistRequest(issue="What is the cost? Selected project: Vishwajeet Precious"))
    fetch.assert_called_once_with(2)
    assert "3400" in result["answer"] and "4300" in result["answer"]
    assert "pending_project_lookup" not in result


def test_site_visit_documents_disambiguates_project_before_guidance():
    result = api_context.build_grounded_site_visit_document_assist(
        api_context.SupportAssistRequest(issue="What documents do I need for a site visit in Vishwajeet?"))
    assert all(p["projectName"] in result["answer"] for p in PROJECTS)
    assert result["clarification_entity"] == "project"


def test_floor_resume_uses_syntax_understood_by_inventory_parser():
    state = service.apply_clarification_contract({"clarification_entity": "floor"},
        "Show available homes in Vishwajeet Myspace, Venus A wing")["pending_project_lookup"]
    query = service.resume_selection(state, "floor 1")
    assert "floor 1" in query
    assert "floor: 1" not in query


def test_selection_metadata_survives_long_stored_answers(tmp_path):
    import sqlite3
    from services import conversation_store_service as store
    database = str(tmp_path / "conversation.db")
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE conversation_turns (session_hash TEXT, conversation_id TEXT, position INTEGER, sender TEXT, text TEXT, expires_at REAL)")
    state = {"kind": "selection", "original_issue": "What amenities?", "entity": "project",
             "options": ["Project " + str(i) for i in range(1000)], "scope": {}}
    marker = build_pending_project_lookup_marker(state)
    session = store.ConversationSession("", "long-answer")
    with patch.object(store, "open_database_connection", side_effect=lambda: sqlite3.connect(database)):
        session.append("amenities?", "x" * 15000, marker)
        saved = session.load()
    assert get_pending_project_lookup(saved[-1]["text"]) == state


def test_relevance_validation_does_not_erase_a_selection_request():
    from graph.main_orchestrator import _finalize_property_response
    from services.turn_analysis_service import TurnAnalysis
    result = _finalize_property_response(
        {"answer": "Choose a wing to continue.", "route": "property"},
        "What is the cost of a flat in Vishwajeet Myspace?", [],
        TurnAnalysis(intent="property", reply_language="English", script="latin", source="test"))
    assert result["pending_project_lookup"]["entity"] == "wing"
    assert "Venus A" in result["answer"]
    assert "could not verify" not in result["answer"]


def test_inventory_selection_chain_reads_records_at_each_stage():
    state = service.apply_clarification_contract({"clarification_entity": "wing"},
        "Show me wings in Vishwajeet Myspace")["pending_project_lookup"]
    query = service.resume_selection(state, "Venus A")
    result = service.build_inventory_selection_answer(query, state)
    assert result["pending_project_lookup"]["options"] == ["1", "2"]
    state = result["pending_project_lookup"]
    query = service.resume_selection(state, "1")
    result = service.build_inventory_selection_answer(query, state)
    assert result["pending_project_lookup"]["options"] == ["101", "102"]
    state = result["pending_project_lookup"]
    query = service.resume_selection(state, "101")
    result = service.build_inventory_selection_answer(query, state)
    assert "Flat 101" in result["answer"]
    assert "Flat 102" not in result["answer"]
    assert "3400" in result["answer"]
    assert "pending_project_lookup" not in result


def test_cost_intent_survives_wing_and_floor_selection():
    original = "What is the cost of a flat in Vishwajeet Myspace?"
    state = service.apply_clarification_contract({"clarification_entity": "wing"}, original)["pending_project_lookup"]
    query = service.resume_selection(state, "Venus A")
    result = service.build_inventory_selection_answer(query, state)
    state = result["pending_project_lookup"]
    assert original in state["original_issue"]
    query = service.resume_selection(state, "1")
    result = service.build_inventory_selection_answer(query, state)
    assert "base rate: INR 3400" in result["answer"]
    assert "Flat 101" in result["answer"] and "Flat 102" in result["answer"]
    assert "Flat 201" not in result["answer"]


def test_home_type_selection_filters_flat_options():
    result = service.apply_clarification_contract({"clarification_entity": "home_type"},
        "Show available homes in Vishwajeet Myspace, Venus A wing, floor 1")
    state = result["pending_project_lookup"]
    query = service.resume_selection(state, "1BHK")
    result = service.build_inventory_selection_answer(query, state)
    assert result["pending_project_lookup"]["options"] == ["101"]


def test_selector_supplied_after_initial_outage_is_not_discarded():
    state = {"kind": "selection", "original_issue": "What amenities in Vishwajeet?",
             "entity": "project", "scope": {}, "options": []}
    query = service.resume_selection(state, "precious")
    assert "amenities" in query and "precious" in query
    assert service.resume_selection(state, "retry") == query


def test_partial_name_lists_only_matching_projects():
    result = service.apply_clarification_contract({"clarification_entity": "project"}, "What amenities in preci?")
    assert result["pending_project_lookup"]["options"] == ["Vishwajeet Precious", "Vishwajeet Precious Phase-V"]


def test_two_explicit_project_names_are_not_silently_collapsed():
    result = service.apply_clarification_contract({"clarification_entity": "project"},
        "What amenities in Vishwajeet Myspace or Vishwajeet Precious?")
    assert set(result["pending_project_lookup"]["options"]) == {"Vishwajeet Myspace", "Vishwajeet Precious"}


def test_selection_overrides_original_multiple_project_names():
    from services.acrobuild_company_service import resolve_project_from_text
    state = service.apply_clarification_contract({"clarification_entity": "project"},
        "What amenities in Vishwajeet Myspace or Vishwajeet Precious?")["pending_project_lookup"]
    query = service.resume_selection(state, "precious")
    assert resolve_project_from_text(PROJECTS, query)["id"] == 2


def test_construction_intent_after_wing_selection_does_not_become_floor_browsing():
    with patch.object(service, "get_project_wings", return_value=[{"id": 10, "name": "Venus A", "constructionStatus": "In progress"}]):
        state = service.apply_clarification_contract({"clarification_entity": "wing"},
            "What is the construction status in Vishwajeet Myspace?")["pending_project_lookup"]
        query = service.resume_selection(state, "Venus A")
        result = service.build_inventory_selection_answer(query, state)
    assert "Construction status: In progress" in result["answer"]
    assert "Which floor" not in result["answer"]
