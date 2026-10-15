"""Provider failures must not expose low-level details in customer chat."""

from graph import main_orchestrator
from services.turn_analysis_service import TurnAnalysis


def test_general_provider_failure_is_safe_for_json_and_stream(monkeypatch):
    marker = "private-provider-host-and-token"

    def fail_json(**_kwargs):
        raise RuntimeError(marker)

    def fail_stream(**_kwargs):
        raise RuntimeError(marker)
        yield ""  # pragma: no cover

    monkeypatch.setattr(main_orchestrator, "generate_qwen_chat_response", fail_json)
    monkeypatch.setattr(main_orchestrator, "stream_qwen_chat_response", fail_stream)
    analysis = TurnAnalysis("general", "English", "latin", "synthetic")
    turn = main_orchestrator.TurnContext([], "Hello", analysis, "Hello")

    json_result = main_orchestrator.run_support_orchestration(
        "Hello", turn=turn, prefer_qwen_response=True,
    )
    events = list(main_orchestrator.stream_support_orchestration_events(
        "Hello", turn=turn, prefer_qwen_response=True,
    ))
    stream_result = events[-1]["response"]

    assert json_result["source_status"] == stream_result["source_status"] == "failed"
    assert json_result["answer"] == stream_result["answer"]
    assert json_result["assist_error"] == stream_result["assist_error"]
    assert json_result["assist_error"]
    assert [event["type"] for event in events] == ["route", "progress", "delta", "done"]
    assert events[-2]["text"] == stream_result["answer"]
    assert marker not in str(json_result)
    assert marker not in str(events)
