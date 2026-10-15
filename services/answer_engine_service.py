"""Readable integration boundary for support answer generation.

The compiled answer engine remains production-selected for rollback. Stage 4
adds an independently executable readable implementation while keeping backend
selection explicit and testable at this boundary.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from time import monotonic
from typing import Any, Iterator, Protocol, TypedDict

from services.observability import get_logger, kv
from services.readable_answer_engine import ReadableAnswerEngine


answer_engine_logger = get_logger("answer_engine")
_CONVERSATION_SCOPE: ContextVar[str] = ContextVar("answer_engine_conversation_scope", default="")

LEGACY_COMPILED_RESPONSIBILITIES = (
    "retrieval_assembly",
    "response_cache_keying_and_storage",
    "deterministic_answer_selection",
    "prompt_construction",
    "llm_generation",
    "confidence_and_handoff_policy",
    "response_and_stream_event_assembly",
)


class AnswerEngineEvent(TypedDict, total=False):
    type: str
    stage: str
    text: str
    response: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AnswerEngineRequest:
    issue: str
    conversation_id: str = ""
    customer_name: str = ""
    customer_email: str = ""
    business_hours_tag: str = ""
    issue_type: str = ""
    article_hint_url: str = ""
    conversation_messages: list[dict[str, Any]] | None = None
    limit: int = 3
    prefer_fast_response: bool = False
    prefer_qwen_response: bool = True

    def legacy_kwargs(self) -> dict[str, Any]:
        """Return the exact keyword contract accepted by the compiled engine."""
        return {
            "issue": self.issue,
            "customer_name": self.customer_name,
            "customer_email": self.customer_email,
            "business_hours_tag": self.business_hours_tag,
            "issue_type": self.issue_type,
            "article_hint_url": self.article_hint_url,
            "conversation_messages": self.conversation_messages,
            "limit": self.limit,
            "prefer_fast_response": self.prefer_fast_response,
            "prefer_qwen_response": self.prefer_qwen_response,
        }


class AnswerEngineBackend(Protocol):
    implementation_name: str

    def answer(self, request: AnswerEngineRequest) -> dict[str, Any]: ...

    def stream(self, request: AnswerEngineRequest) -> Iterator[AnswerEngineEvent]: ...

    def clear_cache(self) -> None: ...


class LegacyCompiledAnswerEngine:
    """Temporary adapter around the current Python 3.12 compiled runtime."""

    implementation_name = "legacy_compiled"

    def answer(self, request: AnswerEngineRequest) -> dict[str, Any]:
        from services import ai_agent_service as legacy_answer_engine

        with legacy_answer_engine.assist_cache_scope(
            customer_name=request.customer_name,
            conversation_id=request.conversation_id,
        ):
            return legacy_answer_engine.build_ai_support_answer(**request.legacy_kwargs())

    def stream(self, request: AnswerEngineRequest) -> Iterator[AnswerEngineEvent]:
        from services import ai_agent_service as legacy_answer_engine

        with legacy_answer_engine.assist_cache_scope(
            customer_name=request.customer_name,
            conversation_id=request.conversation_id,
        ):
            yield from legacy_answer_engine.stream_ai_support_answer_events(**request.legacy_kwargs())

    def clear_cache(self) -> None:
        from services import ai_agent_service as legacy_answer_engine

        legacy_answer_engine.clear_assist_response_cache()


_ACTIVE_ANSWER_ENGINE: AnswerEngineBackend = LegacyCompiledAnswerEngine()
READABLE_ANSWER_ENGINE: AnswerEngineBackend = ReadableAnswerEngine()
_SCOPED_ANSWER_ENGINE: ContextVar[AnswerEngineBackend | None] = ContextVar(
    "scoped_answer_engine", default=None,
)


def get_answer_engine() -> AnswerEngineBackend:
    """Return the production-selected backend (legacy until cutover approval)."""
    return _SCOPED_ANSWER_ENGINE.get() or _ACTIVE_ANSWER_ENGINE


@contextmanager
def use_answer_engine(backend: AnswerEngineBackend):
    """Temporarily select a backend for isolated tests and characterization."""
    token = _SCOPED_ANSWER_ENGINE.set(backend)
    try:
        yield backend
    finally:
        _SCOPED_ANSWER_ENGINE.reset(token)


@contextmanager
def answer_engine_conversation_scope(conversation_id: str):
    """Attach server-side conversation scope without changing public signatures."""
    token = _CONVERSATION_SCOPE.set(str(conversation_id or ""))
    try:
        yield
    finally:
        _CONVERSATION_SCOPE.reset(token)


def _completion_fields(response: object) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {"response_type": type(response).__name__}
    return {
        "source_status": response.get("source_status"),
        "retrieval_mode": response.get("retrieval_mode"),
        "used_llm": response.get("used_llm"),
        "confidence": response.get("confidence_label"),
        "handoff": response.get("handoff_recommended"),
        "agent_mode": response.get("agent_mode"),
    }


def answer_support_request(request: AnswerEngineRequest) -> dict[str, Any]:
    """Execute one non-streaming request without altering legacy behavior."""
    engine = get_answer_engine()
    started = monotonic()
    answer_engine_logger.info(
        "answer engine started %s",
        kv(implementation=engine.implementation_name, delivery="json"),
    )
    try:
        response = engine.answer(request)
    except Exception as error:
        answer_engine_logger.error(
            "answer engine failed %s",
            kv(
                implementation=engine.implementation_name,
                delivery="json",
                error_category=type(error).__name__,
                duration_ms=round((monotonic() - started) * 1000),
            ),
        )
        raise
    answer_engine_logger.info(
        "answer engine completed %s",
        kv(
            implementation=engine.implementation_name,
            delivery="json",
            duration_ms=round((monotonic() - started) * 1000),
            **_completion_fields(response),
        ),
    )
    return response


def stream_support_request(request: AnswerEngineRequest) -> Iterator[AnswerEngineEvent]:
    """Yield legacy events unchanged while tracing source-visible metadata."""
    engine = get_answer_engine()
    started = monotonic()
    event_count = 0
    terminal_count = 0
    terminal_response: object = None
    answer_engine_logger.info(
        "answer engine started %s",
        kv(implementation=engine.implementation_name, delivery="stream"),
    )
    try:
        for event in engine.stream(request):
            event_count += 1
            if event.get("type") == "done":
                terminal_count += 1
                terminal_response = event.get("response")
            yield event
    except GeneratorExit:
        answer_engine_logger.info(
            "answer engine stream closed %s",
            kv(
                implementation=engine.implementation_name,
                events=event_count,
                terminal_events=terminal_count,
                duration_ms=round((monotonic() - started) * 1000),
            ),
        )
        raise
    except Exception as error:
        answer_engine_logger.error(
            "answer engine failed %s",
            kv(
                implementation=engine.implementation_name,
                delivery="stream",
                error_category=type(error).__name__,
                events=event_count,
                terminal_events=terminal_count,
                duration_ms=round((monotonic() - started) * 1000),
            ),
        )
        raise
    answer_engine_logger.info(
        "answer engine completed %s",
        kv(
            implementation=engine.implementation_name,
            delivery="stream",
            events=event_count,
            terminal_events=terminal_count,
            duration_ms=round((monotonic() - started) * 1000),
            **_completion_fields(terminal_response),
        ),
    )


def clear_answer_cache() -> None:
    """Invalidate the cache owned by the active backend."""
    engine = get_answer_engine()
    engine.clear_cache()
    answer_engine_logger.info(
        "answer engine cache cleared %s",
        kv(implementation=engine.implementation_name, cache_owner=engine.implementation_name),
    )


# Compatibility call signatures used by current orchestration and imports.
def build_ai_support_answer(
    issue,
    customer_name="",
    customer_email="",
    business_hours_tag="",
    issue_type="",
    article_hint_url="",
    conversation_messages=None,
    limit=3,
    prefer_fast_response=False,
    prefer_qwen_response=True,
):
    return answer_support_request(AnswerEngineRequest(
        issue=issue,
        conversation_id=_CONVERSATION_SCOPE.get(),
        customer_name=customer_name,
        customer_email=customer_email,
        business_hours_tag=business_hours_tag,
        issue_type=issue_type,
        article_hint_url=article_hint_url,
        conversation_messages=conversation_messages,
        limit=limit,
        prefer_fast_response=prefer_fast_response,
        prefer_qwen_response=prefer_qwen_response,
    ))


def stream_ai_support_answer_events(
    issue,
    customer_name="",
    customer_email="",
    business_hours_tag="",
    issue_type="",
    article_hint_url="",
    conversation_messages=None,
    limit=3,
    prefer_fast_response=False,
    prefer_qwen_response=True,
):
    yield from stream_support_request(AnswerEngineRequest(
        issue=issue,
        conversation_id=_CONVERSATION_SCOPE.get(),
        customer_name=customer_name,
        customer_email=customer_email,
        business_hours_tag=business_hours_tag,
        issue_type=issue_type,
        article_hint_url=article_hint_url,
        conversation_messages=conversation_messages,
        limit=limit,
        prefer_fast_response=prefer_fast_response,
        prefer_qwen_response=prefer_qwen_response,
    ))


def clear_assist_response_cache() -> None:
    clear_answer_cache()
