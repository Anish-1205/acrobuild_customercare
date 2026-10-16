"""Complete limitation answers survive the real assist post-processing path."""

import copy
import json
import re
import uuid

import pytest
from fastapi.testclient import TestClient

from app import api
from api_context import SupportAssistRequest, build_unsupported_capability_assist
from graph import main_orchestrator
from routers import assist
from services import acrobuild_company_service as company
from services.conversation_store_service import (
    get_current_project_context, get_discovery_slots, get_pending_project_lookup,
)
from services.internal_api_log_service import log_data_api_call
from services.turn_analysis_service import TurnAnalysis


ENDPOINTS = ("/api/support/assist", "/api/support/assist/stream")
PROJECTS = [
    {"id": 1, "projectName": "Vishwajeet Prime", "city": "Thane", "locality": "Thane"},
    {"id": 2, "projectName": "Vishwajeet Town", "city": "Thane", "locality": "Thane"},
    {"id": 3, "projectName": "Vishwajeet Precious(Pearl)", "city": "Thane", "locality": "Thane"},
    {"id": 4, "projectName": "Vishwajeet Precious (Emerald)", "city": "Pune", "locality": "Pune"},
]
WINGS = [
    {"id": 11, "name": "A", "totalFloors": 2},
    {"id": 12, "name": "B", "totalFloors": 2},
]
INVENTORY = [
    {"unitNumber": "101", "floorNumber": 1, "typologyName": "3BHK", "typologyId": 101,
     "saleableArea": 1500, "status": "Available"},
    {"unitNumber": "201", "floorNumber": 2, "typologyName": "2BHK", "typologyId": 102,
     "saleableArea": 1200, "status": "Available"},
]
TYPOLOGIES = [
    {"id": 101, "typologyName": "3BHK", "minBasePrice": 4000,
     "maxBasePrice": 7500, "saleableArea": 1500, "rateType": "Rate Per Sq.Ft."},
    {"id": 102, "typologyName": "2BHK", "minBasePrice": 3500,
     "maxBasePrice": 6500, "saleableArea": 1200, "rateType": "Rate Per Sq.Ft."},
]


@pytest.fixture
def support_env(monkeypatch):
    """Keep endpoints and clarification real while replacing external reads."""
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", "true")
    history = {}

    class Session:
        def __init__(self, _cookie, conversation_id):
            self.conversation_id = conversation_id

        def set_cookie(self, _response):
            pass

        def load(self):
            return list(history.get(self.conversation_id, []))

        def append(self, issue, answer, marker=""):
            history.setdefault(self.conversation_id, []).extend([
                {"sender": "customer", "text": issue},
                {"sender": "bot", "text": str(answer or "") + marker},
            ])

    def fake_cached_request(path, params=None, ttl_seconds=None):
        del ttl_seconds
        log_data_api_call(provider="Acrobuild CS API", endpoint=path,
                          params=params, status="completed")
        if path == "/api/cs/projects":
            return copy.deepcopy(PROJECTS)
        match = re.fullmatch(r"/api/cs/projects/(\d+)/(amenities|wings|typologies)", path)
        if match:
            project_id, kind = int(match[1]), match[2]
            if kind == "amenities":
                return ([{"iconName": "Badminton", "type": "Amenities"}]
                        if project_id in {1, 2} else [])
            if kind == "wings":
                return copy.deepcopy(WINGS if project_id == 1 else [])
            return copy.deepcopy(TYPOLOGIES)
        match = re.fullmatch(r"/api/cs/wings/(\d+)/(inventory|typologies)", path)
        if match:
            wing_id, kind = int(match[1]), match[2]
            if wing_id not in {11, 12}:
                return []
            return copy.deepcopy(INVENTORY if kind == "inventory" else TYPOLOGIES)
        raise AssertionError(f"Unexpected CS path: {path}")

    monkeypatch.setattr(assist, "ConversationSession", Session)
    monkeypatch.setattr(company, "_cached_request", fake_cached_request)
    monkeypatch.setattr(company, "_request_json", lambda *_a, **_k: pytest.fail("External CS call"))
    monkeypatch.setattr(main_orchestrator, "analyze_turn",
                        lambda *_a: TurnAnalysis("property", "English", "latin", "test"))
    return history


def ask(client, endpoint, issue, conversation_id=None):
    conversation_id = conversation_id or str(uuid.uuid4())
    response = client.post(endpoint, json={"issue": issue, "conversation_id": conversation_id,
                                           "prefer_qwen_response": True})
    assert response.status_code == 200, response.text
    if endpoint.endswith("/stream"):
        events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        payload = next(event["response"] for event in events if event.get("type") == "done")
    else:
        payload = response.json()
    return payload, conversation_id


LIMITATION_CASES = (
    ("Can you tell me todays best mortgage rate across every bank?", "mortgage_rates"),
    ("Which bank offers the best home loan rate?", "mortgage_rates"),
    ("Which banks are near Vishwajeet Prime?", "nearby_places"),
    ("Which hospitals are within 3 km of Vishwajeet Prime?", "nearby_places"),
    ("What hospitals are near Vishwajeet Prime?", "nearby_places"),
    ("What schools are within 5 km of Vishwajeet Prime?", "nearby_places"),
    ("How far is the nearest hospital from Vishwajeet Prime?", "nearby_places"),
    ("Will this project's price definitely double in 3 years?", "investment_guarantee"),
    ("Will this property definitely double in value?", "investment_guarantee"),
    ("Can you guarantee 20% returns?", "investment_guarantee"),
    ("Is appreciation guaranteed?", "investment_guarantee"),
    ("Can you guarantee a 2 BHK is available to book today?", "booking_guarantee"),
    ("Is the 3BHK in Vishwajeet Prime guaranteed to be available?", "booking_guarantee"),
    ("Can you promise I can book a 2 BHK in Vishwajeet Prime today?", "booking_guarantee"),
    ("What offers are available right now for Vishwajeet Prime?", "offers"),
    ("Send me the brochure and floor plan for Vishwajeet Prime.", "documents"),
    ("How much have I paid and what is my outstanding amount?", "customer_finance"),
)


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize(("issue", "family"), LIMITATION_CASES)
def test_complete_limitation_survives_endpoint_postprocessing(support_env, endpoint, issue, family):
    payload, conversation_id = ask(TestClient(api), endpoint, issue)
    answer = payload["answer"].lower()
    assert payload["unsupported_capability"] == family
    assert payload["retrieval_mode"] == "unsupported_capability"
    assert payload["source_status"] == "unavailable"
    assert payload["route"] == "property"
    assert payload["used_llm"] is False
    assert "pending_project_lookup" not in payload
    assert "clarification_entity" not in payload
    assert not payload.get("quick_replies")
    assert "which project should i check" not in answer
    assert get_pending_project_lookup(support_env[conversation_id][-1]["text"]) is None
    if family == "nearby_places":
        assert "don't currently have verified information" in answer
        assert "an approved location data source is not yet integrated" in answer
    elif family == "investment_guarantee":
        assert "cannot guarantee" in answer
        assert "definitely double" not in answer
    elif family == "booking_guarantee":
        assert "can't guarantee" in answer and "not a reservation" in answer
        assert "unit(s) currently listed" not in answer
    elif family == "mortgage_rates":
        assert "mortgage" in answer or "home loan" in answer
        assert "verified" in answer and "rate" in answer
        assert "nearby places" not in answer


@pytest.mark.parametrize(("issue", "family"), LIMITATION_CASES)
def test_limitation_json_streaming_parity(support_env, issue, family):
    client = TestClient(api)
    json_payload, _ = ask(client, ENDPOINTS[0], issue)
    stream_payload, _ = ask(client, ENDPOINTS[1], issue)
    for key in ("answer", "route", "source_status", "retrieval_mode",
                "unsupported_capability", "quick_replies", "pending_project_lookup"):
        assert json_payload.get(key) == stream_payload.get(key), (family, key)


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("issue", [
    "Which hospitals are within 3 km of Vishwajeet Prime?",
    "Will this project's price definitely double in 3 years?",
])
def test_supported_followup_has_no_stale_limitation_selection(support_env, endpoint, issue):
    client = TestClient(api)
    first, conversation_id = ask(client, endpoint, issue)
    assert first["source_status"] == "unavailable"
    assert get_pending_project_lookup(support_env[conversation_id][-1]["text"]) is None
    followup, _ = ask(client, endpoint, "What amenities does Vishwajeet Prime have?", conversation_id)
    assert followup["route"] == "property"
    assert followup["source_status"] == "live_api"
    assert "Badminton" in followup["answer"]
    assert "Vishwajeet Prime" in followup["answer"]
    assert "unsupported_capability" not in followup
    assert get_pending_project_lookup(support_env[conversation_id][-1]["text"]) is None


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_real_project_and_inventory_clarification_continue(support_env, endpoint):
    client = TestClient(api)
    ambiguous, _ = ask(client, endpoint, "What amenities does Vishwajeet Precious have?")
    assert ambiguous["clarification_entity"] == "project"
    assert {reply["label"] for reply in ambiguous["quick_replies"]} == {
        "Vishwajeet Precious(Pearl)", "Vishwajeet Precious (Emerald)",
    }
    missing, _ = ask(client, endpoint, "What amenities are available?")
    assert missing["clarification_entity"] == "project"
    assert missing["pending_project_lookup"]["options"]

    wing, conversation_id = ask(client, endpoint, "Show me available flats in Vishwajeet Prime")
    assert wing["clarification_entity"] == "wing"
    assert [reply["label"] for reply in wing["quick_replies"]] == ["A", "B"]
    floor, _ = ask(client, endpoint, "A", conversation_id)
    assert floor["clarification_entity"] == "floor"
    assert {reply["label"] for reply in floor["quick_replies"]} == {"1", "2"}
    flat, _ = ask(client, endpoint, "1", conversation_id)
    assert flat["clarification_entity"] == "flat"
    assert [reply["label"] for reply in flat["quick_replies"]] == ["101"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_home_type_clarification_continues(support_env, endpoint):
    payload, _ = ask(TestClient(api), endpoint,
                     "What home types are available in Vishwajeet Prime Wing A?")
    assert payload["clarification_entity"] == "home_type"
    assert {reply["label"] for reply in payload["quick_replies"]} == {"2BHK", "3BHK"}
    assert payload["pending_project_lookup"]["entity"] == "home_type"


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_locality_discovery_continues(support_env, endpoint):
    payload, _ = ask(TestClient(api), endpoint, "Show me 3 BHK")
    assert payload["clarification_entity"] == "locality"
    assert {reply["label"] for reply in payload["quick_replies"]} >= {"Pune", "Thane"}


FULL_COST_REQUESTS = (
    "Give me the complete cost sheet including taxes, stamp duty, parking and floor rise.",
    "Give me the full cost breakup",
    "Show me the complete cost sheet",
    "What are all charges including tax and parking?",
    "Give me the final price including every charge",
    "What is the total including stamp duty and floor rise?",
)


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("issue", FULL_COST_REQUESTS)
def test_full_cost_sheet_limitation_preserves_context(support_env, endpoint, issue):
    client = TestClient(api)
    pricing, conversation_id = ask(client, endpoint,
                                  "What is the 3BHK price in Vishwajeet Prime?")
    assert pricing["source_status"] == "live_api"
    assert "base rate" in pricing["answer"].lower()
    assert get_current_project_context(support_env[conversation_id][-1]["text"]) == {
        "project": "Vishwajeet Prime",
    }

    payload, _ = ask(client, endpoint, issue, conversation_id)
    answer = payload["answer"].lower()
    assert payload["unsupported_capability"] == "complete_cost_sheet"
    assert payload["retrieval_mode"] == "unsupported_capability"
    assert payload["source_status"] == "unavailable"
    assert payload["route"] == "property"
    assert payload["used_llm"] is False
    assert "verified complete cost sheet" in answer
    assert "base rate" in answer and "partial" in answer
    assert "inr" not in answer and "%" not in answer
    assert "pending_project_lookup" not in payload
    assert not payload.get("quick_replies")
    assert get_pending_project_lookup(support_env[conversation_id][-1]["text"]) is None

    followup, _ = ask(client, endpoint, "What is the 3BHK base rate?", conversation_id)
    assert followup["source_status"] == "live_api"
    assert "Vishwajeet Prime" in followup["answer"]
    assert "unsupported_capability" not in followup


@pytest.mark.parametrize("issue", FULL_COST_REQUESTS)
def test_full_cost_sheet_json_streaming_parity(support_env, issue):
    client = TestClient(api)
    json_payload, _ = ask(client, ENDPOINTS[0], issue)
    stream_payload, _ = ask(client, ENDPOINTS[1], issue)
    for key in ("answer", "route", "source_status", "retrieval_mode",
                "unsupported_capability", "quick_replies", "pending_project_lookup"):
        assert json_payload.get(key) == stream_payload.get(key), key


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("issue", (
    "What is the base rate in Vishwajeet Prime?",
    "What is the price per sq ft in Vishwajeet Prime?",
    "How much is a 3 BHK in Vishwajeet Prime?",
    "What will be the total cost?",
    "How much does this flat cost?",
    "Give me full details of amenities including parking",
))
def test_ordinary_price_or_flat_estimate_is_not_cost_sheet(support_env, endpoint, issue):
    payload, _ = ask(TestClient(api), endpoint, issue)
    assert payload.get("unsupported_capability") != "complete_cost_sheet"
    if "Vishwajeet Prime" in issue:
        assert payload["source_status"] == "live_api"
        assert "INR" in payload["answer"]


@pytest.mark.parametrize("issue", (
    "Give me full details of amenities including parking",
    "What is the total area including parking?",
    "What is the total cost of this flat?",
))
def test_non_cost_sheet_wording_is_not_classified_as_full_charges(issue):
    assert build_unsupported_capability_assist(SupportAssistRequest(issue=issue)) is None


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_verified_flat_base_estimate_stays_separate_from_all_charge_request(support_env, endpoint):
    client = TestClient(api)
    conversation_id = str(uuid.uuid4())
    for issue in ("Show me available flats in Vishwajeet Prime", "A", "1", "101"):
        detail, _ = ask(client, endpoint, issue, conversation_id)
    assert "saleable area: 1500" in detail["answer"].lower()
    total, _ = ask(client, endpoint, "What will be the total cost?", conversation_id)
    assert total.get("unsupported_capability") != "complete_cost_sheet"
    assert "For Flat 101" in total["answer"]
    assert "estimated base cost" in total["answer"]
    assert "INR 6,000,000" in total["answer"]
    assert total["source_status"] == "live_api"
    assert "base-price estimate" in total["answer"]
    assert "not the final all-inclusive total" in total["answer"]
    assert get_pending_project_lookup(support_env[conversation_id][-1]["text"]) is None

    estimate, _ = ask(client, endpoint, "How much does this flat cost?", conversation_id)
    assert "For Flat 101" in estimate["answer"]
    assert "estimated base cost" in estimate["answer"]
    assert "INR 6,000,000" in estimate["answer"]
    assert estimate.get("unsupported_capability") != "complete_cost_sheet"

    next_price, _ = ask(client, endpoint, "What is the 3BHK base rate?", conversation_id)
    assert "Vishwajeet Prime" in next_price["answer"]
    assert next_price["source_status"] == "live_api"


def test_selected_flat_total_cost_json_streaming_parity(support_env):
    client = TestClient(api)
    responses = []
    for endpoint in ENDPOINTS:
        conversation_id = str(uuid.uuid4())
        for selection in ("Show me available flats in Vishwajeet Prime", "A", "1", "101"):
            ask(client, endpoint, selection, conversation_id)
        response, _ = ask(client, endpoint, "What will be the total cost?", conversation_id)
        responses.append(response)
    for key in ("answer", "source_status", "retrieval_mode", "route", "unsupported_capability"):
        assert responses[0].get(key) == responses[1].get(key), key


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("issue", (
    "How much will it cost?",
    "What would this cost?",
    "What is the total?",
    "How much is it?",
))
def test_short_cost_followups_use_one_selected_live_flat(support_env, endpoint, issue):
    client = TestClient(api)
    conversation_id = str(uuid.uuid4())
    for selection in ("Show me available flats in Vishwajeet Prime", "A", "1", "101"):
        detail, _ = ask(client, endpoint, selection, conversation_id)
    assert "saleable area: 1500" in detail["answer"].lower()

    estimate, _ = ask(client, endpoint, issue, conversation_id)
    assert estimate["source_status"] == "live_api"
    assert "For Flat 101" in estimate["answer"]
    assert "INR 6,000,000 to INR 11,250,000" in estimate["answer"]
    assert "base-price estimate" in estimate["answer"]
    assert "not the final all-inclusive total" in estimate["answer"]
    assert estimate.get("unsupported_capability") != "complete_cost_sheet"
    assert get_pending_project_lookup(support_env[conversation_id][-1]["text"]) is None


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_explicit_flat_cost_and_complete_sheet_stay_separate(support_env, endpoint):
    client = TestClient(api)
    conversation_id = str(uuid.uuid4())
    for selection in ("Show me available flats in Vishwajeet Prime", "A", "1", "101"):
        ask(client, endpoint, selection, conversation_id)
    explicit, _ = ask(client, endpoint, "What is the total cost of this flat?", conversation_id)
    assert "For Flat 101" in explicit["answer"]
    assert "INR 6,000,000 to INR 11,250,000" in explicit["answer"]
    assert "base-price estimate" in explicit["answer"]

    sheet, _ = ask(client, endpoint,
                   "Give me the complete cost sheet including taxes, stamp duty, parking and floor rise.",
                   conversation_id)
    assert sheet["unsupported_capability"] == "complete_cost_sheet"
    assert sheet["source_status"] == "unavailable"
    assert "verified complete cost sheet" in sheet["answer"].lower()
    assert "estimated base cost" not in sheet["answer"].lower()


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_generic_total_cost_does_not_reuse_flat_after_project_change(support_env, endpoint):
    client = TestClient(api)
    conversation_id = str(uuid.uuid4())
    for selection in ("Show me available flats in Vishwajeet Prime", "A", "1", "101"):
        ask(client, endpoint, selection, conversation_id)
    new_scope, _ = ask(client, endpoint, "What is the 3BHK price in Vishwajeet Town?", conversation_id)
    assert "Vishwajeet Town" in new_scope["answer"]
    generic, _ = ask(client, endpoint, "What will be the total cost?", conversation_id)
    assert "For Flat 101" not in generic["answer"]
    assert "estimated base cost" not in generic["answer"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_generic_total_cost_without_selected_flat_does_not_calculate(support_env, endpoint):
    client = TestClient(api)
    fresh, _ = ask(client, endpoint, "What will be the total cost?")
    assert "estimated base cost" not in fresh["answer"]

    _, conversation_id = ask(client, endpoint, "What is the 3BHK price in Vishwajeet Prime?")
    project_only, _ = ask(client, endpoint, "What will be the total cost?", conversation_id)
    assert "estimated base cost" not in project_only["answer"]
    assert "For Flat" not in project_only["answer"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("missing", ("area", "rate"))
def test_generic_total_cost_needs_verified_area_and_rate(support_env, monkeypatch, endpoint, missing):
    if missing == "area":
        units = copy.deepcopy(INVENTORY)
        units[0].pop("saleableArea")
        monkeypatch.setitem(globals(), "INVENTORY", units)
    else:
        typologies = copy.deepcopy(TYPOLOGIES)
        typologies[0]["minBasePrice"] = None
        typologies[0]["maxBasePrice"] = None
        monkeypatch.setitem(globals(), "TYPOLOGIES", typologies)

    client = TestClient(api)
    conversation_id = str(uuid.uuid4())
    for selection in ("Show me available flats in Vishwajeet Prime", "A", "1", "101"):
        detail, _ = ask(client, endpoint, selection, conversation_id)
    assert ("saleable area" not in detail["answer"].lower() if missing == "area"
            else "base rate" not in detail["answer"].lower())

    response, _ = ask(client, endpoint, "What will be the total cost?", conversation_id)
    assert "estimated base cost" not in response["answer"]
    assert "For Flat 101" not in response["answer"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_generic_total_cost_with_two_flat_choices_reasks_flat(support_env, monkeypatch, endpoint):
    monkeypatch.setitem(globals(), "INVENTORY", INVENTORY + [
        {"unitNumber": "103", "floorNumber": 1, "typologyName": "3BHK", "typologyId": 101,
         "saleableArea": 1510, "status": "Available"},
    ])
    client = TestClient(api)
    conversation_id = str(uuid.uuid4())
    for selection in ("Show me available flats in Vishwajeet Prime", "A", "1"):
        choices, _ = ask(client, endpoint, selection, conversation_id)
    assert {reply["label"] for reply in choices["quick_replies"]} == {"101", "103"}

    response, _ = ask(client, endpoint, "What will be the total cost?", conversation_id)
    assert response["clarification_entity"] == "flat"
    assert {reply["label"] for reply in response["quick_replies"]} == {"101", "103"}
    assert "estimated base cost" not in response["answer"]
    assert response["pending_project_lookup"]["entity"] == "flat"


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_cost_sheet_limitation_keeps_discovery_preferences(support_env, endpoint):
    client = TestClient(api)
    first, conversation_id = ask(client, endpoint, "Show me 3 BHK")
    assert first["clarification_entity"] == "locality"
    before = get_discovery_slots(support_env[conversation_id][-1]["text"])
    assert before["config"] == ["3"]

    limitation, _ = ask(client, endpoint, "Show me the complete cost sheet", conversation_id)
    assert limitation["unsupported_capability"] == "complete_cost_sheet"
    after = get_discovery_slots(support_env[conversation_id][-1]["text"])
    assert after["config"] == before["config"]
    assert after["awaiting"] is None

