"""Synonyms for every kind of CS API data: amenities (all 43 live names), prices, floors, RERA, possession."""
import pytest

from api_context import _AMENITY_HINT_RE, requested_amenities
from services.vocabulary import canonicalize

LIVE_AMENITIES = [
    "24x7 Electricity Supply", "24x7 Water Supply", "Acupressure Park", "Baby Swimming Area", "Badminton",
    "CCTV Coverage", "Carrom", "Children's Playing Area", "Community House", "Earthquake Resistant",
    "Entrance Lobby", "Fire Alarm", "Fire Fighting Tools Ready", "Football Ground", "Gas Pipe", "Gated Community",
    "Gym", "Internet", "Jogging Track", "Lift", "Maintenance", "Multipurpose Hall", "Park", "Parking", "Party Lawn",
    "Paved Walkway", "Pool & Billiards", "Power Backup Lift", "Rain Water Harvesting", "Security Personnel",
    "Senior Citizen Friendly", "Sewage Water Treatment", "Solar Water Heater", "Street Lamps", "Swimming Pool",
    "Table Tennis Court", "Telecom Connection", "Terrace", "Trash Handling", "Visitor Parking",
    "Waste Management System", "Water Connection", "Yoga & Meditation Area",
]


@pytest.mark.parametrize("asked, expected", [
    ("swimming pool", ["Swimming Pool"]),
    ("flat with tarantal", ["Swimming Pool"]),
    ("swiming pool wala project", ["Swimming Pool"]),
    ("pool and billiards", ["Pool & Billiards"]),
    ("kids pool", ["Baby Swimming Area"]),
    ("fitness centre", ["Gym"]),
    ("clubhouse", ["Community House"]),
    ("community house", ["Community House"]),
    ("bacchon ke liye play area", ["Children's Playing Area"]),
    ("garden", ["Park"]),
    ("bagicha", ["Park"]),
    ("watchman", ["Security Personnel"]),
    ("bijli backup", ["Power Backup Lift"]),
    ("generator", ["Power Backup Lift"]),
    ("24 hour paani", ["24x7 Water Supply"]),
    ("guest parking", ["Visitor Parking"]),
    ("car parking", ["Parking"]),
    ("piped gas", ["Gas Pipe"]),
    ("wifi", ["Internet"]),
    ("stp", ["Sewage Water Treatment"]),
    ("kachra", ["Waste Management System"]),
    ("fire safety", ["Fire Alarm", "Fire Fighting Tools Ready"]),
    ("elderly friendly", ["Senior Citizen Friendly"]),
    ("ping pong", ["Table Tennis Court"]),
    ("street lights", ["Street Lamps"]),
    ("geyser", ["Solar Water Heater"]),
    ("earthquake proof", ["Earthquake Resistant"]),
])
def test_amenity_synonyms_reach_live_names(asked, expected):
    text = canonicalize(asked)  # the router canonicalizes before matching; amenity words must survive it
    assert _AMENITY_HINT_RE.search(text), text
    assert requested_amenities(text, LIVE_AMENITIES) == expected


@pytest.mark.parametrize("text", ["ready to move 2bhk", "walking distance from station", "what is the system",
                                  "price of 2bhk"])
def test_ordinary_words_do_not_trigger_an_amenity_lookup(text):
    assert not _AMENITY_HINT_RE.search(canonicalize(text))


@pytest.mark.parametrize("asked, canonical", [
    ("price list of prime", "price"), ("rate card", "price"), ("kitne ka hai 2bhk", "price"),
    ("cost sheet", "price"), ("how many storeys", "floor"), ("kitne manzil", "floor"),
    ("maharera number", "rera"), ("registration number of prime", "rera"),
    ("ready possession flats", "ready to move"), ("tayyar flat", "ready to move"),
    ("possession date", "possession"), ("token amount", "payment plan"), ("festive offer", "offers"),
    ("phone number of office", "contact"),
])
def test_data_synonyms_canonicalize(asked, canonical):
    assert canonical in canonicalize(asked)


def test_customer_amenity_word_beats_a_wrong_rewrite(monkeypatch):
    from unittest.mock import patch
    from graph import main_orchestrator as orchestrator
    from services.turn_analysis_service import TurnAnalysis
    wrong = TurnAnalysis("property", "Hindi", "latin", "llm", english="I want a flat with a terrace")
    monkeypatch.setattr(orchestrator, "_project_names_for_turn", lambda: [])
    with patch.object(orchestrator, "analyze_turn", return_value=wrong):
        turn = orchestrator.prepare_turn("tarantal wala flat chahiye")
    assert "terrace" not in turn.property_issue
    assert requested_amenities(turn.property_issue, LIVE_AMENITIES) == ["Swimming Pool"]
