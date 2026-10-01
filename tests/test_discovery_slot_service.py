"""services/discovery_slot_service.py: discovery slot flow (Inquiry to Sales §28, §32).

Offline and deterministic: acrobuild_company_service._cached_request is a fake
that logs like the real client (so property_tools_service derives a real
source_status), and _request_json fails the test if it is ever reached.
"""
import ast
import copy
import logging
import re
import sys
import time
from pathlib import Path

import pytest

from services import acrobuild_company_service as company_service
from services import discovery_slot_service as discovery
from services import property_tools_service as tools
from services.internal_api_log_service import begin_data_api_trace, end_data_api_trace, log_data_api_call
from services.project_home_type_service import requested_home_types

PROJECTS = [
    {"id": 1, "projectName": "Alpha Heights", "locality": "Wakad", "city": "Pune"},
    {"id": 2, "projectName": "Beta Residency", "locality": "", "city": "Thane"},
    {"id": 3, "projectName": "Gamma Park", "locality": "Hinjewadi", "city": "Pune"},
    {"id": 4, "projectName": "Delta Towers", "locality": "Wakad", "city": "Pune"},
    {"id": 5, "projectName": "Epsilon Homes", "locality": "Kalyan", "city": "Thane"},
    {"id": 55, "projectName": "GBK Group", "address": "someone@example.invalid"},
]
SQFT = "Rate Per Sq.Ft."
TYPOLOGIES = {
    1: [{"id": 11, "typologyName": "3BHK", "rateType": SQFT, "minBasePrice": 10000, "maxBasePrice": 12000,
         "saleableArea": 1200},
        {"id": 12, "typologyName": "2BHK", "rateType": SQFT, "minBasePrice": 9000, "maxBasePrice": 9500,
         "saleableArea": 800}],
    2: [{"id": 21, "typologyName": "3 BHK", "rateType": SQFT, "minBasePrice": 15000, "maxBasePrice": 16000,
         "saleableArea": 1300}],
    3: [{"id": 31, "typologyName": "3BHK", "rateType": "Lump sum", "minBasePrice": 9000000,
         "maxBasePrice": 9500000, "saleableArea": 1100}],
    4: [{"id": 41, "typologyName": "3BHK", "rateType": SQFT, "minBasePrice": 11000, "maxBasePrice": 11500,
         "saleableArea": 1500}],
    5: [{"id": 51, "typologyName": "1BHK", "rateType": SQFT, "minBasePrice": 8000, "maxBasePrice": 8500,
         "saleableArea": 600}],
}
LIVE_3BHK_AREAS = ["Hinjewadi", "Thane", "Wakad"]
PROJECT_NAMES = [p["projectName"] for p in PROJECTS]


def _route(path):
    if path == "/api/cs/projects":
        return PROJECTS
    match = re.fullmatch(r"/api/cs/projects/(\d+)/typologies", path)
    if match:
        return TYPOLOGIES.get(int(match.group(1)), [])
    raise AssertionError(f"unexpected CS path {path}")


class FakeCS:
    def __init__(self):
        self.calls = []
        self.fail = {}

    def __call__(self, path, params=None, ttl_seconds=None):
        self.calls.append(path)
        error = self.fail.get(path)
        if error is not None:
            log_data_api_call(provider="Acrobuild CS API", endpoint=path, params=params, status="failed",
                              error=str(error))
            raise error
        log_data_api_call(provider="Acrobuild CS API", endpoint=path, params=params, status="completed")
        return copy.deepcopy(_route(path))


@pytest.fixture
def cs(monkeypatch):
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", "true")
    fake = FakeCS()
    monkeypatch.setattr(company_service, "_cached_request", fake)
    monkeypatch.setattr(company_service, "_request_json",
                        lambda *a, **k: pytest.fail("discovery must not reach the network in tests"))
    token = begin_data_api_trace("discovery-test", "discovery question")
    yield fake
    end_data_api_trace(token)


def build(issue, slots=None, pending=None, names=PROJECT_NAMES):
    return discovery.build_discovery_answer(issue, slots, pending, names)


def _labels(draft):
    return [reply["label"] for reply in draft["quick_replies"]]


AWAIT_LOCALITY = {"config": ["3"], "awaiting": "locality", "origin_issue": "Show me 3 BHK"}
AWAIT_BUDGET = {"config": ["3"], "locality": "Wakad", "awaiting": "budget", "origin_issue": "Show me 3 BHK"}


# -----------------------------------
# FEATURE FLAG
# -----------------------------------

@pytest.mark.parametrize("value,expected", [
    ("1", True), ("true", True), ("TRUE", True), ("yes", True), ("on", True), (" On ", True),
    ("0", False), ("false", False), ("no", False), ("off", False), ("", False), ("enabled", False),
    ("2", False), ("truee", False),
])
def test_discovery_enabled_values(monkeypatch, value, expected):
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", value)
    assert discovery.discovery_enabled() is expected


def test_flag_defaults_off_and_is_read_at_call_time(monkeypatch, caplog):
    monkeypatch.delenv("ACROBUILD_DISCOVERY_SLOTS", raising=False)
    assert discovery.discovery_enabled() is False
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", "on")
    assert discovery.discovery_enabled() is True
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", "off")
    assert discovery.discovery_enabled() is False
    assert not caplog.records  # the flag value is never logged


def test_flag_off_builds_nothing_and_makes_no_call(cs, monkeypatch):
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", "false")
    assert build("Show me 3 BHK") is None
    assert build("1.5 crore", AWAIT_BUDGET) is None
    assert cs.calls == []
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", "true")
    assert build("Show me 3 BHK")["discovery_kind"] == "locality_question"


# -----------------------------------
# BUDGET PARSER
# -----------------------------------

CR, L = 10**7, 10**5


@pytest.mark.parametrize("text,expected", [
    ("1.5 crore", 15 * 10**6), ("1.5cr", 15 * 10**6), ("1.5 Cr.", 15 * 10**6), ("1.5 crores", 15 * 10**6),
    ("2 crore", 2 * CR), ("0.75 crore", 75 * L), ("₹1.5 Cr", 15 * 10**6), ("Rs 1.5 crore", 15 * 10**6),
    ("Rs1.5 crore", 15 * 10**6), ("rs. 80 lakh", 80 * L), ("150 lakh", 150 * L), ("80L", 80 * L),
    ("80 l", 80 * L), ("90 lacs", 90 * L), ("90 lac", 90 * L), ("45 lakhs", 45 * L), ("1 lakh", L),
    ("₹1,50,00,000", 15 * 10**6), ("₹ 1,50,00,000", 15 * 10**6), ("INR 15000000", 15 * 10**6),
    ("15000000 rupees", 15 * 10**6), ("rs 1,20,00,000", 12 * 10**6), ("1,20,00,000 INR", 12 * 10**6),
    ("1 crore 20 lakh", 12 * 10**6), ("1 crore and 20 lakh", 12 * 10**6), ("1cr 50l", 15 * 10**6),
    ("under 1.5 crore", 15 * 10**6), ("upto 1.5 crore", 15 * 10**6), ("up to 1.5 crore", 15 * 10**6),
    ("around 1.5 crore", 15 * 10**6), ("max 1.5 crore", 15 * 10**6), ("below 90 lakh", 90 * L),
    ("within 1 crore", CR), ("my budget is 1.2 crore", 12 * 10**6), ("budget: 95 lakh", 95 * L),
    ("80 lakh flat", 80 * L), ("1 to 1.5 crore", 15 * 10**6), ("1-1.5 crore", 15 * 10**6),
    ("1 - 1.5 crore", 15 * 10**6), ("80 lakh to 1.2 crore", 12 * 10**6),
    ("between 80 lakh and 1 crore", CR), ("1.2 to 1 crore", 12 * 10**6), ("1000 crore", 10**10),
    ("10000000000 rupees", 10**10),
    ("any budget", "any"), ("Any Budget", "any"), ("no limit", "any"), ("no budget limit", "any"),
    ("flexible", "any"), ("Flexible.", "any"), ("budget is flexible", "any"), ("any", "any"),
    ("no budget", "any"),
    ("1.5", None), ("15000000", None), ("9876543210", None), ("", None), (None, None), ("hello", None),
    ("3 BHK", None), ("0 crore", None), ("0 lakh", None), ("-1 crore", None), ("under -5 lakh", None),
    ("nan crore", None), ("NaN", None), ("inf lakh", None), ("999999 crore", None), ("1000.5 crore", None),
    ("10000000001 rupees", None), ("1e5 crore", None), ("5 labs", None), ("2 flats", None),
    ("floor 12", None), ("call me on 9876543210", None),
])
def test_parse_budget_inr(text, expected):
    assert discovery.parse_budget_inr(text) == expected


def test_parse_budget_values_are_bounded_ints():
    for text in ("1.5 crore", "₹1,50,00,000", "1 crore 20 lakh", "1 to 1.5 crore"):
        value = discovery.parse_budget_inr(text)
        assert isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 10**10


def test_range_keeps_its_wording_in_budget_label():
    slots = discovery.extract_discovery_slots("3 BHK for 1 to 1.5 crore")
    assert slots["budget_max_inr"] == 15 * 10**6
    assert slots["budget_label"] == "1 to 1.5 crore"


@pytest.mark.parametrize("adversarial", [
    "1" * 10_000, "1." * 5_000, "crore " * 2_000, "-" * 10_000, "1 to " * 2_500, "₹" * 10_000,
    "1 crore " * 1_250, "a" * 10_000, ("9" * 50 + " crore ") * 150, "1,2" * 3_333,
], ids=["digits", "dots", "units", "dashes", "ranges", "rupee-signs", "amounts", "letters", "huge-numbers",
        "commas"])
def test_budget_parser_is_linear_on_adversarial_input(adversarial):
    started = time.perf_counter()
    result = discovery.parse_budget_inr(adversarial)
    assert time.perf_counter() - started < 0.5
    assert result is None or result == "any" or 1 <= result <= 10**10


# -----------------------------------
# REQUEST / REPLY DETECTION
# -----------------------------------

@pytest.mark.parametrize("issue", [
    "Show me 3 BHK", "I want a 3bhk", "3 BHK in Wakad under 1.5 crore", "any 2bhks available",
    "Show me 3BHK. Selected locality: Wakad", "2 BHK homes please",
])
def test_discovery_requests(issue):
    assert discovery.is_discovery_request(issue, PROJECT_NAMES)


@pytest.mark.parametrize("issue", [
    "Show me 3 BHK in Alpha Heights",                     # named project
    "Show me 3BHK\nRequested project: Alpha Heights",     # project from context
    "3 BHK in A wing", "3bhk on the 5th floor", "flat 1501 3bhk", "3 BHK amenities", "3bhk location",
    "where can I get 3 BHK", "3 BHK documents", "3 BHK price", "3 BHK cost", "3 bhk possession date",
    "recommend a 3 BHK", "suggest a 2bhk", "best 2bhk", "cheapest 2 BHK", "affordable 3bhk",
    "budget-friendly 2 bhk",
    # Quantity phrasing owned by the budget recommenders (tests/test_global_recommendation.py).
    "I want two 2BHK flats for 40 lakh", "I need 2 flats of 2BHK within 40 lakh",
    "My budget is 40 lakh rupee. I want to buy 2 flats 2BHK.",
    "I want to buy 2 of 2BHK Flats in budget of 40 lakh rupees", "one 1BHK and one 2BHK",
    "2bhk for 40 lakh, is it sufficient?", "can i afford it for a 2bhk",
    "which projects have 3BHK", "which project has 2bhk",   # catalogue filter
    "hello", "Show me the office address",                 # no configuration
])
def test_not_discovery_requests(issue):
    assert not discovery.is_discovery_request(issue, PROJECT_NAMES)


@pytest.mark.parametrize("slots,reply,expected", [
    (AWAIT_BUDGET, "1.5 crore", True), (AWAIT_BUDGET, "any budget", True), (AWAIT_BUDGET, "under 90 lakh", True),
    (AWAIT_BUDGET, "around 1.5 crore?", True), (AWAIT_BUDGET, "1 to 1.5 crore", True),
    (AWAIT_BUDGET, "hi", False), (AWAIT_BUDGET, "what is the price?", False), (AWAIT_BUDGET, "9876543210", False),
    (AWAIT_BUDGET, "1.5", False), (AWAIT_BUDGET, "2 BHK under 1 crore", False),
    (AWAIT_BUDGET, "how much is a 1 crore flat", False), (AWAIT_BUDGET, "Wakad", False),
    (AWAIT_LOCALITY, "Wakad", True), (AWAIT_LOCALITY, "in Wakad", True), (AWAIT_LOCALITY, "Wakad side", True),
    (AWAIT_LOCALITY, "Any area", True), (AWAIT_LOCALITY, "anywhere", True), (AWAIT_LOCALITY, "Kharadi", True),
    (AWAIT_LOCALITY, "hi", False), (AWAIT_LOCALITY, "what amenities?", False), (AWAIT_LOCALITY, "9876543210", False),
    (AWAIT_LOCALITY, "1.5 crore", False), (AWAIT_LOCALITY, "tell me more", False), (AWAIT_LOCALITY, "yes", False),
    (AWAIT_LOCALITY, "start over", False), (AWAIT_LOCALITY, "Show me 2 BHK", False),
    ({"config": ["3"], "awaiting": None}, "Wakad", False), ({"awaiting": "project"}, "Wakad", False),
    (None, "1.5 crore", False), ({"awaiting": "budget"}, "x" * 500 + " 1 crore", False),
])
def test_is_slot_reply(slots, reply, expected):
    assert discovery.is_slot_reply(slots, reply) is expected


# -----------------------------------
# PURE SLOT EXTRACTION
# -----------------------------------

def test_extract_all_slots_from_live_values():
    slots = discovery.extract_discovery_slots("3 BHK in wakad under 1.5 crore", ["Wakad", "Pune"])
    assert slots == {"config": ["3"], "locality": "Wakad", "budget_max_inr": 15 * 10**6,
                     "budget_label": "1.5 crore"}


def test_extract_any_area_and_any_budget():
    slots = discovery.extract_discovery_slots("3 BHK in any area, any budget", ["Wakad"])
    assert slots["locality"] == "any" and slots["budget_max_inr"] is None


@pytest.mark.parametrize("text", ["3 BHK in Kharadi", "3 BHK in Wakad or Hinjewadi", "Wakadd"])
def test_extract_never_stores_unknown_or_ambiguous_place(text):
    assert "locality" not in discovery.extract_discovery_slots(text, ["Wakad", "Hinjewadi"])


def test_extract_prefers_the_longest_live_name():
    slots = discovery.extract_discovery_slots("2 bhk in ambernath east", ["Ambernath", "Ambernath East"])
    assert slots["locality"] == "Ambernath East"


# -----------------------------------
# FLOWS: NAMED OPTIONS, FOLLOW-UPS, ONE-SHOT
# -----------------------------------

def test_locality_question_lists_every_live_option(cs):
    draft = build("Show me 3 BHK")
    assert draft["discovery_kind"] == "locality_question"
    assert draft["options"] == LIVE_3BHK_AREAS
    assert draft["answer"] == "\n".join([
        "I found 3BHK projects in these areas:",
        *[f"- {area}" for area in LIVE_3BHK_AREAS],
        "Which area would you like to explore?",
    ])
    assert _labels(draft) == LIVE_3BHK_AREAS + ["Any area"]
    pending = draft["pending_project_lookup"]
    assert pending == {"kind": "selection", "entity": "locality", "options": LIVE_3BHK_AREAS, "scope": {},
                       "original_issue": "Show me 3 BHK", "purpose": "discovery"}
    assert "Any area" not in pending["options"]
    assert draft["clarification_entity"] == "locality"
    assert draft["discovery_slots"] == {"config": ["3"], "awaiting": "locality", "origin_issue": "Show me 3 BHK"}
    assert draft["source_status"] == "live_api"
    assert draft["matched_chunks"] and all(c["record_kind"] == "company_api" for c in draft["matched_chunks"])


def test_pending_resume_asks_budget_with_live_evidence(cs):
    pending = {"kind": "selection", "entity": "locality", "options": LIVE_3BHK_AREAS,
               "scope": {"locality": "Wakad"}, "original_issue": "Show me 3 BHK", "purpose": "discovery"}
    draft = build("Show me 3 BHK. Selected locality: Wakad", AWAIT_LOCALITY, pending)
    assert draft["discovery_kind"] == "budget_question"
    assert draft["answer"].startswith("What's your approximate budget for a 3BHK in Wakad?")
    assert draft["discovery_prompt"] == "budget"
    assert draft["quick_replies"] == [{"label": "Any budget", "value": "any budget"}]
    assert "pending_project_lookup" not in draft
    assert draft["discovery_slots"]["locality"] == "Wakad" and draft["discovery_slots"]["awaiting"] == "budget"
    assert {c["project"]["projectName"] for c in draft["matched_chunks"]} == {"Alpha Heights", "Delta Towers"}
    assert draft["source_status"] == "live_api"


@pytest.mark.parametrize("reply,canonical", [("Wakad", "Wakad"), ("  wakad  ", "Wakad"), ("in WAKAD", "Wakad"),
                                              ("pune", "Pune"), ("Thane", "Thane")])
def test_short_follow_up_and_typed_city(cs, reply, canonical):
    draft = build(reply, AWAIT_LOCALITY)
    assert draft["discovery_kind"] == "budget_question"
    assert draft["discovery_slots"]["locality"] == canonical


def test_typed_city_not_in_options_is_accepted(cs):
    assert "Pune" not in LIVE_3BHK_AREAS
    draft = build("Pune", AWAIT_LOCALITY)
    assert {c["project"]["projectName"] for c in draft["matched_chunks"]} == {
        "Alpha Heights", "Gamma Park", "Delta Towers"}


@pytest.mark.parametrize("reply", ["Any area", "anywhere", "any area please"])
def test_any_area_skips_the_locality_filter(cs, reply):
    draft = build(reply, AWAIT_LOCALITY)
    assert draft["discovery_kind"] == "budget_question"
    assert draft["discovery_slots"]["locality"] == "any"
    assert draft["answer"].startswith("What's your approximate budget for a 3BHK?")
    results = build("1.5 crore", draft["discovery_slots"])
    assert results["options"] == ["Alpha Heights", "Gamma Park"]
    assert "Beta Residency" in results["answer"] and "Delta Towers" in results["answer"]


def test_any_area_button_works_with_a_pending_selection(cs):
    locality_question = build("Show me 3 BHK")
    draft = build("Any area", locality_question["discovery_slots"], locality_question["pending_project_lookup"])
    assert draft["discovery_slots"]["locality"] == "any"


def test_budget_results_use_estimated_base_amount(cs):
    draft = build("1.5 crore", AWAIT_BUDGET)
    answer = draft["answer"]
    assert draft["discovery_kind"] == "results"
    assert "- Alpha Heights: estimated base amount from INR 1.20 crore" in answer
    assert "Above your budget:" in answer and "- Delta Towers: estimated base amount from INR 1.65 crore" in answer
    assert discovery.DISCLAIMER in answer
    assert draft["options"] == ["Alpha Heights"]
    pending = draft["pending_project_lookup"]
    assert pending["entity"] == "project" and pending["purpose"] == "home_type_search"
    assert pending["original_issue"] == "Show me 3BHK in Wakad within about INR 1.50 crore"
    assert requested_home_types(pending["original_issue"]) == ["3"]
    assert draft["discovery_slots"]["budget_max_inr"] == 15 * 10**6
    assert draft["discovery_slots"]["awaiting"] is None
    assert draft["source_status"] == "live_api"


def test_any_budget_lists_every_priced_project(cs):
    draft = build("any budget", AWAIT_BUDGET)
    assert draft["options"] == ["Alpha Heights", "Delta Towers"]
    assert "Above your budget" not in draft["answer"]
    assert "budget_max_inr" in draft["discovery_slots"] and draft["discovery_slots"]["budget_max_inr"] is None
    assert draft["discovery_slots"]["budget_label"] == "any budget"


def test_one_shot_fills_every_slot(cs):
    draft = build("3 BHK in Pune under 1.5 crore")
    assert draft["discovery_kind"] == "results"
    assert draft["options"] == ["Alpha Heights", "Gamma Park"]
    assert "Pricing not listed:\n- Gamma Park" in draft["answer"]
    assert draft["discovery_slots"]["locality"] == "Pune"


def test_one_shot_with_nothing_in_budget_offers_real_projects(cs):
    draft = build("3 BHK in Thane under 1.5 crore")
    assert "No current 3BHK projects in Thane have an estimated base amount within about INR 1.50 crore." \
        in draft["answer"]
    assert draft["options"] == ["Beta Residency"]


def test_single_live_area_is_selected_automatically(cs):
    draft = build("Show me 2 BHK")
    assert draft["discovery_kind"] == "budget_question"
    assert draft["answer"].startswith("All current 2BHK projects are in Wakad.")
    assert draft["discovery_slots"]["locality"] == "Wakad"


def test_no_project_lists_the_configuration(cs):
    draft = build("Show me 4 BHK")
    assert draft["discovery_kind"] == "no_config"
    assert draft["answer"] == "None of the projects in the latest catalogue list 4BHK right now."
    assert draft["discovery_slots"]["awaiting"] is None
    assert "pending_project_lookup" not in draft


def test_new_configuration_reuses_stored_locality_and_budget(cs):
    stored = {**AWAIT_BUDGET, "awaiting": None, "budget_max_inr": 10**8, "budget_label": "10 crore"}
    draft = build("and 2 BHK?", stored)
    assert draft["discovery_kind"] == "results"
    assert draft["discovery_slots"]["config"] == ["2"]
    assert draft["options"] == ["Alpha Heights"]


# -----------------------------------
# UNKNOWN LOCALITY (never invented, never stored)
# -----------------------------------

def test_unknown_locality_is_quoted_not_stored(cs):
    draft = build("Kharadi", AWAIT_LOCALITY)
    assert draft["discovery_kind"] == "locality_not_found"
    assert draft["answer"] == "\n".join([
        "I couldn't find any current 3BHK projects in 'Kharadi'.",
        "I found 3BHK projects in these areas:",
        *[f"- {area}" for area in LIVE_3BHK_AREAS],
        "Which area would you like to explore?",
    ])
    assert draft["options"] == LIVE_3BHK_AREAS
    assert _labels(draft)[-1] == "Any area"
    assert "Kharadi" not in str(draft["discovery_slots"])
    assert "Kharadi" not in str(draft["pending_project_lookup"])
    assert draft["discovery_slots"]["awaiting"] == "locality"


def test_every_listed_option_is_accepted_when_typed(cs):
    for option in build("Kharadi", AWAIT_LOCALITY)["options"]:
        assert build(option, AWAIT_LOCALITY)["discovery_slots"]["locality"] == option


def test_one_shot_unknown_locality_keeps_other_slots(cs):
    draft = build("3 BHK in Kharadi under 1 crore")
    assert draft["discovery_kind"] == "locality_not_found"
    slots = draft["discovery_slots"]
    assert slots["config"] == ["3"] and slots["budget_max_inr"] == 10**7 and "locality" not in slots


def test_unsafe_customer_text_is_not_echoed(cs):
    # Not place-shaped: not a slot reply at all, so no draft and no call.
    assert build("Kh⁣aradi<script>", AWAIT_LOCALITY) is None
    assert cs.calls == []
    # Marker characters are removed before anything is quoted back.
    draft = build("3 BHK in Kha⁣radi")
    assert "'Kharadi'" in draft["answer"] and "⁣" not in draft["answer"]
    # A resumed selector that is not letters-only is never quoted.
    pending = {"kind": "selection", "entity": "locality", "purpose": "discovery", "scope": {},
               "options": [], "original_issue": "Show me 3 BHK"}
    draft = build("Show me 3 BHK. Requested locality: <script>alert(1)</script>", AWAIT_LOCALITY, pending)
    assert draft["discovery_kind"] == "locality_not_found"
    assert "<script>" not in draft["answer"] and "in that area." in draft["answer"]


# -----------------------------------
# FORGED SLOTS / PENDING STATE
# -----------------------------------

def test_forged_locality_slot_is_rechecked_against_live_data(cs):
    forged = {"config": ["3"], "locality": "Forged Nagar", "awaiting": "budget"}
    draft = build("1.5 crore", forged)
    assert draft["discovery_kind"] == "locality_question"
    assert "Forged Nagar" not in draft["answer"] and "Forged Nagar" not in str(draft["discovery_slots"])


def test_forged_values_are_dropped(cs):
    forged = {"config": ["9"], "awaiting": "locality", "budget_max_inr": -5, "origin_issue": "x⁣y",
              "project": "Alpha Heights"}
    draft = build("Wakad", forged)
    slots = draft["discovery_slots"]
    assert "project" not in slots and "⁣" not in slots["origin_issue"]
    assert slots.get("budget_max_inr") is None and "config" not in slots


def test_forged_pending_scope_is_quoted_never_trusted(cs):
    pending = {"kind": "selection", "entity": "locality", "purpose": "discovery",
               "scope": {"locality": "Forged⁣Nagar"}, "options": ["x"] * 1000,
               "original_issue": "Show me 3 BHK"}
    draft = build("Show me 3 BHK. Selected locality: Forged Nagar", AWAIT_LOCALITY, pending)
    assert draft["discovery_kind"] == "locality_not_found"
    assert draft["options"] == LIVE_3BHK_AREAS
    assert "⁣" not in draft["answer"]
    assert "Forged" not in str(draft["discovery_slots"])


def test_unrelated_pending_state_is_ignored(cs):
    pending = {"kind": "selection", "entity": "wing", "options": ["A"], "scope": {"project": "Alpha Heights"},
               "original_issue": "Show wings"}
    assert build("Wakad", None, pending) is None
    assert cs.calls == []


# -----------------------------------
# NOT A DISCOVERY TURN -> NO CALL
# -----------------------------------

@pytest.mark.parametrize("issue,slots", [
    ("hello", None), ("What amenities does Alpha Heights have?", None), ("Show me 3 BHK in Alpha Heights", None),
    ("hi", AWAIT_BUDGET), ("what are the amenities?", AWAIT_LOCALITY), ("9876543210", AWAIT_BUDGET),
])
def test_non_discovery_turns_return_none_without_calls(cs, issue, slots):
    assert build(issue, slots) is None
    assert cs.calls == []


# -----------------------------------
# TOOL FAILURES (no retry cap, state kept)
# -----------------------------------

def test_repeated_failure_at_locality_step_keeps_state(cs):
    cs.fail["/api/cs/projects"] = RuntimeError("CS API request timed out.")
    drafts = [build("Show me 3 BHK") for _ in range(3)]
    for draft in drafts:
        assert draft["discovery_kind"] == "unavailable"
        assert draft["source_status"] == "failed" and draft["source_status"] != "live_api"
        assert draft["pending_project_lookup"] == {"kind": "selection", "entity": "locality", "options": [],
                                                   "scope": {}, "original_issue": "Show me 3 BHK",
                                                   "purpose": "discovery"}
        assert draft["discovery_slots"]["config"] == ["3"]
        assert "try again" in draft["answer"]
    assert drafts[0] == drafts[1] == drafts[2]
    del cs.fail["/api/cs/projects"]
    retried = build(drafts[-1]["pending_project_lookup"]["original_issue"], drafts[-1]["discovery_slots"])
    assert retried["discovery_kind"] == "locality_question"


def test_repeated_failure_at_results_step_keeps_state(cs):
    cs.fail["/api/cs/projects"] = RuntimeError("CS API request timed out.")
    drafts = [build("1.5 crore", AWAIT_BUDGET) for _ in range(3)]
    for draft in drafts:
        pending = draft["pending_project_lookup"]
        assert pending["entity"] == "project" and pending["purpose"] == "home_type_search"
        assert pending["options"] == []
        assert pending["original_issue"] == "Show me 3BHK in Wakad within about INR 1.50 crore"
        assert draft["discovery_slots"]["locality"] == "Wakad"
        assert draft["discovery_slots"]["budget_max_inr"] == 15 * 10**6
    del cs.fail["/api/cs/projects"]
    retried = build(drafts[-1]["pending_project_lookup"]["original_issue"], drafts[-1]["discovery_slots"])
    assert retried["discovery_kind"] == "results" and retried["options"] == ["Alpha Heights"]


def test_skipped_projects_are_disclosed_and_never_live(cs):
    cs.fail["/api/cs/projects/4/typologies"] = RuntimeError("CS API request timed out.")
    draft = build("3 BHK in Wakad under 1.5 crore")
    assert "1 project(s) could not be checked" in draft["answer"]
    assert "Delta Towers" not in draft["answer"]
    assert draft["source_status"] == "failed"
    assert draft["skipped"] == [{"project": "Delta Towers", "error": "CS API request timed out."}]


@pytest.mark.parametrize("status,source_status", [
    ("blocked", "unavailable"), ("invalid", "unavailable"), ("unavailable", "failed"), ("ok", "unavailable"),
])
def test_unusable_tool_results_never_produce_live_api(cs, monkeypatch, status, source_status):
    result = tools._result("search_projects", status, source_status,
                           {"items": [], "matches": [], "over_budget": [], "unpriced": [], "locality_known": True})
    monkeypatch.setattr(tools, "search_projects", lambda *a, **k: result)
    draft = build("Show me 3 BHK")
    assert draft["discovery_kind"] == "unavailable"
    assert draft["source_status"] == "failed"


# -----------------------------------
# COPY RULES
# -----------------------------------

def test_copy_never_says_price_or_floor_plan(cs):
    answers = [build("Show me 3 BHK")["answer"], build("Wakad", AWAIT_LOCALITY)["answer"],
               build("1.5 crore", AWAIT_BUDGET)["answer"], build("any budget", AWAIT_BUDGET)["answer"],
               build("3 BHK in Pune under 1.5 crore")["answer"], build("Kharadi", AWAIT_LOCALITY)["answer"]]
    for answer in answers:
        assert not re.search(r"\bprices?\b", answer, re.IGNORECASE)
        assert "floor plan" not in answer.lower()


def test_budget_question_avoids_clarification_prose_triggers(cs):
    answer = build("Wakad", AWAIT_LOCALITY)["answer"]
    # property_clarification_service.clarification_entity() prose detector words
    assert not re.search(r"\b(?:which|choose|select|pick|specify|share|provide|mention|tell me)\b", answer, re.I)


# -----------------------------------
# OBSERVABILITY: NO RAW CUSTOMER TEXT IN LOGS
# -----------------------------------

def test_logs_hold_no_customer_text(cs, caplog):
    secrets = ["Kharadi", "1.5 crore", "9876543210", "buyer@example.invalid", "Show me"]
    with caplog.at_level(logging.DEBUG):
        build("Show me 3 BHK, call me on 9876543210 or buyer@example.invalid")
        build("Kharadi", AWAIT_LOCALITY)
        build("1.5 crore", AWAIT_BUDGET)
    discovery_records = [r for r in caplog.records if r.name == "chatbot.discovery"]
    assert len(discovery_records) == 3
    for record in caplog.records:
        message = record.getMessage()
        assert not any(secret in message for secret in secrets), message


# -----------------------------------
# ARCHITECTURE RULES
# -----------------------------------

ALLOWED_PROJECT_IMPORTS = {
    "services.property_tools_service", "services.conversation_store_service",
    "services.project_home_type_service", "services.observability",
}


def test_module_imports_only_allowed_dependencies():
    tree = ast.parse(Path(discovery.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "services":
                imported.update(f"services.{alias.name}" for alias in node.names)
            else:
                imported.add(node.module or "")
    project_imports = {name for name in imported if name.split(".")[0] not in sys.stdlib_module_names}
    assert project_imports <= ALLOWED_PROJECT_IMPORTS, project_imports - ALLOWED_PROJECT_IMPORTS
    forbidden = ("routers", "api_context", "graph", "services.ai_agent_service",
                 "services.property_clarification_service", "services.acrobuild_company_service")
    assert not any(name == prefix or name.startswith(prefix + ".") for name in imported for prefix in forbidden)


def test_module_holds_no_mutable_state():
    tree = ast.parse(Path(discovery.__file__).read_text(encoding="utf-8"))
    mutable_nodes = (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            assert not isinstance(node.value, mutable_nodes), ast.unparse(node)
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
                assert node.value.func.id not in {"list", "dict", "set", "defaultdict", "deque"}, ast.unparse(node)
        assert not isinstance(node, ast.Global)
