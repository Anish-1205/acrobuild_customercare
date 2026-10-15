import pytest

from scripts.live_discovery_acceptance_checks import honesty_problems


def _turn(answer, kind="budget_question", source_status="live_api"):
    return {"answer": answer, "discovery_kind": kind, "source_status": source_status}


def test_neutral_all_prices_budget_question_is_not_a_property_price_claim():
    assert honesty_problems(_turn(
        "Do you have a budget limit, or should I include all prices?\n"
        "Feel free to type your budget in the chat (for example, INR 1.5 crore)."
    )) == []


def test_grounded_estimate_with_required_qualification_is_accepted():
    assert honesty_problems(_turn(
        "3BHK projects (estimated base amount):\n"
        "- Acro Iris: estimated base amount from INR 1.20 crore\n\n"
        "Estimated base amount = minimum listed rate x saleable area. "
        "It is a base estimate only and excludes taxes and registration.",
        kind="results",
    )) == []


@pytest.mark.parametrize("claim", [
    "The price is INR 90 lakh.",
    "Acro Iris costs INR 90 lakh.",
    "Acro Iris is priced at INR 90 lakh.",
    "Acro Iris is available for INR 90 lakh.",
])
def test_assertive_unsupported_property_price_claim_is_rejected(claim):
    assert "unsupported property price claim" in honesty_problems(_turn(claim, kind="locality_question"))


def test_unqualified_estimate_is_rejected():
    problems = honesty_problems(_turn(
        "3BHK projects (estimated base amount):\n"
        "- Acro Iris: estimated base amount from INR 1.20 crore",
        kind="results",
    ))
    assert "missing disclaimer" in problems


_HINDI_RESULTS = (
    "3BHK प्रोजेक्ट्स (अनुमानित बेस राशि):\n"
    "- Project A: अनुमानित बेस राशि ₹57.54 लाख से\n\n"
    "अनुमानित बेस राशि = न्यूनतम सूचीबद्ध दर x सेलेबल एरिया। "
    "यह केवल एक बेस अनुमान है और इसमें कर और पंजीकरण शामिल नहीं हैं।"
)


def test_localized_estimate_with_grounded_amount_and_disclaimer_is_accepted():
    assert honesty_problems(
        _turn(_HINDI_RESULTS, kind="results"),
        expected_figures={"Project A": "INR 57.54 lakh"},
    ) == []


def test_localized_estimate_with_wrong_amount_is_rejected():
    problems = honesty_problems(
        _turn(_HINDI_RESULTS, kind="results"),
        expected_figures={"Project A": "INR 60.00 lakh"},
    )
    assert any(problem.startswith("figure mismatch for Project A") for problem in problems)


def test_localized_estimate_without_disclaimer_is_rejected():
    answer = _HINDI_RESULTS.split("\n\n")[0]
    assert "missing disclaimer" in honesty_problems(_turn(answer, kind="results"))


def test_english_estimate_missing_disclaimer_still_fails_despite_localized_support():
    problems = honesty_problems(_turn(
        "3BHK projects (estimated base amount):\n"
        "- Project A: estimated base amount from INR 57.54 lakh\n\n"
        "Estimated base amount = minimum listed rate x saleable area.",
        kind="results",
    ), expected_figures={"Project A": "INR 57.54 lakh"})
    assert problems == ["missing disclaimer"]


_HINDI_HEADER = (
    "3BHK प्रोजेक्ट्स (अनुमानित बेस राशि):\n"
    "- Project A: अनुमानित बेस राशि ₹57.54 लाख से\n\n"
)


@pytest.mark.parametrize("disclaimer", [
    "यह केवल एक बेस अनुमान है और इसमें कर और पंजीकरण शामिल नहीं हैं।",
    "यह बेस अनुमान है; टैक्स, रजिस्ट्रेशन और अन्य शुल्क अलग से लगेंगे।",
    "अनुमानित राशि में जीएसटी और स्टाम्प ड्यूटी अतिरिक्त है।",
])
def test_valid_localized_disclaimers_are_accepted(disclaimer):
    assert honesty_problems(_turn(_HINDI_HEADER + disclaimer, kind="results")) == []


@pytest.mark.parametrize("line", [
    "अनुमानित राशि ₹2 करोड़",
    "अनुमानित राशि ₹2 करोड़ है, यह शामिल नहीं है।",
    "यह केवल एक बेस अनुमान है।",
    "यह सिर्फ अनुमान है।",
    "यह केवल अनुमान है, इसमें कर शामिल है।",
])
def test_localized_disclaimer_false_positives_are_rejected(line):
    assert "missing disclaimer" in honesty_problems(_turn(_HINDI_HEADER + line, kind="results"))


def test_localized_estimate_label_must_be_on_result_bullets():
    answer = _HINDI_RESULTS.replace("- Project A: अनुमानित बेस राशि ₹57.54 लाख से",
                                    "- Project A: ₹57.54 लाख से")
    assert "missing 'estimated base amount'" in honesty_problems(_turn(answer, kind="results"))


def test_unsupported_live_availability_claim_is_rejected():
    problems = honesty_problems(_turn(
        "Acro Iris has 2 units currently available.", kind="locality_question",
    ))
    assert "unsupported unit availability claim" in problems


@pytest.mark.parametrize("source_status,answer", [
    ("snapshot", "These are catalogue listings; I haven't checked current unit availability yet."),
    ("failed", "Live project data is unavailable right now. Please try again."),
])
def test_honest_snapshot_and_failure_messages_are_accepted(source_status, answer):
    assert honesty_problems(_turn(answer, kind="locality_question", source_status=source_status)) == []


_ROMANIZED_RESULTS = (
    "Lagbhag INR 1.50 crore (estimated base amount) ke andar Pune mein 3BHK projects:\n"
    "- Project A: INR 57.54 lakh se estimated base amount\n\n"
)


def test_romanized_disclaimer_with_grounded_amount_is_accepted():
    answer = _ROMANIZED_RESULTS + (
        "Yeh sirf ek base estimate hai aur ismein taxes, registration, floor rise "
        "aur parking shaamil nahi hain; rates change ho sakte hain.")
    assert honesty_problems(_turn(answer, kind="results"),
                            expected_figures={"Project A": "INR 57.54 lakh"}) == []


@pytest.mark.parametrize("line", [
    "Yeh sirf ek base estimate hai; rates change ho sakte hain.",
    "Yeh sirf ek base estimate hai aur ismein taxes shaamil hain.",
])
def test_romanized_disclaimer_without_exclusion_is_rejected(line):
    assert "missing disclaimer" in honesty_problems(_turn(_ROMANIZED_RESULTS + line, kind="results"))


def test_romanized_reply_with_wrong_amount_is_rejected():
    answer = _ROMANIZED_RESULTS + "Yeh sirf ek base estimate hai; taxes shaamil nahi hain."
    problems = honesty_problems(_turn(answer, kind="results"),
                                expected_figures={"Project A": "INR 60.00 lakh"})
    assert any(p.startswith("figure mismatch") for p in problems)
