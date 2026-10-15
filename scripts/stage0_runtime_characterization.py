"""Safe Stage 0 characterization of the compiled answer engine.

This command performs no network calls, database writes, tickets, callbacks, or
site-visit actions. It uses synthetic retrieval records and a stubbed LLM to:

* compute a conservative static function-name closure from production entry points;
* observe runtime-owned code objects reached by JSON-style and streaming calls;
* measure mocked cache-miss/cache-hit and stream event timings.

The output is JSON on stdout. Timings describe this workstation and synthetic
dependencies only; they are not live-service or production latency evidence.
"""
from __future__ import annotations

import json
import marshal
import statistics
import subprocess
import sys
import time
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "services" / "ai_agent_service_runtime.patched.pyc"
sys.path.insert(0, str(ROOT))

PRODUCTION_ENTRY_POINTS = {
    "answer_matches_response_language",
    "build_ai_support_answer",
    "clear_assist_response_cache",
    "localize_ai_answer",
    "stream_ai_support_answer_events",
}

SYNTHETIC_WORKSPACE_RESULT = {
    "articles": [],
    "embedding_error": "",
    "index_built_at": None,
    "index_error": "",
    "knowledge_documents": [],
    "matched_chunks": [],
    "retrieval_mode": "empty",
}

SYNTHETIC_PROJECT_CHUNK = {
    "source_key": "stage0-synthetic-projects",
    "record_kind": "company_api",
    "title": "Synthetic projects",
    "body_text": "Synthetic project record for Stage 0 characterization.",
    "project_names": ["Stage Zero Project"],
    "projects": [{"id": 900001, "projectName": "Stage Zero Project", "city": "Test City"}],
    "score": 100.0,
}


def _walk_code(code):
    yield code
    for value in code.co_consts:
        if isinstance(value, types.CodeType):
            yield from _walk_code(value)


def _runtime_code():
    raw = RUNTIME.read_bytes()
    return marshal.loads(raw[16:])


def _top_level_functions(module_code):
    return {
        value.co_name: value
        for value in module_code.co_consts
        if isinstance(value, types.CodeType)
    }


def _static_closure(functions):
    reached = set()
    pending = list(PRODUCTION_ENTRY_POINTS & functions.keys())
    while pending:
        name = pending.pop()
        if name in reached:
            continue
        reached.add(name)
        referenced_names = {
            dependency
            for code in _walk_code(functions[name])
            for dependency in code.co_names
        }
        pending.extend(
            dependency
            for dependency in referenced_names
            if dependency in functions and dependency not in reached
        )
    return reached


class RuntimeProfiler:
    def __init__(self, runtime_code_objects):
        self.runtime_code_objects = runtime_code_objects
        self.calls = []

    def __call__(self, frame, event, _arg):
        if event == "call" and frame.f_code in self.runtime_code_objects:
            self.calls.append(frame.f_code.co_name)


def _timed_call(callable_):
    started = time.perf_counter()
    value = callable_()
    return value, (time.perf_counter() - started) * 1000


def _cold_import_samples(iterations):
    child = (
        "import json,time,tracemalloc; "
        "tracemalloc.start(); started=time.perf_counter(); "
        "import services.ai_agent_service; "
        "current,peak=tracemalloc.get_traced_memory(); "
        "print(json.dumps({'elapsed_ms':(time.perf_counter()-started)*1000,"
        "'current_bytes':current,'peak_bytes':peak}))"
    )
    samples = []
    for _ in range(iterations):
        completed = subprocess.run(
            [sys.executable, "-c", child],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        samples.append(json.loads(completed.stdout.strip()))
    return samples


def run_characterization(iterations=5):
    import services.ai_agent_service as agent

    module_code = _runtime_code()
    functions = _top_level_functions(module_code)
    runtime_code_objects = set(_walk_code(module_code))
    static_reachable = _static_closure(functions)

    observed = set()
    miss_timings = []
    hit_timings = []
    stream_first_event_timings = []
    stream_first_delta_timings = []
    stream_done_timings = []
    stream_event_shapes = []

    patches = (
        patch.object(agent, "search_workspace_knowledge", return_value=SYNTHETIC_WORKSPACE_RESULT),
        patch.object(agent, "search_company_knowledge", return_value=[SYNTHETIC_PROJECT_CHUNK]),
        patch.object(agent, "get_company_projects", return_value=[]),
        patch.object(agent, "get_customer_context", return_value={}),
        patch.object(
            agent,
            "generate_qwen_chat_response",
            return_value="Stage Zero Project has synthetic characterization information.",
        ),
    )

    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        for index in range(iterations):
            issue = f"Tell me about Stage Zero Project characterization {index}"
            agent.clear_assist_response_cache()
            profiler = RuntimeProfiler(runtime_code_objects)
            sys.setprofile(profiler)
            try:
                _, miss_ms = _timed_call(lambda: agent.build_ai_support_answer(issue=issue))
                _, hit_ms = _timed_call(lambda: agent.build_ai_support_answer(issue=issue))
            finally:
                sys.setprofile(None)
            observed.update(profiler.calls)
            miss_timings.append(miss_ms)
            hit_timings.append(hit_ms)

        agent.clear_assist_response_cache()
        profiler = RuntimeProfiler(runtime_code_objects)
        stream_started = time.perf_counter()
        first_event_ms = None
        first_delta_ms = None
        done_ms = None
        event_types = []
        sys.setprofile(profiler)
        try:
            for event in agent.stream_ai_support_answer_events(
                issue="Tell me about Stage Zero Project streaming characterization",
            ):
                elapsed_ms = (time.perf_counter() - stream_started) * 1000
                event_type = str(event.get("type") or "")
                event_types.append(event_type)
                if first_event_ms is None:
                    first_event_ms = elapsed_ms
                if event_type == "delta" and first_delta_ms is None:
                    first_delta_ms = elapsed_ms
                if event_type == "done":
                    done_ms = elapsed_ms
        finally:
            sys.setprofile(None)
        observed.update(profiler.calls)
        stream_first_event_timings.append(first_event_ms)
        stream_first_delta_timings.append(first_delta_ms)
        stream_done_timings.append(done_ms)
        stream_event_shapes.append(event_types)

    cold_imports = _cold_import_samples(iterations)
    outside_static_closure = sorted(set(functions) - static_reachable)
    observed_top_level = sorted(observed & set(functions))
    return {
        "evidence_class": "mocked_synthetic_characterization",
        "runtime": str(RUNTIME.relative_to(ROOT)).replace("\\", "/"),
        "iterations": iterations,
        "static": {
            "top_level_function_count": len(functions),
            "production_entry_points": sorted(PRODUCTION_ENTRY_POINTS & set(functions)),
            "conservative_reachable_count": len(static_reachable),
            "conservative_reachable_functions": sorted(static_reachable),
            "outside_conservative_closure_count": len(outside_static_closure),
            "outside_conservative_closure": outside_static_closure,
        },
        "observed": {
            "runtime_top_level_count": len(observed_top_level),
            "runtime_top_level_functions": observed_top_level,
            "note": "Observed calls prove reachability only for these synthetic scenarios; absence is not proof of unreachability.",
        },
        "performance_ms": {
            "cold_import_median": round(statistics.median(
                sample["elapsed_ms"] for sample in cold_imports
            ), 3),
            "cold_import_samples": [
                round(sample["elapsed_ms"], 3) for sample in cold_imports
            ],
            "cold_import_tracemalloc_peak_median_mib": round(
                statistics.median(sample["peak_bytes"] for sample in cold_imports)
                / (1024 * 1024),
                3,
            ),
            "cache_miss_median": round(statistics.median(miss_timings), 3),
            "cache_miss_samples": [round(value, 3) for value in miss_timings],
            "cache_hit_median": round(statistics.median(hit_timings), 3),
            "cache_hit_samples": [round(value, 3) for value in hit_timings],
            "stream_first_event": round(stream_first_event_timings[0], 3),
            "stream_first_delta": (
                round(stream_first_delta_timings[0], 3)
                if stream_first_delta_timings[0] is not None else None
            ),
            "stream_done": round(stream_done_timings[0], 3) if stream_done_timings[0] is not None else None,
            "note": "Local Python/runtime overhead with stubbed retrieval and LLM; not live CS API, Sarvam, or production latency.",
        },
        "stream_event_types": stream_event_shapes[0],
    }


def main():
    print(json.dumps(run_characterization(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
