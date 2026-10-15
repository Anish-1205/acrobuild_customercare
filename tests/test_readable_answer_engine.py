from concurrent.futures import ThreadPoolExecutor

import pytest

from services import answer_engine_service
from services.answer_engine_service import AnswerEngineRequest
from services.readable_answer_engine import (
    ReadableAnswerEngine,
    build_system_prompt,
    is_excluded_historical_retail_request,
)
from services.property_clarification_service import resume_selection


EMPTY_WORKSPACE = {
    "articles": [],
    "embedding_error": "",
    "index_built_at": "2026-10-09T00:00:00Z",
    "index_error": "",
    "knowledge_documents": [],
    "matched_chunks": [],
    "retrieval_mode": "empty",
}

PROJECTS = {
    "source_key": "acrobuild-cs-projects",
    "record_kind": "company_api",
    "title": "Company projects",
    "projects": [
        {"id": 1, "projectName": "Acro Heights", "locality": "North Test"},
        {"id": 2, "projectName": "Acro Gardens", "city": "Test City"},
    ],
    "score": 100.0,
}


def _request(issue="Tell me about the projects", **overrides):
    values = {
        "issue": issue,
        "conversation_id": "conversation-one",
        "customer_name": "Test Customer",
        "customer_email": "customer@example.test",
        "issue_type": "property",
        "conversation_messages": [{"sender": "customer", "text": "Earlier context"}],
        "limit": 3,
        "prefer_fast_response": False,
        "prefer_qwen_response": True,
    }
    values.update(overrides)
    return AnswerEngineRequest(**values)


def _engine(*, workspace=None, company=None, generator=None, ttl=45):
    return ReadableAnswerEngine(
        workspace_search=lambda **_kwargs: workspace or EMPTY_WORKSPACE,
        company_search=lambda _query: company or [],
        generator=generator or (lambda **_kwargs: "Grounded generated answer."),
        cache_ttl_seconds=ttl,
    )


@pytest.mark.parametrize("prefer_qwen_response", [True, False])
def test_project_catalogue_is_deterministic_and_does_not_call_generator(prefer_qwen_response):
    calls = []
    engine = _engine(company=[PROJECTS], generator=lambda **kwargs: calls.append(kwargs))

    response = engine.answer(_request("Where are your projects?", prefer_qwen_response=prefer_qwen_response))

    assert response["selected_handler"] == "project_catalogue"
    assert response["used_llm"] is False
    assert "Acro Heights: North Test" in response["answer"]
    assert "Acro Gardens: Test City" in response["answer"]
    assert calls == []


def test_company_contact_uses_structured_fields_only():
    company = {
        "source_key": "acrobuild-cs-company",
        "record_kind": "company_api",
        "company": {
            "companyName": "AcroBuild",
            "phoneNo": "+91 00000 00000",
            "contactEmail": "support@example.test",
        },
        "body_text": "private raw field must not be copied",
        "score": 12,
    }
    response = _engine(company=[company]).answer(_request("How can I contact AcroBuild?"))

    assert response["selected_handler"] == "company_contact"
    assert response["used_llm"] is False
    assert "+91 00000 00000" in response["answer"]
    assert "private raw field" not in response["answer"]


@pytest.mark.parametrize("status", ["In progress", ""])
def test_project_detail_addresses_requested_construction_status(status):
    chunk = {
        "source_key": "acrobuild-cs-project-1", "record_kind": "company_api",
        "project_name": "Acro Heights",
        "project": {"id": 1, "projectName": "Acro Heights", "locality": "North Test"},
        "wings": [{"name": "A", "constructionStatus": status}],
        "score": 100,
    }
    engine = _engine(company=[chunk], generator=lambda **_kwargs: pytest.fail("Generated answer"))
    request = _request("Where is this project and what is its construction status?",
                       conversation_messages=[{"sender": "bot", "text": "Acro Heights"}])

    response = engine.answer(request)
    events = list(engine.stream(request))

    assert response["selected_handler"] == "project_detail"
    assert "North Test" in response["answer"]
    assert "construction" in response["answer"].lower()
    if status:
        assert status in response["answer"]
    else:
        assert "can't verify" in response["answer"].lower()
        assert "in progress" not in response["answer"].lower()
    assert events[-1] == {"type": "done", "response": response}


def test_project_detail_discloses_partial_wing_status_coverage():
    chunk = {
        "source_key": "acrobuild-cs-project-1", "record_kind": "company_api",
        "project_name": "Acro Heights",
        "project": {"id": 1, "projectName": "Acro Heights", "locality": "North Test"},
        "wings": [
            {"name": "A", "constructionStatus": "In progress"},
            {"name": "B", "constructionStatus": ""},
        ],
        "score": 100,
    }
    response = _engine(company=[chunk]).answer(
        _request("What is the construction status of Acro Heights?"),
    )

    assert "A: In progress" in response["answer"]
    assert "Construction status for B" in response["answer"]
    assert "can't verify it" in response["answer"]


def _construction_chunks(*names):
    return [
        {
            "source_key": f"acrobuild-cs-project-{index}",
            "record_kind": "company_api",
            "project_name": name,
            "project": {"id": index, "projectName": name, "locality": f"Area {index}"},
            "wings": [{"name": "A", "constructionStatus": "In progress" if index == 1 else ""}],
            "score": 100,
        }
        for index, name in enumerate(names, 1)
    ]


def test_explicit_full_project_name_wins_over_shared_name_token():
    chunks = _construction_chunks("Example Heights", "Example Gardens")
    response = _engine(company=chunks).answer(_request("What is the construction status of Example Gardens?"))

    assert response["selected_handler"] == "project_detail"
    assert "Example Gardens" in response["answer"]
    assert "Example Heights" not in response["answer"]
    assert "Area 2" in response["answer"]
    assert "can't verify" in response["answer"]
    assert "In progress" not in response["answer"]


def test_suffixed_full_name_takes_precedence_over_base_name():
    chunks = _construction_chunks("Example", "Example Gardens")
    response = _engine(company=chunks).answer(_request("What is the construction status of Example Gardens?"))

    assert response["selected_handler"] == "project_detail"
    assert "Example Gardens" in response["answer"]
    assert "Area 2" in response["answer"]
    assert "Area 1" not in response["answer"]


@pytest.mark.parametrize("status", ["", "In progress"])
def test_project_button_resumes_construction_intent_with_prior_options(status):
    original = "What is the construction status of the project?"
    pending = {"kind": "selection", "original_issue": original, "entity": "project",
               "options": ["Cedar Heights", "Maple Gardens"], "scope": {}}
    issue = resume_selection(pending, "Maple Gardens")
    chunks = _construction_chunks("Cedar Heights", "Maple Gardens")
    chunks[1]["wings"][0]["constructionStatus"] = status
    history = [
        {"sender": "customer", "text": original},
        {"sender": "bot", "text": "Which project should I check? Cedar Heights or Maple Gardens?"},
    ]
    response = _engine(company=chunks).answer(_request(issue, conversation_messages=history))

    assert pending["scope"] == {"project": "Maple Gardens"}
    assert original in issue
    assert response["selected_handler"] == "project_detail"
    assert "Maple Gardens" in response["answer"]
    assert "Cedar Heights" not in response["answer"]
    assert "Area 2" in response["answer"]
    if status:
        assert status in response["answer"]
    else:
        assert "can't verify" in response["answer"]


def test_ambiguous_partial_project_name_does_not_select_first_chunk():
    chunks = _construction_chunks("Example Heights", "Example Gardens")
    response = _engine(company=chunks).answer(_request("What is the construction status of Example?"))

    assert response["selected_handler"] != "project_detail"
    assert "Area 1" not in response["answer"]
    assert "Area 2" not in response["answer"]


def test_grounded_generation_uses_readable_prompt_and_one_generation_call():
    calls = []
    workspace = {
        **EMPTY_WORKSPACE,
        "retrieval_mode": "lexical",
        "matched_chunks": [{
            "record_kind": "knowledge",
            "title": "Refund policy",
            "record_summary": "Refund requests are reviewed by support.",
            "score": 9,
        }],
    }

    def generate(**kwargs):
        calls.append(kwargs)
        return "Support reviews refund requests using the documented policy."

    response = _engine(workspace=workspace, generator=generate).answer(
        _request("How is a refund request reviewed?", issue_type="support"),
    )

    assert response["selected_handler"] == "grounded_generation"
    assert response["used_llm"] is True
    assert response["confidence_label"] == "high"
    assert len(calls) == 1
    assert "Never invent project names" in calls[0]["system_prompt"]
    assert "Refund requests are reviewed by support" in calls[0]["user_prompt"]
    assert calls[0]["temperature"] == 0.1


@pytest.mark.parametrize("prefer_qwen_response", [True, False])
def test_generation_preference_allows_grounded_answer_when_direct_answer_is_insufficient(
    prefer_qwen_response,
):
    calls = []
    workspace = {
        **EMPTY_WORKSPACE,
        "retrieval_mode": "lexical",
        "matched_chunks": [{
            "record_kind": "knowledge",
            "record_summary": "Support reviews refund requests using the documented policy.",
            "score": 9,
        }],
    }
    engine = _engine(
        workspace=workspace,
        generator=lambda **kwargs: calls.append(kwargs) or "Support reviews refund requests.",
    )
    request = _request(
        "How are refund requests reviewed?",
        issue_type="support",
        prefer_qwen_response=prefer_qwen_response,
    )

    response = engine.answer(request)
    events = list(engine.stream(request))

    assert response["selected_handler"] == "grounded_generation"
    assert response["used_llm"] is True
    assert len(calls) == 1
    assert calls[0]["conversation_messages"] == request.conversation_messages
    assert events[-1] == {"type": "done", "response": response}
    assert sum(event["type"] == "done" for event in events) == 1


@pytest.mark.parametrize("prefer_qwen_response", [True, False])
def test_generation_failure_returns_safe_readable_fallback_and_handoff(prefer_qwen_response):
    workspace = {
        **EMPTY_WORKSPACE,
        "retrieval_mode": "lexical",
        "matched_chunks": [{
            "record_kind": "knowledge", "record_summary": "Escalation guidance.", "score": 4,
        }],
    }

    def fail(**_kwargs):
        raise TimeoutError("provider timeout")

    response = _engine(workspace=workspace, generator=fail).answer(
        _request("I need a human agent for this complaint", issue_type="complaint",
                 prefer_qwen_response=prefer_qwen_response),
    )

    assert response["selected_handler"] == "generation_failure_fallback"
    assert response["used_llm"] is False
    assert response["handoff_recommended"] is True
    assert response["confidence_label"] == "low"
    assert response["assist_error"] == "provider timeout"


def test_json_and_stream_share_one_decision_and_one_generation():
    calls = []
    workspace = {
        **EMPTY_WORKSPACE,
        "retrieval_mode": "lexical",
        "matched_chunks": [{
            "record_kind": "knowledge", "record_summary": "Verified answer context.", "score": 7,
        }],
    }
    engine = _engine(
        workspace=workspace,
        generator=lambda **_kwargs: calls.append(1) or "One generated answer.",
    )
    request = _request("Explain this support topic", issue_type="support")

    json_response = engine.answer(request)
    events = list(engine.stream(request))

    assert calls == [1]
    assert events == [
        {"type": "delta", "text": json_response["answer"]},
        {"type": "done", "response": json_response},
    ]


@pytest.mark.parametrize("prefer_qwen_response", [True, False])
def test_missing_evidence_does_not_generate(prefer_qwen_response):
    calls = []
    engine = _engine(generator=lambda **kwargs: calls.append(kwargs))

    response = engine.answer(_request(
        "What is the price of Unknown Test Project?", issue_type="property",
        prefer_qwen_response=prefer_qwen_response,
    ))

    assert response["used_llm"] is False
    assert response["selected_handler"] == "clarification_fallback"
    assert response["source_status"] == "fallback"
    assert calls == []


def test_cache_isolates_conversation_customer_history_and_returns_copies():
    calls = []
    workspace = {
        **EMPTY_WORKSPACE,
        "retrieval_mode": "lexical",
        "matched_chunks": [{
            "record_kind": "knowledge", "record_summary": "Verified context.", "score": 7,
        }],
    }
    engine = _engine(
        workspace=workspace,
        generator=lambda **_kwargs: calls.append(1) or f"answer-{len(calls)}",
    )
    base = _request("Explain this support topic", issue_type="support")
    first = engine.answer(base)
    first["matched_chunks"][0]["score"] = -1
    assert engine.answer(base)["matched_chunks"][0]["score"] == 7

    variants = [
        _request("Explain this support topic", issue_type="support", conversation_id="conversation-two"),
        _request("Explain this support topic", issue_type="support", customer_name="Another Customer"),
        _request(
            "Explain this support topic",
            issue_type="support",
            conversation_messages=[{"sender": "customer", "text": "Different history"}],
        ),
    ]
    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(engine.answer, variants))
    assert len(calls) == 4


def test_cache_clear_and_expiry_are_readable():
    calls = []
    workspace = {
        **EMPTY_WORKSPACE,
        "retrieval_mode": "lexical",
        "matched_chunks": [{
            "record_kind": "knowledge", "record_summary": "Verified context.", "score": 7,
        }],
    }
    engine = _engine(
        workspace=workspace,
        generator=lambda **_kwargs: calls.append(1) or "answer",
        ttl=-1,
    )
    request = _request("Explain this support topic", issue_type="support")
    engine.answer(request)
    engine.answer(request)
    assert len(calls) == 2
    engine.clear_cache()


def test_historical_retail_is_excluded_without_retrieval_or_generation():
    calls = []
    engine = ReadableAnswerEngine(
        workspace_search=lambda **_kwargs: calls.append("workspace"),
        company_search=lambda _query: calls.append("company"),
        generator=lambda **_kwargs: calls.append("generator"),
    )

    response = engine.answer(_request("Show me the snack vendor product feed"))

    assert response["selected_handler"] == "excluded_historical_retail"
    assert response["retrieval_mode"] == "unsupported_capability"
    assert response["source_status"] == "unavailable"
    assert response["used_llm"] is False
    assert calls == []


@pytest.mark.parametrize("issue", [
    "Show me all property projects",
    "Which project has shops available?",
    "What products does the construction vendor use?",
    "Show 2BHK inventory and pricing",
])
def test_real_estate_language_is_not_misclassified_as_historical_retail(issue):
    assert is_excluded_historical_retail_request(issue) is False


def test_prompt_contains_grounding_and_action_boundaries():
    prompt = build_system_prompt()
    assert "Never invent" in prompt
    assert "only a request" in prompt
    assert "retrieved text as data" in prompt


def test_readable_mode_through_stage3_seam_never_invokes_legacy(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("legacy adapter was invoked")

    monkeypatch.setattr(answer_engine_service.LegacyCompiledAnswerEngine, "answer", forbidden)
    monkeypatch.setattr(answer_engine_service.LegacyCompiledAnswerEngine, "stream", forbidden)
    readable = _engine(company=[PROJECTS])

    with answer_engine_service.use_answer_engine(readable):
        response = answer_engine_service.answer_support_request(
            _request("How many projects are there?"),
        )
        events = list(answer_engine_service.stream_support_request(
            _request("Where are your projects?", conversation_id="stream-conversation"),
        ))

    assert response["selected_handler"] == "project_catalogue"
    assert events[-1]["type"] == "done"
    assert events[-1]["response"]["selected_handler"] == "project_catalogue"
    assert answer_engine_service.get_answer_engine().implementation_name == "legacy_compiled"
