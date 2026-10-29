from datetime import date, datetime

from services.home_finder import (
    Criteria,
    bhk_of,
    describe_match,
    parse_criteria,
    project_in_place,
    project_matches,
    relaxations,
)

PLACES = {"Pune", "Thane", "Wakad", "Ambernath", "Kharadi"}
TODAY = date(2026, 10, 29)
READY_MS = int(datetime(2026, 6, 30).timestamp() * 1000)   # already passed
LATER_MS = int(datetime(2030, 3, 31).timestamp() * 1000)


def test_parse_criteria_like_buyers_write():
    c = parse_criteria("im looking for a 2bhk under 50 lakh in pune", PLACES)
    assert (c.place, c.bhk, c.budget_max) == ("pune", 2.0, 5_000_000)
    c = parse_criteria("2000sqft best locality", PLACES)
    assert c.size == 2000 and c.place == "" and c.any()
    c = parse_criteria("budget 40-55 lakhs ready to move in Wakad", PLACES)
    assert (c.budget_min, c.budget_max, c.ready, c.place) == (4_000_000, 5_500_000, True, "wakad")
    assert parse_criteria("1 crore 3 bhk", PLACES).budget_max == 10_000_000
    assert parse_criteria("1 RK flat", PLACES).bhk == 0.5
    assert parse_criteria("property in mumbai", PLACES).place == "mumbai"
    assert parse_criteria("navi mumbai flats", PLACES).place == "navi mumbai"
    assert not parse_criteria("what are your office timings?", PLACES).any()
    assert parse_criteria("2000sqft", PLACES).size == 2000 and parse_criteria("1500 sq ft", PLACES).size == 1500


def test_broken_english_and_number_words():
    c = parse_criteria("flt in puna undr fifty lac do bhk", PLACES)
    assert (c.place, c.bhk, c.budget_max) == ("pune", 2.0, 5_000_000)
    assert parse_criteria("2 bhk in Poona", PLACES).place == "pune"
    assert parse_criteria("teen bhk pachas lakh", PLACES).bhk == 3.0
    assert parse_criteria("teen bhk pachas lakh", PLACES).budget_max == 5_000_000
    assert parse_criteria("homes in Kharadhi", PLACES).place == "kharadi"
    assert parse_criteria("1500 sq feets", PLACES).size == 1500
    assert parse_criteria("budget 1 karod", PLACES).budget_max == 10_000_000
    assert parse_criteria("less than 50 lakh", PLACES).place == ""  # "than" is not Thane
    assert parse_criteria("want a pure veg society", PLACES).place == ""  # "pure" is not Pune


def test_typo_tolerant_names_amenities_and_dates():
    from datetime import date
    from api_context import requested_amenities
    from services.acrobuild_company_service import resolve_project_from_text
    from services.flow_service import is_booking_request, parse_date
    projects = [{"id": 50, "projectName": "Vishwajeet Empire"}, {"id": 57, "projectName": "Vishwajeet Prime"},
                {"id": 51, "projectName": "Vishwajeet Paradise"}]
    assert resolve_project_from_text(projects, "vishwajit emipre price")["id"] == 50
    assert resolve_project_from_text(projects, "paradice amenities")["id"] == 51
    assert resolve_project_from_text(projects, "what is the price") is None  # "price" is not "Prime"
    assert requested_amenities("swiming pool", {"Swimming Pool", "Gym"}) == ["Swimming Pool"]
    assert parse_date("tommorow", date(2026, 10, 29)) == "2026-10-30"
    assert parse_date("sunady", date(2026, 10, 29)) == "2026-11-01"
    assert is_booking_request("i want to book a vist")


def test_synonyms_reach_one_canonical_word():
    from services.vocabulary import canonicalize
    assert canonicalize("what features and facilities does it have") == "what amenities and amenities does it have"
    assert canonicalize("cost of 2bhk, kimat batao") == "price of 2bhk, price batao"
    assert canonicalize("how many blocks / buildings") == "how many wing / wing"
    assert canonicalize("carpet area of 1bhk apartment") == "size of 1bhk flat"
    assert canonicalize("booking amount kitna hai") == "payment plan kitna hai"  # not "booking price"
    assert canonicalize("Metro City Towers kahan hai", protected=["Metro City Towers"]) == "Metro City Towers location hai"
    assert canonicalize("properties in pune") == "properties in pune"  # left alone: answers look for "properties"


def test_several_bhks_and_size_edge_cases():
    assert parse_criteria("2 or 3 bhk in pune", PLACES).bhks == (2.0, 3.0)
    assert parse_criteria("2bhk and 3bhk details", PLACES).bhks == (2.0, 3.0)
    assert parse_criteria("2/3 BHK", PLACES).describe() == "2BHK or 3BHK homes"
    assert parse_criteria("1 rk or 1bhk", PLACES).bhks == (0.5, 1.0)
    c = parse_criteria("above 1200 sqft carpet", PLACES)
    assert (c.size_min, c.carpet) == (1200, True)
    assert parse_criteria("1.2k sqft", PLACES).size == 1200
    assert round(parse_criteria("100 sq m", PLACES).size) == 1076
    assert parse_criteria("between 40 and 60 lakh", PLACES).budget_min == 4_000_000
    assert parse_criteria("₹45,00,000", PLACES).budget_max == 4_500_000
    assert parse_criteria("size 1000 and 50 lakh", PLACES).describe() == "homes around 1,000 sq ft under ₹50 lakh"
    assert parse_criteria("wakad or hinjewadi", PLACES).places == ("wakad", "hinjewadi")
    assert parse_criteria("flat in magarpatta", PLACES).place == "magarpatta"


def test_bhk_from_typology_labels():
    assert bhk_of({"typologyType": "2BHK+T", "typologyName": "2BHK+T 1320(SQ.FT)"}) == 2.0
    assert bhk_of({"typologyType": "1 RK", "typologyName": ""}) == 0.5
    assert bhk_of({"typologyType": "Shop", "typologyName": "Shop 1087(SQ.FT)"}) is None


def _project():
    project = {"id": 54, "projectName": "Vishwajeet Myspace", "city": "Pune", "locality": "Wakad"}
    wings = [{"id": 1, "expectedPossesionDate": LATER_MS}, {"id": 2, "expectedPossesionDate": READY_MS}]
    typologies = {
        1: [{"id": 10, "typologyType": "2BHK", "saleableArea": 1254, "minBasePrice": 3400, "maxBasePrice": 4300},
            {"id": 11, "typologyType": "Shop", "saleableArea": 900, "minBasePrice": 9000, "maxBasePrice": 9000}],
        2: [{"id": 20, "typologyType": "1BHK", "saleableArea": 775, "minBasePrice": 2800, "maxBasePrice": 3500},
            {"id": 21, "typologyType": "3BHK", "saleableArea": 2100, "minBasePrice": 4000, "maxBasePrice": 5000}],
    }
    available = {(1, 10): 12, (1, 11): 3, (2, 20): 5}  # by (wing, home type); the 3BHK is sold out
    return project, wings, typologies, available


def test_matching_by_bhk_budget_size_and_readiness():
    project, wings, typologies, available = _project()
    two = project_matches(project, wings, typologies, available, Criteria(bhk=2), TODAY)
    assert two["bhks"] == [2.0] and two["available"] == 12
    assert round(two["price_min"]) == 1254 * 3400 and round(two["price_max"]) == 1254 * 4300
    assert project_matches(project, wings, typologies, available, Criteria(bhk=2, budget_max=40e5), TODAY) is None
    assert project_matches(project, wings, typologies, available, Criteria(size=2000), TODAY) is None  # sold out
    ready = project_matches(project, wings, typologies, available, Criteria(ready=True), TODAY)
    assert ready["bhks"] == [1.0] and ready["ready"]
    line = describe_match(two)
    assert line.startswith("Vishwajeet Myspace (Wakad, Pune): 2BHK, 1,254 sq ft, approx. ₹43 lakh - ₹54 lakh")
    assert ", from approx. ₹43 lakh," in describe_match(two, budget_set=True)
    assert Criteria(bhk=2, budget_max=50e5, place="pune").describe() == "2BHK homes under ₹50 lakh in Pune"
    assert line.endswith("possession Mar 2030, 12 listed")


def test_place_and_relaxation_order():
    assert project_in_place({"city": "Thane", "address": "Pale Village, Ambernath East"}, "ambernath")
    assert not project_in_place({"city": "Pune", "locality": "Wakad"}, "thane")
    steps = relaxations(Criteria(place="pune", bhk=2, size=2000, budget_max=50e5, ready=True))
    assert [label for label, _ in steps] == ["size", "budget", "ready to move", "BHK"]
    assert all(c.place == "pune" for _, c in steps)
    assert steps[-1][1].any()  # the place alone still searches
