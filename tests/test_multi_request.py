"""Several requests in one message are split only where they ask different things."""
import pytest

from services.multi_request import split_requests

NAMES = ["Vishwajeet Prime", "Vishwajeet Paradise", "Vishwajeet Heights"]


def find(text):
    lowered = text.lower()
    return next((n for n in NAMES if n.split()[-1].lower() in lowered), None)


@pytest.mark.parametrize("text, parts", [
    ("price of prime and amenities of paradise", ["price of prime", "amenities of paradise"]),
    ("price and amenities of prime", ["price of Vishwajeet Prime", "amenities of prime"]),
    ("price of prime and paradise", ["price of prime", "price of paradise"]),
    ("where is heights? any offers?", ["where is heights", "any offers of Vishwajeet Heights"]),
    ("location of prime, also payment plan", ["location of prime", "payment plan of Vishwajeet Prime"]),
])
def test_separate_requests_are_split(text, parts):
    assert split_requests(text, find) == parts


@pytest.mark.parametrize("text", [
    "2bhk and 3bhk in pune", "parking and lift", "3bhk with best amenities", "price of 2bhk and 3bhk in prime",
    "3bhk in pune? with gym", "hi? price of prime", "1200 sq. ft flat in thane", "2bhk plus study room",
])
def test_one_request_stays_whole(text):
    assert len(split_requests(text, find)) == 1


def test_answers_about_two_projects_offer_both_projects():
    from routers.assist import _combine_answers
    from services.choice_service import single_project_choices
    combined = _combine_answers([{"answer": "a", "choices": single_project_choices("Vishwajeet Prime")},
                                 {"answer": "b", "choices": single_project_choices("Vishwajeet Paradise")}], [])
    assert [c["label"] for c in combined["choices"]] == ["Vishwajeet Prime", "Vishwajeet Paradise"]
    assert all(c["action"] == "project" for c in combined["choices"])
