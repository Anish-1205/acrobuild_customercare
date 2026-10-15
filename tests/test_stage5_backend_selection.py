"""Stage 5 verifies backend selection cannot cross concurrent test requests."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from services import answer_engine_service
from services.readable_answer_engine import ReadableAnswerEngine


class _Backend:
    def __init__(self, name):
        self.implementation_name = name


def test_scoped_backend_selection_isolated_between_concurrent_requests():
    first = _Backend("first")
    second = _Backend("second")
    both_selected = Barrier(2)
    both_read = Barrier(2)

    def select(backend):
        with answer_engine_service.use_answer_engine(backend):
            both_selected.wait(timeout=5)
            selected = answer_engine_service.get_answer_engine()
            both_read.wait(timeout=5)
            return selected

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(select, first)
        second_future = pool.submit(select, second)
        assert first_future.result(timeout=10) is first
        assert second_future.result(timeout=10) is second

    assert answer_engine_service.get_answer_engine().implementation_name == "legacy_compiled"


def test_structured_property_answer_reports_live_source_and_workspace_stays_workspace():
    workspace = {
        "matched_chunks": [{"record_kind": "knowledge", "record_summary": "Document guide", "score": 8}],
        "retrieval_mode": "lexical", "articles": [], "knowledge_documents": [],
    }
    projects = [{"record_kind": "company_api", "source_key": "acrobuild-cs-projects",
                 "projects": [{"id": 1, "projectName": "Example Heights"}], "score": 100}]
    engine = ReadableAnswerEngine(
        workspace_search=lambda **_kwargs: workspace,
        company_search=lambda _query: projects,
        generator=lambda **_kwargs: "unused",
    )
    property_result = engine.answer(answer_engine_service.AnswerEngineRequest(issue="Show me all projects"))
    workspace_result = engine.answer(answer_engine_service.AnswerEngineRequest(
        issue="What documents should I prepare?", prefer_fast_response=True,
    ))

    assert property_result["agent_mode"] == "grounded"
    assert property_result["source_status"] == "live_api"
    assert workspace_result["agent_mode"] == "retrieval"
    assert workspace_result["source_status"] == "workspace"


def test_readable_stream_close_after_delta_has_no_terminal_and_cache_is_reusable():
    calls = []
    engine = ReadableAnswerEngine(
        workspace_search=lambda **_kwargs: {"matched_chunks": [
            {"record_kind": "knowledge", "record_summary": "Synthetic support policy.", "score": 8},
        ], "retrieval_mode": "lexical"},
        company_search=lambda _query: [],
        generator=lambda **_kwargs: calls.append(1) or "Synthetic policy answer.",
    )
    request = answer_engine_service.AnswerEngineRequest(issue="Explain the policy")
    with answer_engine_service.use_answer_engine(engine):
        events = answer_engine_service.stream_support_request(request)
        assert next(events) == {"type": "delta", "text": "Synthetic policy answer."}
        events.close()
        response = answer_engine_service.answer_support_request(request)

    assert response["answer"] == "Synthetic policy answer."
    assert calls == [1]
    assert answer_engine_service.get_answer_engine().implementation_name == "legacy_compiled"


@pytest.mark.parametrize("prefer_qwen_response", [True, False])
def test_generated_property_price_without_matching_evidence_is_rejected(prefer_qwen_response):
    engine = ReadableAnswerEngine(
        workspace_search=lambda **_kwargs: {"matched_chunks": [], "retrieval_mode": "empty"},
        company_search=lambda _query: [{
            "record_kind": "company_api", "source_key": "acrobuild-cs-project-1",
            "body_text": "Example Heights is in North Test. No verified price is available.",
            "score": 100,
        }],
        generator=lambda **_kwargs: "Example Heights costs INR 99,999 per sq. ft.",
    )
    response = engine.answer(answer_engine_service.AnswerEngineRequest(
        issue="What is the price of Example Heights?", issue_type="property",
        prefer_qwen_response=prefer_qwen_response,
    ))

    assert "99,999" not in response["answer"]
    assert response["used_llm"] is False
    assert response["confidence_label"] == "low"


@pytest.mark.parametrize("prefer_qwen_response", [True, False])
def test_generated_property_price_with_matching_company_evidence_can_pass(prefer_qwen_response):
    engine = ReadableAnswerEngine(
        workspace_search=lambda **_kwargs: {"matched_chunks": [], "retrieval_mode": "empty"},
        company_search=lambda _query: [{
            "record_kind": "company_api", "source_key": "acrobuild-cs-project-1",
            "body_text": "Example Heights base rate is INR 5,000 per sq. ft.",
            "score": 100,
        }],
        generator=lambda **_kwargs: "The listed base rate is INR 5,000 per sq. ft.",
    )
    response = engine.answer(answer_engine_service.AnswerEngineRequest(
        issue="What is the price of Example Heights?", issue_type="property",
        prefer_qwen_response=prefer_qwen_response,
    ))

    assert response["used_llm"] is True
    assert "INR 5,000" in response["answer"]
