"""A base-rate question must not depend on the live inventory endpoint."""

import pytest

from services import acrobuild_company_service as company_service
from services.answer_engine_service import AnswerEngineRequest
from services.readable_answer_engine import ReadableAnswerEngine


def test_readable_price_answer_survives_unrelated_inventory_timeout(monkeypatch):
    calls = []

    def fetch(path, params=None, ttl_seconds=None):
        calls.append(path)
        if path == "/api/cs/projects":
            return [{"id": 1, "projectName": "Example Heights", "city": "Test City"}]
        if path == "/api/cs/projects/1/wings":
            return [{"id": 2, "name": "A"}]
        if path == "/api/cs/projects/1/typologies":
            return [{"typologyName": "2 BHK", "saleableArea": 800,
                     "rateType": "Per Sq Ft", "minBasePrice": 5000, "maxBasePrice": 5500}]
        if path == "/api/cs/wings/2/inventory":
            raise RuntimeError("CS API request timed out.")
        raise AssertionError(f"Unexpected read: {path}")

    monkeypatch.setattr(company_service, "is_cs_api_configured", lambda: True)
    monkeypatch.setattr(company_service, "_cached_request", fetch)
    engine = ReadableAnswerEngine(
        workspace_search=lambda **_kwargs: {"matched_chunks": [], "retrieval_mode": "empty"},
        company_search=company_service.search_company_knowledge,
        generator=lambda **_kwargs: "unexpected generation",
    )
    request = AnswerEngineRequest(
        issue="What is the 2 BHK price in Example Heights?",
        conversation_id="synthetic-price-isolation", issue_type="property",
    )

    answer = engine.answer(request)
    events = list(engine.stream(request))

    assert answer["selected_handler"] == "project_detail"
    assert answer["source_status"] == "live_api"
    assert "INR 5,000–5,500 per sq. ft." in answer["answer"]
    assert "/api/cs/wings/2/inventory" not in calls
    assert events[-1] == {"type": "done", "response": answer}
    assert sum(event["type"] == "done" for event in events) == 1

    with pytest.raises(RuntimeError, match="timed out"):
        company_service.search_company_knowledge(
            "What is the price and availability in Example Heights?",
        )
    assert "/api/cs/wings/2/inventory" in calls
