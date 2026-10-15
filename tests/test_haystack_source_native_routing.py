import importlib
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from graph import haystack_conversation_pipeline as pipeline
from graph.main_orchestrator import (
    TurnContext,
    run_support_orchestration,
    stream_support_orchestration_events,
)
from services.turn_analysis_service import TurnAnalysis


ROOT = Path(__file__).resolve().parent.parent


def _property_turn(issue):
    analysis = TurnAnalysis(
        intent="property",
        reply_language="English",
        script="latin",
        source="test",
        english=issue,
    )
    return TurnContext(
        conversation_messages=[{"sender": "customer", "text": issue}],
        resolved_issue=issue,
        analysis=analysis,
        property_issue=issue,
    )


def _wing_response():
    return {
        "agent_mode": "knowledge_retrieval",
        "answer": "The available options are A wing and B wing.",
        "confidence_label": "high",
        "source_label": "Test property source",
        "source_status": "live_api",
        "related_articles": [],
        "used_llm": False,
    }


def test_conversation_facade_is_a_normal_source_import_without_runtime_loader():
    facade_text = Path(pipeline.__file__).read_text(encoding="utf-8")

    assert pipeline._source.__file__.endswith("haystack_conversation_pipeline_source.py")
    assert "marshal" not in facade_text
    assert "exec(" not in facade_text
    assert "haystack_conversation_pipeline_runtime.pyc" not in facade_text


def test_clean_process_imports_application_without_haystack_or_runtime_blob():
    import_guard = """
import builtins

original_import = builtins.__import__

def reject_haystack(name, *args, **kwargs):
    if name == "haystack" or name.startswith("haystack."):
        raise AssertionError(f"unexpected Haystack import: {name}")
    return original_import(name, *args, **kwargs)

builtins.__import__ = reject_haystack
import app
import graph.haystack_conversation_pipeline
"""
    result = subprocess.run(
        [sys.executable, "-c", import_guard],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_source_and_requirements_have_no_haystack_framework_dependency():
    application_files = [ROOT / "app.py", ROOT / "api_context.py"]
    for directory in ("graph", "routers", "services"):
        application_files.extend((ROOT / directory).rglob("*.py"))

    for path in application_files:
        source_text = path.read_text(encoding="utf-8")
        assert not re.search(r"(?m)^\s*(?:from|import)\s+haystack\b", source_text), path
        assert "@component" not in source_text, path
        assert not re.search(r"\bPipeline\s*\(", source_text), path

    requirement_files = [ROOT / "requirements.txt", *(ROOT / "requirements").glob("*.txt")]
    for path in requirement_files:
        assert "haystack-ai" not in path.read_text(encoding="utf-8").casefold(), path


def test_native_pipeline_preserves_historical_input_and_output_shape():
    calls = []
    native_pipeline = pipeline.build_conversation_pipeline()

    result = native_pipeline.run({"orchestrator": {
        "issue": "show me the wings",
        "conversation_messages": [],
        "support_handler": lambda: calls.append("support") or _wing_response(),
    }})

    assert calls == ["support"]
    assert result == {"orchestrator": {"response": _wing_response()}}


def test_source_native_facade_remains_reloadable():
    reloaded = importlib.reload(pipeline)
    project_chunks = [{
        "source_key": "acrobuild-cs-projects",
        "project_names": ["Stage One Heights"],
        "body_text": "Stage One Heights is a test project.",
    }]

    with patch.object(reloaded, "search_company_knowledge", return_value=project_chunks):
        assert reloaded.matches_live_company_context("Tell me about Stage One Heights")


def test_plural_wings_routes_to_the_support_handler():
    calls = []

    response = pipeline.run_conversation_pipeline(
        issue="show me the wings",
        conversation_messages=[],
        support_handler=lambda: calls.append("support") or _wing_response(),
    )

    assert calls == ["support"]
    assert response["agent_mode"] == "knowledge_retrieval"


def test_opt_out_branch_remains_available_for_json_and_streaming_orchestration():
    issue = "show me the wings"
    turn = _property_turn(issue)

    with patch("graph.main_orchestrator.build_ai_support_answer", return_value=_wing_response()) as build:
        response = run_support_orchestration(
            issue,
            prefer_qwen_response=False,
            turn=turn,
        )
        events = list(stream_support_orchestration_events(
            issue,
            prefer_qwen_response=False,
            turn=turn,
        ))

    assert response["answer"] == _wing_response()["answer"]
    assert events[-1]["type"] == "done"
    assert events[-1]["response"]["answer"] == response["answer"]
    assert build.call_count == 2
