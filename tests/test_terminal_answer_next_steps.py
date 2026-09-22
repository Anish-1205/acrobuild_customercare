"""_complete_payload() (routers/assist.py) offers "Browse all projects /
Book a site visit / Raise a support ticket" after any terminal property
answer -- one gate shared by every answer type, not a per-answer-type
feature. These tests exercise that gate directly against the real evidence
shapes each answer builder produces, so a shape only one builder uses (e.g.
amenities' nested "project" dict) cannot silently exclude every other
builder from next-step options.
"""
from unittest.mock import patch

from routers import assist
from graph.main_orchestrator import TurnContext
from services.turn_analysis_service import TurnAnalysis

ACTIONS = {"ticket", "site_visit", "browse_projects"}


def _run(matched_chunks, source_status="live_api", extra=None, is_property=True):
    payload = {"route": "property", "source_status": source_status,
               "matched_chunks": matched_chunks, **(extra or {})}
    turn = TurnContext([], "x", TurnAnalysis(
        "property" if is_property else "general", "English", "latin", "test",
        unsure=False), "x")
    with patch.object(assist, "get_current_data_api_logs", return_value=[]), \
            patch.object(assist, "apply_clarification_contract", side_effect=lambda p, *a: p), \
            patch.object(assist, "_enforce_live_property_data", side_effect=lambda p, *a: p):
        return assist._complete_payload(payload, "x", turn)


def _site_visit_project(result):
    return next(q["project_name"] for q in result["quick_replies"] if q["action"] == "site_visit")


def test_amenities_shape_offers_next_steps():
    # services/property_clarification_service.py and api_context.py's amenities
    # builder evidence a resolved project as a nested {"project": {...}} dict.
    result = _run([{"project": {"projectName": "Vishwajeet Heights"}}])
    assert {q["action"] for q in result["quick_replies"]} == ACTIONS
    assert _site_visit_project(result) == "Vishwajeet Heights"


def test_pricing_shape_offers_next_steps():
    # api_context.py's build_grounded_project_cost_clarification_assist
    # evidences a resolved single project as a one-entry "projects" list.
    result = _run([{"projects": [{"projectName": "Vishwajeet Empire"}]}])
    assert {q["action"] for q in result["quick_replies"]} == ACTIONS
    assert _site_visit_project(result) == "Vishwajeet Empire"


def test_location_multi_project_shape_offers_next_steps_without_forcing_a_project():
    # build_grounded_project_location_assist's "we have N projects in <area>"
    # answer lists every matching project -- a real informational answer, not
    # a clarification, so it still gets the menu, but must not guess which of
    # several projects the "Book a site visit" button should pre-fill.
    result = _run([{"projects": [{"projectName": "A"}, {"projectName": "B"}]}])
    assert {q["action"] for q in result["quick_replies"]} == ACTIONS
    assert _site_visit_project(result) == ""


def test_main_pipeline_chunk_shape_offers_next_steps():
    # The general orchestration pipeline (pricing detail, project overview,
    # availability, cross-project comparisons -- services/ai_agent_service.py)
    # names the project with a plain "project_name" string field.
    result = _run([{"project_name": "Vishwajeet Prime", "inventory_loaded": True}])
    assert {q["action"] for q in result["quick_replies"]} == ACTIONS
    assert _site_visit_project(result) == "Vishwajeet Prime"


def test_wing_floor_flat_inventory_shape_offers_next_steps():
    # services/property_clarification_service.py's build_inventory_selection_answer
    # (terminal wing/floor/flat listing) evidences units/typologies, no project key.
    result = _run([{"record_kind": "company_api", "source_key": "wing-10-inventory",
                     "units": [{"unitNumber": "101"}], "typologies": []}])
    assert {q["action"] for q in result["quick_replies"]} == ACTIONS


def test_snapshot_fallback_still_offers_next_steps():
    result = _run([{"project_name": "Vishwajeet Prime"}], source_status="snapshot")
    assert {q["action"] for q in result["quick_replies"]} == ACTIONS


def test_pending_clarification_is_not_offered_next_steps():
    # A "which project/wing/floor?" clarification is not a terminal answer.
    result = _run([], extra={"clarification_entity": "project"})
    assert not result.get("quick_replies")


def test_pending_project_lookup_is_not_offered_next_steps():
    result = _run([], extra={"pending_project_lookup": {"kind": "selection", "entity": "project", "options": ["A"]}})
    assert not result.get("quick_replies")


def test_existing_quick_replies_are_not_overwritten():
    existing = [{"label": "Vishwajeet Heights", "value": "Vishwajeet Heights"}]
    result = _run([{"project_name": "Vishwajeet Prime"}], extra={"quick_replies": existing})
    assert result["quick_replies"] == existing


def test_non_property_turn_is_not_offered_next_steps():
    result = _run([{"project_name": "Vishwajeet Prime"}], is_property=False)
    assert not result.get("quick_replies")


def test_failed_source_status_is_not_offered_next_steps():
    result = _run([{"project_name": "Vishwajeet Prime"}], source_status="failed")
    assert not result.get("quick_replies")


def test_browse_projects_value_resumes_the_full_catalogue():
    # The button's value is a plain chat message (frontend replays it with a
    # fresh conversation), so it must actually route back into the catalogue
    # browse, not silently fall through to general chat.
    result = _run([{"project_name": "Vishwajeet Prime"}])
    browse = next(q for q in result["quick_replies"] if q["action"] == "browse_projects")
    assert assist._is_broad_project_request(browse["value"])
