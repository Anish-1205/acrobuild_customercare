from scripts import stage0_runtime_characterization as characterization
from scripts import verify_pipeline_reconstruction as verifier


def test_known_mismatch_families_are_named_without_treating_bytecode_as_truth():
    assert verifier._mismatch_family(
        "is_property_support_message",
        ("show me the wings",),
        ("ok", True),
        ("ok", False),
    ) == "property-term-boundary-routing"
    assert verifier._mismatch_family(
        "validate_support_answer",
        ("compare A and B", "A"),
        ("ok", []),
        ("ok", ["requested project"]),
    ) == "all-explicit-projects-required"
    assert verifier._mismatch_family(
        "validate_support_answer",
        ("how much is this", "answer"),
        ("ok", ["pricing"]),
        ("ok", []),
    ) == "property-scoped-pricing-guard"
    assert verifier._mismatch_family(
        "validate_support_node",
        ({"issue": "", "response": {"answer": ""}},),
        ("ok", {}),
        ("ok", {}),
    ) == "safe-relevance-fallback-copy"


def test_runtime_characterization_is_synthetic_and_covers_both_engine_entry_points():
    result = characterization.run_characterization(iterations=2)

    assert result["evidence_class"] == "mocked_synthetic_characterization"
    assert result["runtime"] == "services/ai_agent_service_runtime.patched.pyc"
    assert result["static"]["top_level_function_count"] == 152
    assert "build_ai_support_answer" in result["observed"]["runtime_top_level_functions"]
    assert "stream_ai_support_answer_events" in result["observed"]["runtime_top_level_functions"]
    assert result["stream_event_types"] == ["delta", "done"]
    assert len(result["performance_ms"]["cache_miss_samples"]) == 2
    assert len(result["performance_ms"]["cache_hit_samples"]) == 2
    assert len(result["performance_ms"]["cold_import_samples"]) == 2
