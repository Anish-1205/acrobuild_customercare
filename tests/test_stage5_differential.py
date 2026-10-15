"""Offline comparison gates for supported outcomes, with explicit exceptions."""
from scripts.stage5_differential_check import run_comparison


def test_constructed_differential_has_only_reviewed_difference_families():
    result = run_comparison()
    assert result["evidence_class"] == "constructed_synthetic_offline_differential"
    cases = {case["case"]: case for case in result["cases"]}
    assert len(cases) == 11
    assert all(case["legacy_terminal_count"] == case["readable_terminal_count"] == 1
               for case in cases.values())

    for case_id in (
        "project_catalogue", "project_location", "configuration_price", "inventory",
        "construction", "workspace", "contextual_followup",
    ):
        case = cases[case_id]
        assert case["different_fields"] == ["agent_mode"]
        assert case["classification"] == "legacy_implementation_defect_invalid_agent_mode"
        assert case["legacy"]["source_status"] == case["readable"]["source_status"]
        assert case["legacy"]["used_llm"] == case["readable"]["used_llm"] is False

    assert cases["opt_out"]["classification"] == "approved_generation_flag_parity_confidence_policy_difference"
    assert cases["opt_out"]["different_fields"] == ["confidence_label"]
    assert cases["opt_out"]["legacy"]["used_llm"] is True
    assert cases["opt_out"]["readable"]["used_llm"] is True
    assert cases["missing_data"]["classification"] == "approved_intentional_safe_fallback"
    assert cases["provider_timeout"]["classification"] == "semantically_equivalent_error_outcome"
    assert cases["retail_exclusion"]["classification"] == "approved_intentional_retail_exclusion"
