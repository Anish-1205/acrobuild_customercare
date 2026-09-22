"""Shared "which projects have X?" mechanism (services/acrobuild_company_service.py:
build_project_record_index / filter_project_index), and the two callers that
now go through it instead of their own hand-rolled project loop.

The CS API can add a project before the on-disk snapshot is regenerated for
it (services/acrobuild_company_service.py's snapshot fallback then has no
data for that one project). Before this fix, a single project's live-and-
snapshot failure raised uncaught out of the per-project loop and aborted the
entire catalogue-wide scan -- every "which projects have X?" question, for
any field. These tests pin the fix: one project's failure is skipped, not
fatal, and every remaining project is still checked correctly.
"""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from services import acrobuild_company_service as service
from services import amenity_search_service as amenity
from services import property_clarification_service as clarification
from services import project_home_type_service as home
from routers import assist
from graph.main_orchestrator import TurnContext
from services.turn_analysis_service import TurnAnalysis
from app import api

PROJECTS = [
    {"id": 1, "projectName": "Vishwajeet Alpha", "address": "Thane"},
    {"id": 2, "projectName": "Vishwajeet Beta", "address": "Thane"},
    {"id": 3, "projectName": "Vishwajeet Gamma", "address": "Thane"},
]


def _failing_fetcher(good, exception=RuntimeError("CS API request timed out.")):
    def fetch(project_id):
        if project_id not in good:
            raise exception
        return good[project_id]
    return fetch


def test_build_project_record_index_skips_failing_projects():
    fetcher = _failing_fetcher({1: ["a"], 3: ["c"]})
    index, failed = service.build_project_record_index(fetcher, projects=PROJECTS)
    assert set(index.keys()) == {1, 3}
    assert [project["id"] for project, _error in failed] == [2]


def test_build_project_record_index_only_catches_runtime_and_timeout_errors():
    def fetch(_project_id):
        raise ValueError("not a live-data failure")
    with __import__("pytest").raises(ValueError):
        service.build_project_record_index(fetch, projects=PROJECTS)


def test_filter_project_index_matches_all_and_reports_per_value():
    index = {
        1: {"project": PROJECTS[0], "records": {"gym", "pool"}},
        2: {"project": PROJECTS[1], "records": {"gym"}},
        3: {"project": PROJECTS[2], "records": {"pool"}},
    }
    matches, per_value = service.filter_project_index(
        index, lambda entry: entry["records"], ["gym", "pool"])
    assert [project["projectName"] for project in matches] == ["Vishwajeet Alpha"]
    assert [p["projectName"] for p in per_value["gym"]] == ["Vishwajeet Alpha", "Vishwajeet Beta"]
    assert [p["projectName"] for p in per_value["pool"]] == ["Vishwajeet Alpha", "Vishwajeet Gamma"]


def test_home_type_catalogue_filter_survives_one_project_failing(monkeypatch):
    monkeypatch.setattr(home, "get_company_projects", lambda: PROJECTS)
    # Project 2 (Beta) fails to fetch entirely; Alpha and Gamma both list 3BHK.
    monkeypatch.setattr(home, "get_project_typologies", _failing_fetcher({
        1: [{"typologyName": "3BHK"}],
        3: [{"typologyName": "3BHK"}],
    }))
    result = home.build_catalogue_home_type_answer("which projects offer 3bhk?")
    assert result["pending_project_lookup"]["options"] == ["Vishwajeet Alpha", "Vishwajeet Gamma"]
    assert "could not be checked" in result["answer"]
    assert "Vishwajeet Beta" in result["answer"]  # named as the skipped project


def test_home_type_catalogue_filter_clean_when_nothing_fails(monkeypatch):
    monkeypatch.setattr(home, "get_company_projects", lambda: PROJECTS)
    monkeypatch.setattr(home, "get_project_typologies", lambda _id: [{"typologyName": "3BHK"}])
    result = home.build_catalogue_home_type_answer("which projects offer 3bhk?")
    assert "could not be checked" not in result["answer"]
    assert set(result["pending_project_lookup"]["options"]) == {
        "Vishwajeet Alpha", "Vishwajeet Beta", "Vishwajeet Gamma"}


def test_live_amenity_index_survives_one_project_failing(monkeypatch):
    monkeypatch.setattr(amenity, "get_company_projects", lambda: PROJECTS)
    monkeypatch.setattr(amenity, "get_project_amenities", _failing_fetcher({
        1: [{"iconName": "Gym"}],
        3: [{"iconName": "Gym"}],
    }))
    index = amenity.live_amenity_index()
    assert set(index.keys()) == {1, 3}
    assert index[1]["amenities"] == ["Gym"]


# -----------------------------------
# "WHICH PROJECTS HAVE A 3BHK?" MUST REACH THE CATALOGUE FILTER
# -----------------------------------
# Reported dead end: this phrasing came back as "Which project should I
# check?" with every project offered as an unfiltered choice, instead of the
# catalogue-wide filter's matched subset. Traced and could not reproduce
# against the current detector/builder (is_catalogue_home_type_query() does
# match this text; see test below), including live end-to-end -- these pin
# the detector and the full-stack routing so a future regression here fails
# loudly instead of silently falling back to an unfiltered clarification.


@pytest.mark.parametrize("issue", [
    "which projects have a 3bhk?",
    "which projects have a 3bhk",
    "Which projects have a 3bhk?",
    "which project have a 3bhk?",
    "which projects have 3bhk?",
    "which projects has a 3bhk?",
    "which projects offer 3bhk?",
    # Plural "3bhks" -- requested_home_types()'s regex required a word
    # boundary straight after "bhk", which a trailing "s" broke, so the
    # number was silently dropped from detection entirely.
    "which projects have 3bhks?",
    "which projects offer 3bhks?",
    # "these/them/those" refer back to a shown project set without ever
    # saying "project(s)"; is_catalogue_home_type_query() required that word
    # literally and missed every phrasing below.
    "which one of these has 3bhks?",
    "which one of these has a 3bhk?",
    "which of these has 3bhk?",
    "any of these have 3bhk?",
    "any of these have a 3bhk?",
    "out of these which have 3bhk?",
    "out of these, which have a 3bhk?",
])
def test_which_projects_have_a_bhk_is_detected_as_catalogue_query(issue):
    assert home.is_catalogue_home_type_query(issue)


@pytest.mark.parametrize("issue,expected", [
    ("3bhk", ["3"]),
    ("3bhks", ["3"]),
    ("3 bhks", ["3"]),
    ("2bhks and 3bhks", ["2", "3"]),
])
def test_requested_home_types_recognizes_plural_bhks(issue, expected):
    assert home.requested_home_types(issue) == expected


NINE_PROJECTS = [
    {"id": index, "projectName": f"Vishwajeet Project {index}", "address": "Thane"}
    for index in range(1, 10)
]


@pytest.mark.parametrize("endpoint", ["/api/support/assist", "/api/support/assist/stream"])
@pytest.mark.parametrize("issue", [
    "which projects have a 3bhk?",
    "which one of these has 3bhks?",
    "any of these have a 3bhk?",
    "out of these, which have a 3bhk?",
])
def test_which_projects_have_a_bhk_returns_filtered_list_not_full_catalogue(endpoint, issue, monkeypatch):
    # Every project has 2BHK; only the first three also have 3BHK -- a real
    # unfiltered "pick a project" clarification would offer all 9, so
    # asserting fewer than 9 options proves this went through the filter.
    monkeypatch.setattr(clarification, "get_company_projects", lambda: NINE_PROJECTS)
    monkeypatch.setattr(home, "get_company_projects", lambda: NINE_PROJECTS)
    monkeypatch.setattr(home, "get_project_typologies", lambda project_id: (
        [{"typologyName": "3BHK"}, {"typologyName": "2BHK"}] if project_id <= 3
        else [{"typologyName": "2BHK"}]
    ))
    monkeypatch.setattr(assist, "prepare_turn", lambda issue, *_a: TurnContext(
        [], issue, TurnAnalysis("property", "English", "latin", "test", unsure=False), issue,
    ))
    monkeypatch.setattr(assist, "_complete_payload", lambda payload, *_a: payload)

    class Session:
        def __init__(self, *_a): pass
        def set_cookie(self, *_a): pass
        def load(self): return []
        def append(self, *_a, **_kw): pass

    monkeypatch.setattr(assist, "ConversationSession", Session)
    response = TestClient(api).post(endpoint, json={"issue": issue})
    assert response.status_code == 200
    payload = response.json() if not endpoint.endswith("stream") else next(
        event["response"] for event in map(json.loads, response.text.splitlines()) if event["type"] == "done")

    assert payload["clarification_entity"] == "project"
    options = payload["pending_project_lookup"]["options"]
    assert options == ["Vishwajeet Project 1", "Vishwajeet Project 2", "Vishwajeet Project 3"]
    assert len(options) < len(NINE_PROJECTS)
