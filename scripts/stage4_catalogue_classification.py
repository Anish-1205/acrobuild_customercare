"""Classify legacy catalogue-named runtime helpers without executing them.

This is static evidence only.  It reads code-object names from the preserved
runtime and separates the retail-specific family from explicitly protected
real-estate catalogue behavior.
"""
from __future__ import annotations

import json
import marshal
from pathlib import Path
import types


ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "services" / "ai_agent_service_runtime.patched.pyc"

RETAIL_NAME_MARKERS = ("catalog", "local_product", "product", "snack")
PROTECTED_REAL_ESTATE_FUNCTIONS = {
    "build_company_api_direct_answer",
    "build_construction_update_answer",
    "build_project_location_answer",
    "format_floor_location",
    "has_global_project_scope",
    "is_cross_project_flat_count_comparison_request",
    "is_cross_project_floor_comparison_request",
    "is_highest_property_value_request",
    "is_lowest_property_value_request",
    "is_price_question",
    "mentions_wing_reference",
    "normalize_floor_number",
}
STAGE0_OBSERVED_RETAIL_CHECKS = {
    "build_catalog_guidance_line",
    "build_local_product_feed_guidance_line",
    "build_product_fact_guidance_line",
    "detect_catalog_query_kind",
    "extract_local_product_feed_key",
    "filter_catalog_products_for_issue",
    "get_local_product_feed_summary_from_chunks",
    "get_selected_local_product_feed_summary",
    "get_workspace_local_product_feed_keys",
    "is_local_product_feed_recommendation_question",
    "is_local_product_feed_source_name",
    "select_local_product_feed_key",
}


def classify_runtime_functions(runtime_path: Path = RUNTIME) -> dict:
    module_code = marshal.loads(runtime_path.read_bytes()[16:])
    names = {
        value.co_name
        for value in module_code.co_consts
        if isinstance(value, types.CodeType)
    }
    retail = sorted(
        name for name in names
        if any(marker in name for marker in RETAIL_NAME_MARKERS)
    )
    protected = sorted(names & PROTECTED_REAL_ESTATE_FUNCTIONS)
    return {
        "evidence_class": "static_code_object_inventory",
        "runtime": str(runtime_path.relative_to(ROOT)).replace("\\", "/"),
        "top_level_function_count": len(names),
        "confirmed_retail_name_count": len(retail),
        "confirmed_retail_names": retail,
        "stage0_observed_retail_check_count": len(STAGE0_OBSERVED_RETAIL_CHECKS & names),
        "stage0_observed_retail_checks": sorted(STAGE0_OBSERVED_RETAIL_CHECKS & names),
        "protected_real_estate_names": protected,
        "note": (
            "Name classification is supported by retail-only constants and the macros/soulara "
            "Shopify CSV schema documented in the Stage 4 report. It does not prove runtime reachability."
        ),
    }


def main() -> None:
    print(json.dumps(classify_runtime_functions(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
