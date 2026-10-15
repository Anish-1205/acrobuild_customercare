import json
from pathlib import Path

import pytest

from services import answer_engine_service
from services.answer_engine_service import AnswerEngineRequest
from services.readable_answer_engine import ReadableAnswerEngine
from services.turn_analysis_service import TurnAnalysis


CORPUS_PATH = Path(__file__).parent / "fixtures" / "stage4_readable_scenarios.json"
CORPUS = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))

WORKSPACE = {
    "articles": [{"title": "Document guide", "url": "https://example.test/documents"}],
    "embedding_error": "",
    "index_built_at": "2026-10-09T00:00:00Z",
    "index_error": "",
    "knowledge_documents": [],
    "matched_chunks": [{
        "record_kind": "knowledge",
        "title": "Document guide",
        "record_summary": "Keep identity and agreement documents ready for support review.",
        "score": 8,
    }],
    "retrieval_mode": "lexical",
}

PROJECTS = {
    "source_key": "acrobuild-cs-projects",
    "record_kind": "company_api",
    "title": "Company projects",
    "projects": [
        {"id": 1, "projectName": "Acro Heights", "locality": "North Test", "city": "Test City"},
        {"id": 2, "projectName": "Acro Gardens", "locality": "South Test", "city": "Test City"},
    ],
    "score": 100,
}

PROJECT_DETAIL = {
    "source_key": "acrobuild-cs-project-1",
    "record_kind": "company_api",
    "title": "Acro Heights live property details",
    "project_name": "Acro Heights",
    "project": {
        "id": 1,
        "projectName": "Acro Heights",
        "locality": "North Test",
        "city": "Test City",
        "reraNo": "TEST-RERA-1",
        "projectType": "Residential",
    },
    "wings": [{"id": 11, "name": "Wing A", "constructionStatus": "In progress"}],
    "typologies": [{
        "id": 21,
        "typologyType": "2BHK",
        "saleableArea": 800,
        "minBasePrice": 5000,
        "maxBasePrice": 5500,
    }],
    "available_inventory": [
        {"id": 31, "unitNumber": "101", "floorNumber": 1, "typologyType": "2BHK"},
        {"id": 32, "unitNumber": "201", "floorNumber": 2, "typologyType": "2BHK"},
    ],
    "inventory_loaded": True,
    "score": 100,
}


def _workspace_search(**_kwargs):
    return WORKSPACE


def _company_search(_query):
    return [PROJECTS, PROJECT_DETAIL]


def _engine():
    return ReadableAnswerEngine(
        workspace_search=_workspace_search,
        company_search=_company_search,
        generator=lambda **_kwargs: "A grounded synthetic answer.",
    )


def _request(scenario, **overrides):
    values = {
        "issue": scenario["issue"],
        "conversation_id": f"conversation-{scenario['id']}",
        "customer_name": "Synthetic Customer",
        "customer_email": "synthetic@example.test",
        "issue_type": "property",
        "conversation_messages": [],
        "prefer_fast_response": scenario["handler"] == "workspace_direct",
        "prefer_qwen_response": scenario.get("prefer_qwen_response", True),
    }
    values.update(overrides)
    return AnswerEngineRequest(**values)


def test_corpus_is_explicitly_constructed_not_live_evidence():
    assert CORPUS["evidence_class"] == "constructed_sanitized_scenarios"
    assert "not production conversation evidence" in CORPUS["note"]


def test_corpus_maps_every_upstream_supported_family_to_readable_owners_and_tests():
    families = {entry["family"] for entry in CORPUS["upstream_contracts"]}
    assert families == {
        "amenities",
        "bhk_and_project_selection",
        "discovery_and_feature_flag",
        "grounding_and_failures",
        "multilingual_finalization",
        "property_clarification",
        "support_actions",
    }
    for entry in CORPUS["upstream_contracts"]:
        assert entry["owner"]
        assert entry["tests"]
        assert all((Path(__file__).parent.parent / path).exists() for path in entry["tests"])


@pytest.mark.parametrize("scenario", CORPUS["scenarios"], ids=lambda item: item["id"])
def test_supported_corpus_runs_in_readable_mode_without_legacy(monkeypatch, scenario):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("compiled legacy backend was invoked")

    monkeypatch.setattr(answer_engine_service.LegacyCompiledAnswerEngine, "answer", forbidden)
    monkeypatch.setattr(answer_engine_service.LegacyCompiledAnswerEngine, "stream", forbidden)
    engine = _engine()
    request = _request(scenario)

    with answer_engine_service.use_answer_engine(engine):
        response = answer_engine_service.answer_support_request(request)
        events = list(answer_engine_service.stream_support_request(request))

    assert response["selected_handler"] == scenario["handler"]
    assert events[-1] == {"type": "done", "response": response}
    assert sum(event["type"] == "done" for event in events) == 1
    assert response["used_llm"] is (scenario["handler"] == "grounded_generation")


def test_price_and_inventory_contracts_are_grounded_and_distinct():
    engine = _engine()
    price = engine.answer(_request({
        "id": "price", "issue": "What is the 2BHK price in Acro Heights?", "handler": "project_detail",
    }))
    inventory = engine.answer(_request({
        "id": "inventory", "issue": "How many units are available in Acro Heights?", "handler": "project_detail",
    }))

    assert "INR 5,000–5,500 per sq. ft." in price["answer"]
    assert "taxes" in price["answer"].lower() and "final quotation" in price["answer"]
    assert "2 available units" in inventory["answer"]
    assert "catalogue" not in inventory["answer"].lower()


def test_unloaded_inventory_never_claims_availability():
    unloaded = {**PROJECT_DETAIL, "available_inventory": [], "inventory_loaded": False}
    engine = ReadableAnswerEngine(
        workspace_search=_workspace_search,
        company_search=lambda _query: [PROJECTS, unloaded],
        generator=lambda **_kwargs: "must not generate",
    )
    response = engine.answer(_request({
        "id": "unloaded", "issue": "Are units available in Acro Heights?", "handler": "project_detail",
    }))

    assert "Availability was not checked" in response["answer"]
    assert "0 available" not in response["answer"]


def test_contextual_follow_up_is_used_for_retrieval_without_leaking_to_response():
    queries = []
    engine = ReadableAnswerEngine(
        workspace_search=lambda **kwargs: queries.append(kwargs["query"]) or WORKSPACE,
        company_search=_company_search,
        generator=lambda **_kwargs: "A grounded synthetic answer.",
    )
    scenario = {"id": "follow-up", "issue": "What about its price?", "handler": "project_detail"}
    request = _request(
        scenario,
        conversation_messages=[{"sender": "customer", "text": "Tell me about Acro Heights"}],
    )

    response = engine.answer(request)

    assert "Acro Heights" in queries[0]
    assert response["selected_handler"] == "project_detail"


def test_retrieval_failure_returns_safe_response_without_property_facts():
    engine = ReadableAnswerEngine(
        workspace_search=lambda **_kwargs: {**WORKSPACE, "matched_chunks": [], "retrieval_mode": "empty"},
        company_search=lambda _query: (_ for _ in ()).throw(RuntimeError("CS unavailable")),
        generator=lambda **_kwargs: "must not generate",
    )
    response = engine.answer(AnswerEngineRequest(
        issue="What is available in Unknown Project?",
        conversation_id="failure",
        issue_type="property",
    ))

    assert response["selected_handler"] == "clarification_fallback"
    assert response["source_status"] == "fallback"
    assert "enough verified information" in response["answer"]
    assert "Unknown Project is" not in response["answer"]


@pytest.mark.parametrize("prefer_qwen_response", [True, False])
def test_json_and_stream_orchestration_use_readable_backend_without_legacy(
    monkeypatch,
    prefer_qwen_response,
):
    import graph.main_orchestrator as orchestrator

    def forbidden(*_args, **_kwargs):
        raise AssertionError("compiled legacy backend was invoked")

    monkeypatch.setattr(answer_engine_service.LegacyCompiledAnswerEngine, "answer", forbidden)
    monkeypatch.setattr(answer_engine_service.LegacyCompiledAnswerEngine, "stream", forbidden)
    issue = "Where is Acro Heights located?"
    messages = [{"sender": "customer", "text": issue}]
    turn = orchestrator.TurnContext(
        conversation_messages=messages,
        resolved_issue=issue,
        property_issue=issue,
        analysis=TurnAnalysis(
            intent="property",
            reply_language="English",
            script="latin",
            source="constructed_stage4_corpus",
            english=issue,
        ),
    )
    engine = _engine()

    with answer_engine_service.use_answer_engine(engine):
        response = orchestrator.run_support_orchestration(
            issue,
            conversation_id=f"json-{prefer_qwen_response}",
            conversation_messages=messages,
            prefer_qwen_response=prefer_qwen_response,
            turn=turn,
        )
        events = list(orchestrator.stream_support_orchestration_events(
            issue,
            conversation_id=f"stream-{prefer_qwen_response}",
            conversation_messages=messages,
            prefer_qwen_response=prefer_qwen_response,
            turn=turn,
        ))

    assert response["answer"]
    assert events[-1]["type"] == "done"
    assert events[-1]["response"]["answer"]
    assert sum(event["type"] == "done" for event in events) == 1
