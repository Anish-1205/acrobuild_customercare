"""Offline endpoint acceptance for the readable backend and property buffering."""
import json

import pytest
from fastapi.testclient import TestClient

from app import api
from graph import main_orchestrator
from graph import haystack_conversation_pipeline_source
from graph.main_orchestrator import TurnContext
from routers import assist
from services import answer_engine_service
from services.internal_api_log_service import log_data_api_call
from services.readable_answer_engine import ReadableAnswerEngine
from services import property_clarification_service
from services.conversation_store_service import build_pending_project_lookup_marker, get_current_project_context
from services.turn_analysis_service import TurnAnalysis


@pytest.mark.parametrize("prefer_qwen_response", [True, False])
def test_readable_json_and_stream_keep_final_property_answer_and_session_state(
    monkeypatch, prefer_qwen_response,
):
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", "false")
    issue = "Where is Example Heights project located?"
    turn = TurnContext(
        conversation_messages=[], resolved_issue=issue, property_issue=issue,
        analysis=TurnAnalysis("property", "English", "latin", "stage5_synthetic"),
    )
    saved = []

    class Session:
        def __init__(self, *_args):
            pass

        def load(self):
            return []

        def set_cookie(self, *_args):
            pass

        def append(self, customer_issue, answer, marker=""):
            saved.append((customer_issue, answer, marker))

    monkeypatch.setattr(assist, "ConversationSession", Session)
    monkeypatch.setattr(assist, "_prepare_lookup_turn", lambda request, _issue, slots=None: (None, request, issue, turn))
    monkeypatch.setattr(assist, "_grounded_property_shortcut", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(assist, "_is_broad_project_request", lambda *_args: False)
    monkeypatch.setattr(assist, "apply_clarification_contract", lambda payload, *_args: payload)
    monkeypatch.setattr(assist, "localize_response", lambda payload, *_args: payload)
    monkeypatch.setattr(main_orchestrator, "apply_clarification_contract", lambda payload, *_args: payload)
    monkeypatch.setattr(main_orchestrator, "validate_support_node", lambda state: state)
    monkeypatch.setattr(haystack_conversation_pipeline_source, "validate_support_node", lambda state: state)

    def company_search(_query):
        log_data_api_call(provider="Acrobuild CS API", endpoint="/api/cs/projects",
                          method="GET", status="completed", response_summary={"record_count": 1})
        return [{
            "record_kind": "company_api", "source_key": "acrobuild-cs-project-1",
            "project_name": "Example Heights",
            "project": {"id": 1, "projectName": "Example Heights", "locality": "North Test"},
            "score": 100,
        }]

    engine = ReadableAnswerEngine(
        workspace_search=lambda **_kwargs: {"matched_chunks": [], "retrieval_mode": "empty"},
        company_search=company_search,
        generator=lambda **_kwargs: "unexpected generation",
    )
    client = TestClient(api)
    request = {"issue": issue, "conversation_id": "stage5-synthetic",
               "prefer_qwen_response": prefer_qwen_response}
    with answer_engine_service.use_answer_engine(engine):
        json_result = client.post("/api/support/assist", json=request)
        stream_result = client.post("/api/support/assist/stream", json=request)

    assert json_result.status_code == 200
    assert stream_result.status_code == 200
    events = [json.loads(line) for line in stream_result.text.splitlines()]
    assert [event["type"] for event in events] == ["delta", "done"]
    assert events[0]["text"] == events[1]["response"]["answer"]
    assert json_result.json()["answer"] == events[1]["response"]["answer"]
    assert json_result.json()["source_status"] == events[1]["response"]["source_status"] == "live_api"
    assert len(saved) == 2
    assert all(row[0] == issue and row[1] == json_result.json()["answer"] for row in saved)
    assert answer_engine_service.get_answer_engine().implementation_name == "legacy_compiled"


@pytest.mark.parametrize("status", ["In progress", ""])
def test_construction_status_followup_survives_json_and_stream_finalization(monkeypatch, status):
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", "false")
    issue = "Where is this project and what is its construction status?"
    resolved = "Where is Example Heights and what is its construction status?"
    turn = TurnContext(
        conversation_messages=[{"sender": "bot", "text": "Example Heights"}],
        resolved_issue=resolved, property_issue=resolved,
        analysis=TurnAnalysis("property", "English", "latin", "stage5_synthetic"),
    )

    class Session:
        def __init__(self, *_args):
            pass

        def load(self):
            return []

        def set_cookie(self, *_args):
            pass

        def append(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr(assist, "ConversationSession", Session)
    monkeypatch.setattr(assist, "_prepare_lookup_turn",
                        lambda request, _issue, slots=None: (None, request, resolved, turn))
    monkeypatch.setattr(assist, "_grounded_property_shortcut", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(assist, "_is_broad_project_request", lambda *_args: False)
    monkeypatch.setattr(assist, "localize_response", lambda payload, *_args: payload)
    monkeypatch.setattr(main_orchestrator, "validate_support_node", lambda state: state)
    monkeypatch.setattr(property_clarification_service, "get_company_projects",
                        lambda: pytest.fail("Unexpected clarification catalogue read"))

    def company_search(_query):
        log_data_api_call(provider="Acrobuild CS API", endpoint="/api/cs/projects",
                          method="GET", status="completed", response_summary={"record_count": 1})
        return [{
            "record_kind": "company_api", "source_key": "acrobuild-cs-project-1",
            "project_name": "Example Heights",
            "project": {"id": 1, "projectName": "Example Heights", "locality": "North Test"},
            "wings": [{"name": "A", "constructionStatus": status}],
            "score": 100,
        }]

    engine = ReadableAnswerEngine(
        workspace_search=lambda **_kwargs: {"matched_chunks": [], "retrieval_mode": "empty"},
        company_search=company_search,
        generator=lambda **_kwargs: pytest.fail("Unexpected generation"),
    )
    request = {"issue": issue, "conversation_id": "stage5-construction",
               "prefer_qwen_response": True}
    client = TestClient(api)
    with answer_engine_service.use_answer_engine(engine):
        json_result = client.post("/api/support/assist", json=request)
        stream_result = client.post("/api/support/assist/stream", json=request)

    assert json_result.status_code == stream_result.status_code == 200
    events = [json.loads(line) for line in stream_result.text.splitlines()]
    assert [event["type"] for event in events] == ["delta", "done"]
    answer = json_result.json()["answer"]
    assert answer == events[-1]["response"]["answer"]
    assert json_result.json().get("clarification_entity") is None
    assert events[-1]["response"].get("clarification_entity") is None
    assert not json_result.json().get("pending_project_lookup")
    assert not events[-1]["response"].get("pending_project_lookup")
    assert "North Test" in answer
    if status:
        assert status in answer
    else:
        assert "construction status" in answer.lower()
        assert "can't verify" in answer.lower()
    assert json_result.json()["source_status"] == events[-1]["response"]["source_status"] == "live_api"


@pytest.mark.parametrize("status", ["", "In progress"])
def test_selected_project_resumes_construction_question_on_both_endpoints(monkeypatch, status):
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", "false")
    original = "What is the construction status of the project?"
    pending = {"kind": "selection", "original_issue": original, "entity": "project",
               "options": ["Cedar Heights", "Maple Gardens"], "scope": {}}
    saved = [
        {"sender": "customer", "text": original},
        {"sender": "bot", "text": "Which project should I check?" + build_pending_project_lookup_marker(pending)},
    ]
    appended = []

    class Session:
        def __init__(self, *_args):
            pass

        def load(self):
            return saved

        def set_cookie(self, *_args):
            pass

        def append(self, customer_issue, answer, marker=""):
            appended.append((customer_issue, answer, marker))

    monkeypatch.setattr(assist, "ConversationSession", Session)
    monkeypatch.setattr(assist, "prepare_turn", lambda issue, *_args: TurnContext(
        conversation_messages=[{"sender": "customer", "text": original},
                               {"sender": "bot", "text": "Which project should I check?"}],
        resolved_issue=issue, property_issue=issue,
        analysis=TurnAnalysis("property", "English", "latin", "stage5_synthetic"),
    ))
    monkeypatch.setattr(assist, "_grounded_property_shortcut", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(assist, "_is_broad_project_request", lambda *_args: False)
    monkeypatch.setattr(assist, "localize_response", lambda payload, *_args: payload)
    monkeypatch.setattr(haystack_conversation_pipeline_source, "get_live_project_names",
                        lambda: ["Cedar Heights", "Maple Gardens"])

    def company_search(_query):
        log_data_api_call(provider="Acrobuild CS API", endpoint="/api/cs/projects",
                          method="GET", status="completed", response_summary={"record_count": 2})
        return [
            {"record_kind": "company_api", "source_key": f"acrobuild-cs-project-{index}",
             "project_name": name, "project": {"id": index, "projectName": name,
                                                 "locality": f"Area {index}"},
             "wings": [{"name": "A", "constructionStatus": "In progress" if index == 1 else status}],
             "score": 100}
            for index, name in enumerate(["Cedar Heights", "Maple Gardens"], 1)
        ]

    engine = ReadableAnswerEngine(
        workspace_search=lambda **_kwargs: {"matched_chunks": [], "retrieval_mode": "empty"},
        company_search=company_search,
        generator=lambda **_kwargs: pytest.fail("Unexpected generation"),
    )
    client = TestClient(api)
    request = {"issue": "Maple Gardens", "conversation_id": "stage5-selected-construction"}
    with answer_engine_service.use_answer_engine(engine):
        json_result = client.post("/api/support/assist", json=request)
        stream_result = client.post("/api/support/assist/stream", json=request)

    assert json_result.status_code == stream_result.status_code == 200
    events = [json.loads(line) for line in stream_result.text.splitlines()]
    assert [event["type"] for event in events] == ["delta", "done"]
    answer = json_result.json()["answer"]
    assert answer == events[-1]["response"]["answer"]
    assert "Maple Gardens" in answer and "Cedar Heights" not in answer
    assert "Area 2" in answer and "Area 1" not in answer
    assert (status in answer) if status else ("can't verify" in answer)
    assert all(issue == "Maple Gardens" for issue, _answer, _marker in appended)
    assert all(get_current_project_context(marker) == {"project": "Maple Gardens"}
               for _issue, _answer, marker in appended)


@pytest.mark.parametrize("prefer_qwen_response", [True, False])
def test_readable_json_and_stream_allow_grounded_generation_in_both_preference_modes(
    monkeypatch, prefer_qwen_response,
):
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", "false")
    issue = "Explain the AcroBuild support policy for owners"
    turn = TurnContext(
        conversation_messages=[], resolved_issue=issue, property_issue=issue,
        analysis=TurnAnalysis("property", "English", "latin", "stage5_synthetic"),
    )
    saved = []
    generation_calls = []

    class Session:
        def __init__(self, *_args):
            pass

        def load(self):
            return []

        def set_cookie(self, *_args):
            pass

        def append(self, customer_issue, answer, marker=""):
            saved.append((customer_issue, answer))

    monkeypatch.setattr(assist, "ConversationSession", Session)
    monkeypatch.setattr(assist, "_prepare_lookup_turn",
                        lambda request, _issue, slots=None: (None, request, issue, turn))
    monkeypatch.setattr(assist, "_grounded_property_shortcut", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(assist, "_is_broad_project_request", lambda *_args: False)
    monkeypatch.setattr(assist, "apply_clarification_contract", lambda payload, *_args: payload)
    monkeypatch.setattr(assist, "localize_response", lambda payload, *_args: payload)
    monkeypatch.setattr(main_orchestrator, "apply_clarification_contract", lambda payload, *_args: payload)
    monkeypatch.setattr(main_orchestrator, "validate_support_node", lambda state: state)
    monkeypatch.setattr(haystack_conversation_pipeline_source, "validate_support_node", lambda state: state)

    def company_search(_query):
        log_data_api_call(provider="Acrobuild CS API", endpoint="/api/cs/projects",
                          method="GET", status="completed", response_summary={"record_count": 1})
        return [{"record_kind": "company_api", "source_key": "acrobuild-cs-support-policy",
                 "body_text": "Synthetic support policy: owners may ask the team for guidance.",
                 "score": 9}]

    def generate(**_kwargs):
        generation_calls.append(1)
        return "Owners may ask the support team for guidance."

    engine = ReadableAnswerEngine(
        workspace_search=lambda **_kwargs: {"matched_chunks": [], "retrieval_mode": "empty"},
        company_search=company_search,
        generator=generate,
    )
    request = {"issue": issue, "conversation_id": "stage5-generated",
               "prefer_qwen_response": prefer_qwen_response}
    client = TestClient(api)
    with answer_engine_service.use_answer_engine(engine):
        json_result = client.post("/api/support/assist", json=request)
        stream_result = client.post("/api/support/assist/stream", json=request)

    events = [json.loads(line) for line in stream_result.text.splitlines()]
    assert json_result.status_code == stream_result.status_code == 200
    assert json_result.json()["used_llm"] is True
    assert json_result.json()["answer"] == "Owners may ask the support team for guidance."
    assert [event["type"] for event in events] == ["delta", "done"]
    assert events[-1]["response"]["answer"] == json_result.json()["answer"]
    assert events[-1]["response"]["used_llm"] is True
    assert generation_calls == [1, 1]
    assert len(saved) == 2
