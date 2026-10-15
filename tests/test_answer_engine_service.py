from concurrent.futures import ThreadPoolExecutor
import inspect
from unittest.mock import patch

import pytest

from services import ai_agent_service as legacy
from services import answer_engine_service as engine_service
from scripts.stage0_runtime_characterization import (
    SYNTHETIC_PROJECT_CHUNK,
    SYNTHETIC_WORKSPACE_RESULT,
)


def _request(**overrides):
    values = {
        "issue": "Tell me about the selected project",
        "customer_name": "Test Customer",
        "customer_email": "customer@example.test",
        "business_hours_tag": "open",
        "issue_type": "property",
        "article_hint_url": "https://example.test/article",
        "conversation_messages": [{"sender": "customer", "text": "Earlier question"}],
        "limit": 4,
        "prefer_fast_response": True,
        "prefer_qwen_response": False,
    }
    values.update(overrides)
    return engine_service.AnswerEngineRequest(**values)


class FakeAnswerEngine:
    implementation_name = "fake_readable"

    def __init__(self):
        self.requests = []
        self.clear_count = 0

    def answer(self, request):
        self.requests.append(request)
        return {"answer": "fixture", "used_llm": False, "source_status": "fixture"}

    def stream(self, request):
        self.requests.append(request)
        yield {"type": "delta", "text": "fixture"}
        yield {"type": "done", "response": {"answer": "fixture", "used_llm": False}}

    def clear_cache(self):
        self.clear_count += 1


def test_json_compatibility_function_builds_typed_request(monkeypatch):
    fake = FakeAnswerEngine()
    monkeypatch.setattr(engine_service, "_ACTIVE_ANSWER_ENGINE", fake)

    response = engine_service.build_ai_support_answer(**_request().legacy_kwargs())

    assert response == {"answer": "fixture", "used_llm": False, "source_status": "fixture"}
    assert fake.requests == [_request()]


def test_conversation_scope_reaches_typed_request_without_signature_change(monkeypatch):
    fake = FakeAnswerEngine()
    monkeypatch.setattr(engine_service, "_ACTIVE_ANSWER_ENGINE", fake)

    with engine_service.answer_engine_conversation_scope("conversation-one"):
        engine_service.build_ai_support_answer(**_request().legacy_kwargs())

    assert fake.requests == [_request(conversation_id="conversation-one")]


def test_streaming_events_are_exposed_without_mutation(monkeypatch):
    fake = FakeAnswerEngine()
    monkeypatch.setattr(engine_service, "_ACTIVE_ANSWER_ENGINE", fake)

    events = list(engine_service.stream_ai_support_answer_events(**_request().legacy_kwargs()))

    assert events == [
        {"type": "delta", "text": "fixture"},
        {"type": "done", "response": {"answer": "fixture", "used_llm": False}},
    ]
    assert fake.requests == [_request()]


def test_cache_invalidation_delegates_to_active_backend(monkeypatch):
    fake = FakeAnswerEngine()
    monkeypatch.setattr(engine_service, "_ACTIVE_ANSWER_ENGINE", fake)

    engine_service.clear_assist_response_cache()

    assert fake.clear_count == 1


def test_legacy_adapter_resolves_existing_monkeypatch_points_dynamically():
    response = {"answer": "patched legacy"}
    events = [{"type": "done", "response": response}]
    request = _request()

    with (
        patch.object(legacy, "build_ai_support_answer", return_value=response) as answer,
        patch.object(legacy, "stream_ai_support_answer_events", return_value=iter(events)) as stream,
        patch.object(legacy, "clear_assist_response_cache") as clear,
    ):
        adapter = engine_service.LegacyCompiledAnswerEngine()
        assert adapter.answer(request) is response
        assert list(adapter.stream(request)) == events
        adapter.clear_cache()

    answer.assert_called_once_with(**request.legacy_kwargs())
    stream.assert_called_once_with(**request.legacy_kwargs())
    clear.assert_called_once_with()


def test_compatibility_function_signatures_match_legacy_entry_points():
    assert inspect.signature(engine_service.build_ai_support_answer) == inspect.signature(
        legacy.build_ai_support_answer,
    )
    assert inspect.signature(engine_service.stream_ai_support_answer_events) == inspect.signature(
        legacy.stream_ai_support_answer_events,
    )


def test_production_orchestration_and_api_context_use_readable_boundary():
    import api_context
    import graph.main_orchestrator as orchestrator

    assert orchestrator.build_ai_support_answer is engine_service.build_ai_support_answer
    assert orchestrator.stream_ai_support_answer_events is engine_service.stream_ai_support_answer_events
    assert api_context.build_ai_support_answer is engine_service.build_ai_support_answer
    assert api_context.stream_ai_support_answer_events is engine_service.stream_ai_support_answer_events
    assert api_context.clear_assist_response_cache is engine_service.clear_assist_response_cache


def test_synthetic_json_and_stream_results_match_direct_legacy_execution():
    issue = "Tell me about Stage Zero Project through the Stage 3 interface"
    patches = (
        patch.object(legacy, "search_workspace_knowledge", return_value=SYNTHETIC_WORKSPACE_RESULT),
        patch.object(legacy, "search_company_knowledge", return_value=[SYNTHETIC_PROJECT_CHUNK]),
        patch.object(legacy, "get_company_projects", return_value=[]),
        patch.object(legacy, "get_customer_context", return_value={}),
        patch.object(
            legacy,
            "generate_qwen_chat_response",
            return_value="Stage Zero Project has synthetic characterization information.",
        ),
    )

    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        legacy.clear_assist_response_cache()
        direct_response = legacy.build_ai_support_answer(issue=issue)
        legacy.clear_assist_response_cache()
        interface_response = engine_service.build_ai_support_answer(issue=issue)
        legacy.clear_assist_response_cache()
        direct_events = list(legacy.stream_ai_support_answer_events(issue=f"{issue} streaming"))
        legacy.clear_assist_response_cache()
        interface_events = list(engine_service.stream_ai_support_answer_events(issue=f"{issue} streaming"))

    assert interface_response == direct_response
    assert interface_events == direct_events


def test_observability_does_not_log_request_or_customer_content(monkeypatch, caplog):
    fake = FakeAnswerEngine()
    monkeypatch.setattr(engine_service, "_ACTIVE_ANSWER_ENGINE", fake)
    secret_issue = "private customer question 483920"

    with caplog.at_level("INFO", logger="chatbot.answer_engine"):
        engine_service.answer_support_request(_request(issue=secret_issue))

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert "fake_readable" in rendered
    assert "delivery=json" in rendered
    assert secret_issue not in rendered
    assert "customer@example.test" not in rendered
    assert "Test Customer" not in rendered


def test_legacy_cache_key_isolates_customer_context_and_request_scope():
    base = {
        "issue": "price please",
        "customer_email": "one@example.test",
        "issue_type": "property",
        "business_hours_tag": "open",
        "article_hint_url": "article-one",
        "conversation_messages": [{"sender": "customer", "text": "Project One"}],
        "limit": 3,
        "prefer_fast_response": False,
        "prefer_qwen_response": True,
    }
    baseline = legacy.build_assist_cache_key(**base)

    for field, value in (
        ("customer_email", "two@example.test"),
        ("issue", "availability please"),
        ("issue_type", "billing"),
        ("business_hours_tag", "closed"),
        ("article_hint_url", "article-two"),
        ("conversation_messages", [{"sender": "customer", "text": "Project Two"}]),
        ("limit", 6),
        ("prefer_fast_response", True),
        ("prefer_qwen_response", False),
    ):
        assert legacy.build_assist_cache_key(**{**base, field: value}) != baseline

    with legacy.assist_cache_scope(customer_name="Customer One", conversation_id="conversation-one"):
        first_scope = legacy.build_assist_cache_key(**base)
    with legacy.assist_cache_scope(customer_name="Customer Two", conversation_id="conversation-one"):
        second_customer = legacy.build_assist_cache_key(**base)
    with legacy.assist_cache_scope(customer_name="Customer One", conversation_id="conversation-two"):
        second_conversation = legacy.build_assist_cache_key(**base)

    assert first_scope != second_customer
    assert first_scope != second_conversation


def test_legacy_cache_copy_expiry_and_concurrent_key_isolation(monkeypatch):
    legacy.clear_assist_response_cache()
    now = 1_000.0
    monkeypatch.setattr(legacy, "time", lambda: now)
    payload = {"answer": "cached", "matched_chunks": [{"id": "one"}]}
    legacy.store_cached_assist_response("copy", payload)

    first = legacy.get_cached_assist_response("copy")
    first["matched_chunks"][0]["id"] = "changed"
    assert legacy.get_cached_assist_response("copy") == payload

    monkeypatch.setattr(legacy, "time", lambda: now + legacy.ASSIST_RESPONSE_CACHE_TTL_SECONDS + 1)
    assert legacy.get_cached_assist_response("copy") is None

    def store_and_read(index):
        key = f"concurrent-{index}"
        value = {"answer": str(index)}
        legacy.store_cached_assist_response(key, value)
        return legacy.get_cached_assist_response(key)

    monkeypatch.setattr(legacy, "time", lambda: now)
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(store_and_read, range(32)))
    assert results == [{"answer": str(index)} for index in range(32)]

    def scoped_key(index):
        with legacy.assist_cache_scope(
            customer_name=f"Customer {index}",
            conversation_id=f"conversation-{index}",
        ):
            return legacy.build_assist_cache_key(issue="same issue")

    with ThreadPoolExecutor(max_workers=8) as executor:
        scoped_keys = list(executor.map(scoped_key, range(32)))
    assert len(set(scoped_keys)) == 32
    legacy.clear_assist_response_cache()


def test_interface_propagates_backend_failures_without_rewriting_them(monkeypatch):
    fake = FakeAnswerEngine()
    monkeypatch.setattr(engine_service, "_ACTIVE_ANSWER_ENGINE", fake)
    failure = RuntimeError("fixture failure")
    monkeypatch.setattr(fake, "answer", lambda request: (_ for _ in ()).throw(failure))

    with pytest.raises(RuntimeError) as raised:
        engine_service.answer_support_request(_request())

    assert raised.value is failure
