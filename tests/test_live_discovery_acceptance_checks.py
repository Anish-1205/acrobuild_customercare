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
