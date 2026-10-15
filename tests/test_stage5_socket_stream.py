"""Real loopback regression for completed and disconnected NDJSON streams."""
from scripts.stage5_socket_stream_check import run


def test_socket_disconnect_blocked_provider_and_bulk_backpressure():
    result = run()

    assert result["event_types"] == ["delta", "delta", "done"]
    assert result["terminal_count"] == 1
    assert result["persisted_turns"] == 3
    assert result["persisted_conversations"] == [
        "stage5-socket", "stage5-concurrent", "stage5-bulk-complete",
    ]
    assert result["generation_starts"] == [
        "stage5-socket", "stage5-disconnect", "stage5-blocked", "stage5-bulk", "stage5-concurrent",
        "stage5-bulk-complete",
    ]
    assert result["concurrent_event_types"] == ["delta", "delta", "done"]
    assert result["normal_generator_cleanup"] is True
    assert result["disconnect_generator_cleanup"] is True
    assert result["disconnect_trace_cleanup"] is True
    assert result["blocked_closed_before_release"] is False
    assert result["blocked_generator_cleanup"] is True
    assert result["blocked_trace_cleanup"] is True
    assert result["blocked_terminal_reached"] is False
    assert result["bulk_events_produced_while_reader_paused"] < result["bulk_total_events"]
    assert result["bulk_generator_cleanup"] is True
    assert result["bulk_trace_cleanup"] is True
    assert result["completed_bulk_delta_count"] == 128
    assert result["completed_bulk_terminal_count"] == 1
    assert result["completed_bulk_generator_cleanup"] is True
