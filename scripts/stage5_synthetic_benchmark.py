"""Comparable offline answer-engine timings; no network or customer data."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import statistics
import subprocess
import sys
from time import perf_counter
from unittest.mock import patch

from scripts.stage5_differential_check import DETAIL, PROJECTS, WORKSPACE
from services import ai_agent_service as legacy_module
from services.answer_engine_service import AnswerEngineRequest, LegacyCompiledAnswerEngine
from services.readable_answer_engine import ReadableAnswerEngine


def _timed(call):
    start = perf_counter()
    value = call()
    return value, (perf_counter() - start) * 1000


def _percentiles(values):
    ordered = sorted(values)
    return {
        "p50_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[max(0, int(len(ordered) * .95 + .999) - 1)], 3),
    }


def _measure(engine, count):
    miss, hit, first_delta, completion = [], [], [], []
    for index in range(count):
        request = AnswerEngineRequest(issue=f"Where is Example Heights located? {index}",
                                      conversation_id=f"synthetic-{index}")
        engine.clear_cache()
        _, elapsed = _timed(lambda: engine.answer(request))
        miss.append(elapsed)
        _, elapsed = _timed(lambda: engine.answer(request))
        hit.append(elapsed)
        engine.clear_cache()
        started = perf_counter()
        events = engine.stream(request)
        first = None
        for event in events:
            elapsed = (perf_counter() - started) * 1000
            if event.get("type") == "delta" and first is None:
                first = elapsed
            if event.get("type") == "done":
                completion.append(elapsed)
        if first is not None:
            first_delta.append(first)

    engine.clear_cache()
    def concurrent(index):
        request = AnswerEngineRequest(issue=f"Tell me about Example Heights {index}",
                                      conversation_id=f"parallel-{index}")
        response = engine.answer(request)
        return bool(response.get("answer"))

    started = perf_counter()
    with ThreadPoolExecutor(max_workers=8) as pool:
        successful = sum(pool.map(concurrent, range(32)))
    concurrency_ms = (perf_counter() - started) * 1000
    return {
        "cache_miss": _percentiles(miss),
        "cache_hit": _percentiles(hit),
        "first_delta": _percentiles(first_delta),
        "stream_complete": _percentiles(completion),
        "concurrent_32_with_8_workers_ms": round(concurrency_ms, 3),
        "concurrent_successes": successful,
    }


def _cold_import(module_name, count=3):
    child = (
        "import importlib,json,time,tracemalloc; "
        "tracemalloc.start(); start=time.perf_counter(); "
        f"importlib.import_module({module_name!r}); "
        "current,peak=tracemalloc.get_traced_memory(); "
        "print(json.dumps({'elapsed_ms':(time.perf_counter()-start)*1000,"
        "'peak_mib':peak/1048576}))"
    )
    samples = []
    for _ in range(count):
        result = subprocess.run([sys.executable, "-c", child], check=True, capture_output=True, text=True)
        samples.append(json.loads(result.stdout.strip()))
    return {
        "elapsed_ms": _percentiles([sample["elapsed_ms"] for sample in samples]),
        "peak_mib_median": round(statistics.median(sample["peak_mib"] for sample in samples), 3),
    }


def run_benchmark(count=30):
    legacy = LegacyCompiledAnswerEngine()
    readable = ReadableAnswerEngine(
        workspace_search=lambda **_kwargs: WORKSPACE,
        company_search=lambda _query: [PROJECTS, DETAIL],
        generator=lambda **_kwargs: "Synthetic support evidence was reviewed.",
    )
    patches = (
        patch.object(legacy_module, "search_workspace_knowledge", return_value=WORKSPACE),
        patch.object(legacy_module, "search_company_knowledge", return_value=[PROJECTS, DETAIL]),
        patch.object(legacy_module, "get_company_projects", return_value=[]),
        patch.object(legacy_module, "get_customer_context", return_value={}),
        patch.object(legacy_module, "generate_qwen_chat_response",
                     return_value="Synthetic support evidence was reviewed."),
    )
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        return {
            "evidence_class": "synthetic_mocked_local_benchmark",
            "method": "same constructed source records; 30 sequential unique requests per mode; "
                      "32 concurrent unique requests on 8 threads; process already warm; "
                      "cold imports in 3 fresh processes per module",
            "iterations": count,
            "cold_import": {
                "readable_interface": _cold_import("services.answer_engine_service"),
                "legacy_module": _cold_import("services.ai_agent_service"),
            },
            "legacy": _measure(legacy, count),
            "readable": _measure(readable, count),
        }


if __name__ == "__main__":
    print(json.dumps(run_benchmark(), indent=2, sort_keys=True))
