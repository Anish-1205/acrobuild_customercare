"""Defences against the CS API's known data and availability problems (2026-10-29 audit)."""
import pytest

from services import cs_records


def test_record_cleaning():
    projects = cs_records.clean_projects([
        {"id": 1, "projectName": " Vishwajeet  Prime ", "city": "Thane "}, {"id": None, "projectName": "x"},
        {"id": 2, "projectName": "  "}, "junk"])
    assert projects == [{"id": 1, "projectName": "Vishwajeet Prime", "city": "Thane"}]
    wings = cs_records.clean_wings([{"id": 5, "name": "A ", "totalFloors": 0}, {"id": 6, "totalFloors": "12"}])
    assert [(w["name"] if "name" in w else None, w["totalFloors"]) for w in wings] == [("A", None), (None, 12)]
    typology = cs_records.clean_typologies([{"id": 9, "typologyType": "3BHK ", "carpetArea": 1900,
                                             "saleableArea": 731, "minBasePrice": 8000, "maxBasePrice": 4000}])[0]
    assert (typology["typologyType"], typology["carpetArea"], typology["saleableArea"]) == ("3BHK", 731, 1900)
    assert (typology["minBasePrice"], typology["maxBasePrice"]) == (4000, 8000)
    lone = cs_records.clean_typologies([{"id": 1, "minBasePrice": 0, "maxBasePrice": 3500}])[0]
    assert (lone["minBasePrice"], lone["maxBasePrice"]) == (3500, 3500)


def test_duplicate_units_counted_once():
    units = [{"id": 1, "wingId": 7, "unitNumber": 201, "floorNumber": 2, "typologyId": 3},
             {"id": 2, "wingId": 7, "unitNumber": 201, "floorNumber": 2, "typologyId": 3},  # repeated unit 201
             {"id": 1, "wingId": 7, "unitNumber": 201, "floorNumber": 2, "typologyId": 3},  # same row twice
             {"id": 3, "wingId": 7, "unitNumber": 202, "floorNumber": 2, "typologyId": 3}]
    assert [u["id"] for u in cs_records.clean_inventory(units)] == [1, 3]


def test_amenity_and_plan_names():
    assert cs_records.amenity_name(" Mantainence ") == "Maintenance"
    assert cs_records.amenity_name("Enterance Lobby") == "Entrance Lobby"
    assert cs_records.plan_name("1% To be paid to the promoter as Booking Amount", "Construction Linked") \
        == "Construction Linked plan"
    assert cs_records.plan_name("Prime Payment Schedule", "Construction Linked") == "Prime Payment Schedule"


def test_orphan_flats_are_relinked_and_counted_per_wing(monkeypatch):
    import api_context
    monkeypatch.setattr(api_context, "get_project_wings", lambda pid: [{"id": 70, "name": "A"}, {"id": 71, "name": "B"}])
    monkeypatch.setattr(api_context, "get_project_typologies", lambda pid: [
        {"id": 188, "wingId": 70, "typologyName": "2BHK 1254(SQ.FT)"},
        {"id": 189, "wingId": 71, "typologyName": "3BHK 1944(SQ.FT)"}])
    inventory = {70: [{"id": 1, "unitNumber": 205, "typologyId": 189},          # wing A flat, wing B home type
                      {"id": 2, "unitNumber": 206, "typologyId": 999, "typologyName": "2BHK 1254(SQ.FT)"},  # by name
                      {"id": 3, "unitNumber": 207, "typologyId": 998}],          # unknown: can't be priced
                 71: [{"id": 4, "unitNumber": 101, "typologyId": 189}]}
    monkeypatch.setattr(api_context, "get_wing_inventory", lambda wid, available_only=True: inventory[wid])
    wings, by_wing, available = api_context._project_listing({"id": 57})
    assert available == {(70, 189): 1, (70, 188): 1, (71, 189): 1}
    assert {t["id"] for t in by_wing[70]} == {188, 189}


def test_circuit_breaker_fails_fast_after_repeated_timeouts(monkeypatch):
    import urllib.request
    import services.acrobuild_company_service as cs
    attempts = []

    class Opener:
        def open(self, request, timeout=None):
            attempts.append(request.full_url)
            raise TimeoutError()

    monkeypatch.setattr(cs, "CS_API_KEY", "k")
    monkeypatch.setattr(cs, "log_data_api_call", lambda **kw: None)
    monkeypatch.setattr(cs, "_BREAKER", {"failures": 0, "open_until": 0.0})
    monkeypatch.setattr(urllib.request, "build_opener", lambda *a: Opener())
    for _ in range(cs.BREAKER_FAILURES):
        with pytest.raises(RuntimeError, match="timed out"):
            cs._request_json("/api/cs/projects")
    tried = len(attempts)
    with pytest.raises(RuntimeError, match="paused"):
        cs._request_json("/api/cs/projects")
    assert len(attempts) == tried  # no network call while the breaker is open


@pytest.mark.parametrize("error, hint", [
    ('{"status":404,"error":"Not Found"}', "routes may have changed"),
    ('{"status":400,"error":"Bad Request"}', "company id"),
    ("CS API request timed out.", "Network problem"),
])
def test_contract_check_explains_failures(monkeypatch, error, hint):
    import services.acrobuild_company_service as cs
    monkeypatch.setattr(cs, "CS_API_KEY", "k")
    monkeypatch.setattr(cs, "_CONTRACT_CHECK", {"at": 0.0, "result": None})

    def fail(path, params=None):
        raise RuntimeError(error)
    monkeypatch.setattr(cs, "_request_json", fail)
    result = cs.check_cs_api_contract()
    assert result["status"] == "failed" and hint in result["hint"]


def test_chat_and_explorer_list_only_projects_with_flats(monkeypatch):
    from fastapi.testclient import TestClient
    import app
    from services import flow_service
    import services.acrobuild_company_service as cs
    monkeypatch.setattr(cs, "_SELLABLE", {"at": 0.0, "items": None})
    monkeypatch.setattr(cs, "get_company_projects", lambda: [{"id": 1, "projectName": "Real"},
                                                             {"id": 2, "projectName": "Empty shell"},
                                                             {"id": 3, "projectName": "API down"}])

    def wings(pid):
        if pid == 3:
            raise RuntimeError("timed out")
        return [{"id": 9}] if pid == 1 else []
    monkeypatch.setattr(cs, "get_project_wings", wings)
    monkeypatch.setattr(cs, "is_cs_api_configured", lambda: True)
    assert [p["projectName"] for p in flow_service._sellable_projects()] == ["Real", "API down"]
    explorer = TestClient(app.api).get("/api/property-flow/projects").json()
    assert [p["projectName"] for p in explorer["items"]] == ["Real", "API down"]  # same list, one journey


def test_explorer_booking_keeps_wing_and_flat(monkeypatch):
    from datetime import date
    from services import action_registry, flow_service
    booked = []
    monkeypatch.setattr(flow_service, "_projects", lambda: [{"id": 1, "projectName": "Vishwajeet Town"}])
    monkeypatch.setattr(flow_service, "_sellable_projects", lambda: [{"id": 1, "projectName": "Vishwajeet Town"}])
    monkeypatch.setitem(action_registry.ACTIONS, "book_site_visit",
                        (action_registry.SiteVisitRequest, lambda r: booked.append(r) or {"ticket_id": "T1"}))
    today, flow = date(2026, 10, 29), None
    for message in ("Book a site visit at Vishwajeet Town, wing Astra C, flat 305", "tomorrow", "11am",
                    "Priya", "9876543210", "priya@example.com"):
        reply, flow = flow_service.step(flow, message, today=today)
    assert "• Wing: Astra C\n• Flat: 305" in reply["answer"]
    flow_service.step(flow, reply["choices"][0]["value"], today=today)
    assert (booked[0].wing_name, booked[0].unit_number, booked[0].project_name) == ("Astra C", "305", "Vishwajeet Town")
