"""Local socket probe of the real NDJSON route with synthetic, action-free events."""
from __future__ import annotations

import json
import socket
from threading import Event, Thread
from time import sleep
from unittest.mock import patch

import httpx
import uvicorn

from app import api
from graph import main_orchestrator
from graph.main_orchestrator import TurnContext
from routers import assist
from services.turn_analysis_service import TurnAnalysis


def run():
    closed = Event()
    trace_closed = Event()
    blocked_entered = Event()
    blocked_release = Event()
    blocked_closed = Event()
    blocked_terminal_reached = Event()
    bulk_closed = Event()
    bulk_complete_closed = Event()
    bulk_produced = []
    started = []
    original_stream = assist.stream_support_orchestration_events
    saved = []
    issue = "Explain the synthetic support policy"
    turn = TurnContext(
        conversation_messages=[], resolved_issue=issue, property_issue=issue,
        analysis=TurnAnalysis("general", "English", "latin", "stage5_socket_synthetic"),
    )

    class Session:
        def __init__(self, _cookie, conversation_id):
            self.conversation_id = conversation_id

        def load(self):
            return []

        def set_cookie(self, *_args):
            pass

        def append(self, customer_issue, answer, marker=""):
            saved.append((self.conversation_id, customer_issue, answer))

    def blocked_provider(**_kwargs):
        try:
            yield "Synthetic first chunk."
            blocked_entered.set()
            blocked_release.wait(3)
            yield "Synthetic second chunk."
            blocked_terminal_reached.set()
        finally:
            blocked_closed.set()

    def events(**kwargs):
        conversation_id = kwargs.get("conversation_id")
        started.append(conversation_id)
        try:
            if conversation_id == "stage5-blocked":
                yield from original_stream(**kwargs)
                return
            if conversation_id == "stage5-bulk":
                for index in range(512):
                    bulk_produced.append(index)
                    yield {"type": "delta", "text": "x" * 32768}
                yield {"type": "done", "response": {"answer": "Synthetic bulk complete.",
                                                   "source_status": "workspace", "used_llm": False}}
                return
            if conversation_id == "stage5-bulk-complete":
                for _ in range(128):
                    yield {"type": "delta", "text": "x" * 8192}
                yield {"type": "done", "response": {"answer": "Synthetic bulk complete.",
                                                   "source_status": "workspace", "used_llm": False}}
                return
            yield {"type": "delta", "text": "Synthetic support response. "}
            sleep(0.25)
            yield {"type": "delta", "text": "No customer action."}
            yield {"type": "done", "response": {"answer": "Synthetic support response. No customer action.",
                                                 "source_status": "workspace", "used_llm": False}}
        finally:
            closed.set()
            if conversation_id == "stage5-bulk":
                bulk_closed.set()
            if conversation_id == "stage5-bulk-complete":
                bulk_complete_closed.set()

    original_end_data_api_trace = assist.end_data_api_trace

    def end_trace(token):
        original_end_data_api_trace(token)
        trace_closed.set()

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(api, lifespan="off", log_level="error"))
    thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    patches = (
        patch.object(assist, "ConversationSession", Session),
        patch.object(assist, "_prepare_lookup_turn",
                     side_effect=lambda request, *_args, **_kwargs: (None, request, issue, turn)),
        patch.object(assist, "_grounded_property_shortcut", return_value=None),
        patch.object(assist, "_is_broad_project_request", return_value=False),
        patch.object(assist, "stream_support_orchestration_events", side_effect=events),
        patch.object(main_orchestrator, "_grounded_general_answer", return_value=None),
        patch.object(main_orchestrator, "stream_qwen_chat_response", side_effect=blocked_provider),
        patch.object(assist, "_complete_payload", side_effect=lambda payload, *_args: payload),
        patch.object(assist, "end_data_api_trace", side_effect=end_trace),
    )
    for item in patches:
        item.start()
    try:
        thread.start()
        for _ in range(100):
            if server.started:
                break
            sleep(0.02)
        if not server.started:
            raise RuntimeError("Local Uvicorn server did not start")
        with httpx.Client(timeout=5, trust_env=False) as client:
            with client.stream("POST", f"http://127.0.0.1:{port}/api/support/assist/stream",
                               json={"issue": issue, "conversation_id": "stage5-socket"}) as response:
                lines = []
                for line in response.iter_lines():
                    if line:
                        lines.append(json.loads(line))
                        sleep(0.1)
                if response.status_code != 200:
                    raise RuntimeError(f"Stream returned HTTP {response.status_code}")
        if [line["type"] for line in lines] != ["delta", "delta", "done"]:
            raise RuntimeError("Completed socket stream event sequence changed")
        if not closed.wait(2):
            raise RuntimeError("Completed stream did not close its generator")
        closed.clear()
        trace_closed.clear()
        with httpx.Client(timeout=5, trust_env=False) as client:
            with client.stream("POST", f"http://127.0.0.1:{port}/api/support/assist/stream",
                               json={"issue": issue, "conversation_id": "stage5-disconnect"}) as response:
                first = next(line for line in response.iter_lines() if line)
                if json.loads(first).get("type") != "delta":
                    raise RuntimeError("Disconnect probe did not receive its first delta")
            # Closing the response closes the socket before the next synthetic event.
        disconnect_cleanup = closed.wait(2)
        disconnect_trace_cleanup = trace_closed.wait(0.1)
        trace_closed.clear()
        with httpx.Client(timeout=5, trust_env=False) as client:
            with client.stream("POST", f"http://127.0.0.1:{port}/api/support/assist/stream",
                               json={"issue": issue, "conversation_id": "stage5-blocked"}) as response:
                next(line for line in response.iter_lines()
                     if line and json.loads(line).get("type") == "delta")
                if not blocked_entered.wait(2):
                    raise RuntimeError("Blocked provider probe did not enter the call")
        blocked_closed_before_release = blocked_closed.wait(0.1)
        blocked_release.set()
        blocked_cleanup = blocked_closed.wait(2)
        blocked_trace_cleanup = trace_closed.wait(0.1)
        trace_closed.clear()
        with httpx.Client(timeout=10, trust_env=False) as client:
            with client.stream("POST", f"http://127.0.0.1:{port}/api/support/assist/stream",
                               json={"issue": issue, "conversation_id": "stage5-bulk"}) as response:
                first = next(line for line in response.iter_lines() if line)
                if json.loads(first).get("type") != "delta":
                    raise RuntimeError("Bulk probe did not receive a delta")
                with httpx.Client(timeout=5, trust_env=False) as concurrent_client:
                    with concurrent_client.stream(
                        "POST", f"http://127.0.0.1:{port}/api/support/assist/stream",
                        json={"issue": issue, "conversation_id": "stage5-concurrent"},
                    ) as concurrent_response:
                        concurrent_types = [json.loads(line)["type"] for line in concurrent_response.iter_lines() if line]
                sleep(0.3)
                produced_while_paused = len(bulk_produced)
        bulk_cleanup = bulk_closed.wait(2)
        bulk_trace_cleanup = trace_closed.wait(0.1)
        with httpx.Client(timeout=10, trust_env=False) as client:
            with client.stream("POST", f"http://127.0.0.1:{port}/api/support/assist/stream",
                               json={"issue": issue, "conversation_id": "stage5-bulk-complete"}) as response:
                completed_bulk_types = []
                for line in response.iter_lines():
                    if line:
                        completed_bulk_types.append(json.loads(line)["type"])
                        sleep(0.005)
        completed_bulk_cleanup = bulk_complete_closed.wait(2)
        return {"evidence_class": "local_socket_synthetic", "terminal_count": 1,
                "event_types": [line["type"] for line in lines], "persisted_turns": len(saved),
                "persisted_conversations": [row[0] for row in saved],
                "generation_starts": started,
                "concurrent_event_types": concurrent_types,
                "normal_generator_cleanup": True, "disconnect_generator_cleanup": disconnect_cleanup,
                "disconnect_trace_cleanup": disconnect_trace_cleanup,
                "slow_reader_delay_ms_per_line": 100,
                "blocked_closed_before_release": blocked_closed_before_release,
                "blocked_generator_cleanup": blocked_cleanup,
                "blocked_trace_cleanup": blocked_trace_cleanup,
                "blocked_terminal_reached": blocked_terminal_reached.is_set(),
                "bulk_events_produced_while_reader_paused": produced_while_paused,
                "bulk_total_events": 512, "bulk_generator_cleanup": bulk_cleanup,
                "bulk_trace_cleanup": bulk_trace_cleanup,
                "completed_bulk_delta_count": completed_bulk_types.count("delta"),
                "completed_bulk_terminal_count": completed_bulk_types.count("done"),
                "completed_bulk_generator_cleanup": completed_bulk_cleanup}
    finally:
        blocked_release.set()
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()
        for item in reversed(patches):
            item.stop()


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
