from scripts.stage4_catalogue_classification import classify_runtime_functions


def test_retail_and_real_estate_catalogue_families_are_separated():
    result = classify_runtime_functions()

    assert result["top_level_function_count"] == 152
    assert result["confirmed_retail_name_count"] == 57
    assert result["stage0_observed_retail_check_count"] == 12
    assert "build_local_product_feed_product_reply" in result["confirmed_retail_names"]
    assert "build_combined_products_and_snacks_line" in result["confirmed_retail_names"]
    assert "build_project_location_answer" in result["protected_real_estate_names"]
    assert "is_price_question" in result["protected_real_estate_names"]
    assert not set(result["confirmed_retail_names"]) & set(result["protected_real_estate_names"])
