import json
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_context
from routers import assist
from graph.main_orchestrator import TurnContext, _localize_answer
from services.turn_analysis_service import TurnAnalysis

PROJECTS = [
    {"id": 50, "projectName": "Vishwajeet Empire"},
    {"id": 57, "projectName": "Vishwajeet Prime"},
    {"id": 54, "projectName": "Vishwajeet Myspace"},
    {"id": 52, "projectName": "Vishwajeet Precious"},
]


def test_two_turn_amenities_on_both_endpoints():
    app = FastAPI()
    app.include_router(assist.router)
    for endpoint in ("/api/support/assist", "/api/support/assist/stream"):
        history = []
        def append(issue, answer, marker=""):
            history.extend([{"sender": "customer", "text": issue},
                            {"sender": "bot", "text": answer + marker}])
        # Deliberately unreliable analysis must not override explicit lookup state.
        turn = TurnContext([], "Tell me about projects", TurnAnalysis(
            intent="general", reply_language="English", script="latin",
            source="test", unsure=True), "Tell me about projects")
        with TestClient(app) as client, \
                patch.object(assist.ConversationSession, "load", side_effect=lambda: list(history)), \
                patch.object(assist.ConversationSession, "append", side_effect=append), \
                patch.object(assist, "prepare_turn", return_value=turn), \
                patch.object(assist, "get_current_data_api_logs", return_value=[{"provider": "Acrobuild CS API", "status": "completed", "endpoint": "/api/cs/projects"}]), \
                patch("services.property_clarification_service.get_company_projects", return_value=PROJECTS), \
                patch.object(api_context, "get_company_projects", return_value=PROJECTS), \
                patch.object(api_context, "get_project_amenities", return_value=[{"iconName": "Gym"}, {"iconName": "Swimming Pool"}]) as amenities, \
                patch.object(assist, "run_support_orchestration", side_effect=AssertionError("lookup fell through")), \
                patch.object(assist, "stream_support_orchestration_events", side_effect=AssertionError("lookup fell through")):
            def ask(issue):
                response = client.post(endpoint, json={"issue": issue, "conversation_id": "amenities-regression"})
                assert response.status_code == 200
                if endpoint.endswith("stream"):
                    return next(json.loads(line)["response"] for line in response.text.splitlines()
                                if json.loads(line).get("type") == "done")
                return response.json()
            first = ask("vishwajeet lo amenities em em vunnai ?")
            for project in PROJECTS:
                assert project["projectName"] in first["answer"]
            amenities.assert_not_called()
            second = ask("precious")
            assert "Vishwajeet Precious" in second["answer"]
            assert "Gym" in second["answer"]
            assert "Swimming Pool" in second["answer"]
            amenities.assert_called_once_with(52)


def test_unspecified_project_lists_catalogue():
    index = {p["id"]: {"project": p, "amenities": ["Gym"] if p["id"] == 57 else []} for p in PROJECTS}
    with patch.object(api_context, "get_company_projects", return_value=PROJECTS), \
            patch.object(api_context, "live_amenity_index", return_value=index):
        result = api_context.build_grounded_project_amenities_assist(
            api_context.SupportAssistRequest(issue="What amenities are available?"))
    assert result["pending_project_lookup"]["options"] == ["Vishwajeet Prime"]
    assert "Vishwajeet Myspace" not in result["answer"]


def test_translation_cannot_discard_retrieved_list():
    answer = "Amenities for Vishwajeet Precious:\n- Gym\n- Swimming Pool"
    analysis = TurnAnalysis(intent="property", reply_language="Telugu", script="latin", source="test")
    with patch("graph.main_orchestrator.generate_qwen_chat_response", return_value="Please contact support."):
        assert _localize_answer(answer, analysis) == answer
