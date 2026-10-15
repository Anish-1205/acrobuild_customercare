import json
import re

import pytest
from fastapi.testclient import TestClient

from app import api
from graph import haystack_conversation_pipeline as pipeline
from graph import main_orchestrator as orchestrator
from routers import assist
from services import project_home_type_service as home
from services import property_clarification_service as clarification
from services.acrobuild_company_service import resolve_project_candidates_from_text
from services.turn_analysis_service import TurnAnalysis
from services.conversation_store_service import (
    build_current_project_marker, build_home_type_scope_marker,
    get_current_project_context, get_home_type_scope, get_pending_project_lookup,
    latest_home_type_scope,
)


PROJECTS = [{"id": 1, "projectName": "Vishwajeet Empire"},
            {"id": 2, "projectName": "Vishwajeet Empire NX"}]


@pytest.fixture
def catalogue(monkeypatch):
    monkeypatch.setattr(pipeline, "get_live_project_names", lambda: [p["projectName"] for p in PROJECTS])
    monkeypatch.setattr(home, "get_company_projects", lambda: PROJECTS)
    monkeypatch.setattr(clarification, "get_company_projects", lambda: PROJECTS)
    monkeypatch.setattr(home, "get_project_typologies", lambda project_id: [
        {"id": 20, "typologyName": "2BHK", "carpetArea": 620, "minBasePrice": 5000, "rateType": "PerSqft"},
        *([{"id": 30, "typologyName": "3BHK", "carpetArea": 900}] if project_id == 1 else []),
    ])
    monkeypatch.setattr(home, "get_project_wings", lambda _id: [{"id": 30}])
    monkeypatch.setattr(home, "get_wing_inventory", lambda _id: [{"typologyId": 20, "typologyName": "2BHK"}])


@pytest.fixture
def no_amenity_lookup(monkeypatch):
    """Keep non-amenity endpoint tests independent of the live amenity catalogue."""
    monkeypatch.setattr(assist, "live_amenity_index", lambda: {})


def test_full_suffix_and_ambiguous_fragment():
    assert resolve_project_candidates_from_text(PROJECTS, "Empire") == PROJECTS
    assert resolve_project_candidates_from_text(PROJECTS, "Vishwajeet Empire NX") == [PROJECTS[1]]
    assert resolve_project_candidates_from_text(PROJECTS, "Vishwajeet Empire") == [PROJECTS[0]]


@pytest.mark.parametrize("question", ["2bhk matrame cheppu", "indhulo 2bk and 3bhk details cheppu", "3bhk levva?"])
def test_followups_keep_nx_and_every_type(catalogue, question):
    history = [{"sender": "customer", "text": "Tell me about Vishwajeet Empire NX"},
               {"sender": "bot", "text": "Home types in Vishwajeet Empire NX: 2BHK"}]
    resolved = pipeline.resolve_contextual_support_issue(question, history)
    assert "Requested project: Vishwajeet Empire NX" in resolved
    assert home.requested_home_types(resolved) == home.requested_home_types(question)


def test_compound_and_absent_types(catalogue):
    result = home.build_project_home_type_answer("2bk and 3bhk details in Vishwajeet Empire NX")
    assert "2BHK: 1 unit(s)" in result["answer"]
    assert "3BHK: Not listed" in result["answer"]
    assert "Vishwajeet Empire NX" in result["answer"]
    assert not pipeline.validate_support_answer("2BHK and 3BHK in Vishwajeet Empire NX", result["answer"])


def test_listed_type_without_available_units(catalogue, monkeypatch):
    monkeypatch.setattr(home, "get_wing_inventory", lambda _id: [])
    result = home.build_project_home_type_answer("2BHK in Vishwajeet Empire NX")
    assert "configuration is listed, but no units" in result["answer"]


def test_small_home_type_result_shows_direct_grounded_detail(catalogue):
    result = home.build_project_home_type_answer("Do you have 2BHK in Vishwajeet Empire NX?")
    assert "1 unit(s) currently listed as available" in result["answer"]
    assert "carpet area: 620 sq. ft." in result["answer"]
    assert "API-listed base rate: INR 5,000 to INR 5,000 (PerSqft)" in result["answer"]
    assert "concise overview" not in result["answer"]


def _large_typology_catalogue(monkeypatch):
    records = [
        {"id": 1, "wingId": 10, "typologyName": "3BHK 1000", "typologyType": "3BHK",
         "carpetArea": 700, "saleableArea": 1000, "rateType": "Rate Per Sq.Ft.",
         "minBasePrice": 4000, "maxBasePrice": 7500},
        {"id": 2, "wingId": 11, "typologyName": "3BHK 1000", "typologyType": "3BHK",
         "carpetArea": 700, "saleableArea": 1000, "rateType": "Rate Per Sq.Ft.",
         "minBasePrice": 4000, "maxBasePrice": 7500},
        {"id": 3, "wingId": 10, "typologyName": "3BHK 1100", "typologyType": "3BHK",
         "carpetArea": 720, "saleableArea": 1100, "rateType": "Rate Per Sq.Ft.",
         "minBasePrice": 4000, "maxBasePrice": 7500},
        {"id": 4, "wingId": 10, "typologyName": "3BHK Duplex 1500", "typologyType": "3BHK Duplex",
         "carpetArea": 900, "saleableArea": 1500, "rateType": "Rate Per Sq.Ft.",
         "minBasePrice": 4000, "maxBasePrice": 8000},
        {"id": 5, "wingId": 11, "typologyName": "3BHK Duplex 1600", "typologyType": "3BHK Duplex",
         "carpetArea": 920, "saleableArea": 1600, "rateType": "Rate Per Sq.Ft.",
         "minBasePrice": 4000, "maxBasePrice": 8000},
        {"id": 6, "wingId": 10, "typologyName": "3BHK 900", "typologyType": "3BHK",
         "carpetArea": 800, "saleableArea": 1900, "rateType": "Rate Per Sq.Ft.",
         "minBasePrice": 4000, "maxBasePrice": 7500},
        {"id": 7, "wingId": 10, "typologyName": "3BHK 1900", "typologyType": "3BHK",
         "carpetArea": 800, "saleableArea": 1900, "rateType": "Rate Per Sq.Ft.",
         "minBasePrice": 4000, "maxBasePrice": 7500},
    ]
    monkeypatch.setattr(home, "get_company_projects", lambda: [{"id": 9, "projectName": "Large Project"}])
    monkeypatch.setattr(home, "get_project_typologies", lambda _id: records)
    monkeypatch.setattr(home, "get_project_wings", lambda _id: [
        {"id": 10, "name": "A"}, {"id": 11, "name": "B"},
    ])
    monkeypatch.setattr(home, "get_wing_inventory", lambda wing_id: [
        {"id": record["id"] * 10, "typologyId": record["id"], "typologyName": record["typologyName"]}
        for record in records if record["wingId"] == wing_id
    ])


def test_large_home_type_result_summarizes_without_losing_distinct_facts(monkeypatch):
    _large_typology_catalogue(monkeypatch)
    answer = home.build_project_home_type_answer("Do you have 3BHK in Large Project?")["answer"]
    assert "7 unit(s) currently listed as available" in answer
    assert "5 distinct area/rate variants" in answer
    assert "3BHK: 3 distinct area/rate variant(s)" in answer
    assert "3BHK Duplex: 2 distinct area/rate variant(s)" in answer
    assert "saleable area 1,000 to 1,900 sq. ft." in answer
    assert "show all 3BHK details" in answer
    assert "source labels: 3BHK 900 / 3BHK 1900" not in answer
    assert "differing or conflicting source labels" in answer


def test_explicit_complete_details_groups_equivalents_and_retains_differences(monkeypatch):
    _large_typology_catalogue(monkeypatch)
    answer = home.build_project_home_type_answer("Show all 3BHK details in Large Project")["answer"]
    assert answer.count("available unit(s) linked to this variant") == 5
    assert "wings: A, B; carpet area: 700 sq. ft.; saleable area: 1,000 sq. ft." in answer
    assert "3BHK Duplex; wing: A; carpet area: 900 sq. ft.; saleable area: 1,500 sq. ft." in answer
    assert "3BHK Duplex; wing: B; carpet area: 920 sq. ft.; saleable area: 1,600 sq. ft." in answer
    assert "source labels: 3BHK 900 / 3BHK 1900" in answer


def test_short_complete_detail_followup_restores_customer_bhk_and_server_project(monkeypatch):
    _large_typology_catalogue(monkeypatch)
    history = [
        {"sender": "customer", "text": "Do you have 3BHK?"},
        {"sender": "bot", "text": "Concise summary" + build_current_project_marker("Large Project")},
    ]
    answer = home.build_project_home_type_answer("show all details", history)["answer"]
    assert "Home types in Large Project" in answer
    assert answer.count("available unit(s) linked to this variant") == 5


def test_contextual_duplex_followup_keeps_project_and_bhk(monkeypatch):
    _large_typology_catalogue(monkeypatch)
    history = [
        {"sender": "customer", "text": "Do you have 3BHK?"},
        {"sender": "bot", "text": "Concise summary" + build_current_project_marker("Large Project")},
    ]
    payload = home.build_project_home_type_answer("only duplex", history)
    assert payload is not None
    assert "3BHK Duplex" in payload["answer"]
    assert "3BHK 1000" not in payload["answer"]
    assert "2 unit(s) currently listed as available" in payload["answer"]


def test_contextual_duplex_not_found_does_not_treat_plus_t_as_duplex(monkeypatch):
    _large_typology_catalogue(monkeypatch)
    original = home.get_project_typologies
    monkeypatch.setattr(home, "get_project_typologies", lambda project_id: [
        *original(project_id),
        {"id": 10, "wingId": 10, "typologyName": "2BHK+T 1350", "typologyType": "2BHK+T",
         "carpetArea": 700, "saleableArea": 1350, "rateType": "Rate Per Sq.Ft.",
         "minBasePrice": 4000, "maxBasePrice": 7000},
    ])
    history = [
        {"sender": "customer", "text": "What about 2BHK?"},
        {"sender": "bot", "text": "2BHK summary" + build_current_project_marker("Large Project")},
    ]
    payload = home.build_project_home_type_answer("show duplex options", history)
    assert payload is not None
    assert "no 2BHK Duplex" in payload["answer"]
    assert "2BHK+T" not in payload["answer"]


def test_short_price_followup_is_scoped_and_formats_rates(monkeypatch):
    _large_typology_catalogue(monkeypatch)
    history = [
        {"sender": "customer", "text": "What about 3BHK?"},
        {"sender": "bot", "text": "3BHK summary" + build_current_project_marker("Large Project")},
    ]
    builder = getattr(home, "build_project_home_type_price_answer", lambda *_a: None)
    payload = builder("how much?", history)
    assert payload is not None
    assert "Pricing for 3BHK in Large Project" in payload["answer"]
    assert "INR 4,000 to INR 8,000" in payload["answer"]
    assert "INR 4000.0" not in payload["answer"]
    assert "5BHK" not in payload["answer"]


def test_price_after_successful_duplex_scope_stays_duplex(monkeypatch):
    _large_typology_catalogue(monkeypatch)
    marker = build_current_project_marker("Large Project") + build_home_type_scope_marker(
        {"project": "Large Project", "config": ["3"], "subtype": "duplex"},
    )
    history = [{"sender": "bot", "text": "Duplex options" + marker}]
    payload = home.build_project_home_type_price_answer("what about the rate?", history)
    assert "Pricing for 3BHK Duplex in Large Project" in payload["answer"]
    assert "INR 4,000 to INR 8,000" in payload["answer"]
    assert "INR 7,500" not in payload["answer"]


def test_unsuccessful_duplex_does_not_replace_valid_bhk_scope(monkeypatch):
    _large_typology_catalogue(monkeypatch)
    original = home.get_project_typologies
    monkeypatch.setattr(home, "get_project_typologies", lambda project_id: [
        *original(project_id),
        {"id": 9, "wingId": 10, "typologyName": "2BHK 1200", "typologyType": "2BHK",
         "carpetArea": 650, "saleableArea": 1200, "rateType": "Rate Per Sq.Ft.",
         "minBasePrice": 3500, "maxBasePrice": 6500},
    ])
    marker = build_current_project_marker("Large Project") + build_home_type_scope_marker(
        {"project": "Large Project", "config": ["2"]},
    )
    history = [{"sender": "bot", "text": "2BHK options" + marker}]
    unavailable = home.build_project_home_type_answer("only duplex", history)
    assert unavailable["home_type_scope"] == {"project": "Large Project", "config": ["2"]}
    history.append({"sender": "customer", "text": "only duplex"})
    history.append({"sender": "bot", "text": unavailable["answer"] + marker})
    price = home.build_project_home_type_price_answer("price?", history)
    assert "Pricing for 2BHK" in price["answer"]
    assert "Duplex" not in price["answer"]


def test_ambiguous_duplex_scope_uses_home_type_clarification(monkeypatch):
    _large_typology_catalogue(monkeypatch)
    original = home.get_project_typologies
    monkeypatch.setattr(home, "get_project_typologies", lambda project_id: [
        *original(project_id),
        {"id": 8, "wingId": 10, "typologyName": "5BHK Duplex 2500", "typologyType": "5BHK Duplex",
         "carpetArea": 1800, "saleableArea": 2500, "rateType": "Rate Per Sq.Ft.",
         "minBasePrice": 5000, "maxBasePrice": 9000},
    ])
    history = [{"sender": "bot", "text": "Project overview" + build_current_project_marker("Large Project")}]
    payload = home.build_project_home_type_answer("show duplex options", history)
    assert payload["clarification_entity"] == "home_type"
    assert [reply["label"] for reply in payload["quick_replies"]] == ["3BHK Duplex", "5BHK Duplex"]
    assert payload["pending_project_lookup"]["purpose"] == "home_type_scope"
    resumed = clarification.resume_selection(payload["pending_project_lookup"], "3BHK Duplex")
    assert "Requested home types: 3BHK" in resumed
    assert "Requested subtype: Duplex" in resumed
    assert "Selected project: Large Project" in resumed


def test_home_type_scope_marker_is_validated_and_customer_text_is_ignored():
    marker = build_home_type_scope_marker(
        {"project": "Large Project", "config": ["3", "3", "9"], "subtype": "Duplex"},
    )
    assert get_home_type_scope(marker) == {
        "project": "Large Project", "config": ["3"], "subtype": "duplex",
    }
    messages = [{"sender": "customer", "text": marker}]
    assert latest_home_type_scope(messages) == {}
    assert get_home_type_scope(assist._home_type_scope_marker({}, reset=True)) == {}


def test_complete_pricing_details_retains_every_distinct_scoped_plan(monkeypatch):
    _large_typology_catalogue(monkeypatch)
    marker = build_current_project_marker("Large Project") + build_home_type_scope_marker(
        {"project": "Large Project", "config": ["3"], "subtype": "duplex"},
    )
    history = [{"sender": "bot", "text": "Duplex prices" + marker}]
    payload = home.build_project_home_type_price_answer("show all pricing details", history)
    assert payload["answer"].count("API-listed base rate:") == 2
    assert "saleable area: 1,500 sq. ft." in payload["answer"]
    assert "saleable area: 1,600 sq. ft." in payload["answer"]


def test_ambiguous_more_details_does_not_invent_home_type_intent(monkeypatch):
    _large_typology_catalogue(monkeypatch)
    history = [
        {"sender": "customer", "text": "Do you have 3BHK?"},
        {"sender": "bot", "text": "Concise summary" + build_current_project_marker("Large Project")},
    ]
    assert home.build_project_home_type_answer("more details", history) is None


def test_large_home_type_summary_localizes_without_changing_grounded_numbers(monkeypatch):
    _large_typology_catalogue(monkeypatch)
    payload = home.build_project_home_type_answer("Do you have 3BHK in Large Project?")

    def translate(**kwargs):
        source = kwargs["user_prompt"].split("ENGLISH MESSAGE:\n", 1)[1]
        return source.replace("Home types in", "Home types unnayi in")

    monkeypatch.setattr(orchestrator, "generate_qwen_chat_response", translate)
    localized = orchestrator.localize_response(payload, TurnAnalysis("property", "Telugu", "latin", "test"))
    assert localized["answer"].startswith("Home types unnayi in Large Project:")
    assert "7 unit(s) currently listed as available" in localized["answer"]
    assert "saleable area 1,000 to 1,900 sq. ft." in localized["answer"]
    assert "API-listed base rate INR 4,000 to 7,500" in localized["answer"]


def test_marathi_localization_translates_bullets_while_preserving_facts(monkeypatch):
    _large_typology_catalogue(monkeypatch)
    payload = home.build_project_home_type_answer("Do you have 3BHK in Large Project?")

    def translate(**kwargs):
        source = kwargs["user_prompt"].split("ENGLISH MESSAGE:\n", 1)[1]
        return (source
                .replace("Home types in", "घरांचे प्रकार")
                .replace("currently listed as available", "सध्या उपलब्ध म्हणून सूचीबद्ध")
                .replace("distinct area/rate variants are listed", "वेगवेगळे क्षेत्रफळ/दर पर्याय सूचीबद्ध आहेत")
                .replace("Here is a concise overview", "हा संक्षिप्त आढावा आहे")
                .replace("carpet area", "कार्पेट क्षेत्रफळ")
                .replace("saleable area", "विक्रीयोग्य क्षेत्रफळ"))

    monkeypatch.setattr(orchestrator, "generate_qwen_chat_response", translate)
    localized = orchestrator.localize_response(payload, TurnAnalysis("property", "Marathi", "native", "test"))
    assert localized["answer"].startswith("घरांचे प्रकार")
    assert "Large Project" in localized["answer"]
    assert "3BHK Duplex" in localized["answer"]
    assert "7 unit(s)" in localized["answer"]
    assert "API-listed base rate INR 4,000 to 8,000" in localized["answer"]


def test_romanized_marathi_structured_answer_recovers_from_flattened_echo(monkeypatch):
    _large_typology_catalogue(monkeypatch)
    payload = home.build_project_home_type_answer("Do you have 3BHK in Large Project?")

    def translate(**kwargs):
        prompt = kwargs["user_prompt"]
        if "ENGLISH FRAGMENTS:\n" in prompt:
            lines = json.loads(prompt.split("ENGLISH FRAGMENTS:\n", 1)[1])
            translated = [
                line.replace("Home types in", "Gharanche prakar")
                .replace("currently listed as available", "sadhya uplabdh mhanun nondlele")
                .replace("distinct area/rate variants are listed", "vegvegale area/rate paryay nondlele aahet")
                .replace("distinct area/rate variant(s)", "vegvegale area/rate paryay")
                .replace("Here is a concise overview", "Ha sankshipt aadhava aahe")
                .replace("carpet area", "carpet area")
                .replace("saleable area", "saleable area")
                .replace("Ask me to show all", "Sampurna mahitisathi mala vichara")
                for line in lines
            ]
            return json.dumps([
                value if value != source or len(re.findall(r"[A-Za-z]+", source)) < 3
                else "Marathi " + source
                for source, value in zip(lines, translated)
            ])
        source = prompt.split("ENGLISH MESSAGE:\n", 1)[1]
        return " ".join(source.splitlines())

    monkeypatch.setattr(orchestrator, "generate_qwen_chat_response", translate)
    localized = orchestrator.localize_response(
        payload, TurnAnalysis("property", "Marathi", "latin", "test"),
    )

    assert localized["answer"].startswith("Large Project madhil gharanche prakar:")
    assert localized["answer"].count("\n") == payload["answer"].count("\n")
    assert localized["answer"].count("\n  - ") == payload["answer"].count("\n  - ")
    assert "3BHK Duplex" in localized["answer"]
    assert "7 unit(s)" in localized["answer"]
    assert "saleable area 1,000 te 1,900 sq. ft." in localized["answer"]
    assert "API-listed base rate INR 4,000 te 8,000" in localized["answer"]


def _romanized_marathi_translator(**kwargs):
    prompt = kwargs["user_prompt"]
    if "ENGLISH FRAGMENTS:\n" in prompt:
        lines = json.loads(prompt.split("ENGLISH FRAGMENTS:\n", 1)[1])
        translated = []
        for line in lines:
            value = (
                line.replace("Home types in", "Ya projectmadhil gharanche prakar")
                .replace("currently listed as available", "sadhya uplabdh mhanun nondlele aahet")
                .replace("distinct area/rate variants are listed", "vegvegale area/rate paryay nondlele aahet")
                .replace("Here is a concise overview", "Ha sankshipt aadhava aahe")
                .replace("carpet area", "carpet kshetrafal")
                .replace("saleable area", "saleable kshetrafal")
                .replace("available unit(s) linked to this variant", "ya paryayashi jodaleli uplabdh unit(s)")
                .replace("Pricing for", "Yasathi kimat")
                .replace("listed plan variant(s)", "nondlele plan variant(s)")
                .replace("These are", "He")
                .replace("not all-inclusive home quotations", "sarva kharchansahit gharache quotation nahi")
                .replace("Ask for all pricing details", "Sampurna pricing mahitisathi vichara")
                .replace("Ask me to show all", "Sampurna mahitisathi mala vichara")
            )
            translated.append(
                value if value != line or len(re.findall(r"[A-Za-z]+", line)) < 3
                else "Marathi " + line
            )
        return json.dumps(translated)
    source = prompt.split("ENGLISH MESSAGE:\n", 1)[1]
    return source.replace("Pricing for", "Yasathi kimat")


def test_romanized_marathi_complete_details_duplex_and_price_keep_exact_facts(monkeypatch):
    _large_typology_catalogue(monkeypatch)
    monkeypatch.setattr(orchestrator, "generate_qwen_chat_response", _romanized_marathi_translator)
    analysis = TurnAnalysis("property", "Marathi", "latin", "test")

    details = home.build_project_home_type_answer("Show all 3BHK details in Large Project")
    localized_details = orchestrator.localize_response(details, analysis)["answer"]
    assert localized_details.count("ya variant-shi jodaleli available unit(s)") == 5
    assert "3BHK Duplex; wing: A; carpet area: 900 sq. ft.; saleable area: 1,500 sq. ft." in localized_details
    assert "3BHK Duplex; wing: B; carpet area: 920 sq. ft.; saleable area: 1,600 sq. ft." in localized_details

    history = [{"sender": "bot", "text": "scope" + build_current_project_marker("Large Project")
                + build_home_type_scope_marker({"project": "Large Project", "config": ["3"]})}]
    duplex = home.build_project_home_type_answer("only duplex", history)
    localized_duplex = orchestrator.localize_response(duplex, analysis)["answer"]
    assert localized_duplex.startswith("Large Project madhil gharanche prakar:")
    assert "3BHK Duplex: 2 unit(s)" in localized_duplex
    assert "INR 4,000 te INR 8,000" in localized_duplex
    assert "INR 7,500" not in localized_duplex

    scoped_history = [{"sender": "bot", "text": "scope" + build_current_project_marker("Large Project")
                       + build_home_type_scope_marker(
                           {"project": "Large Project", "config": ["3"], "subtype": "duplex"},
                       )}]
    price = home.build_project_home_type_price_answer("how much?", scoped_history)
    localized_price = orchestrator.localize_response(price, analysis)["answer"]
    assert localized_price.startswith("Large Project madhil 3BHK Duplex chi kimat:")
    assert "INR 4,000 te INR 8,000 (Rate Per Sq.Ft.)" in localized_price
    assert "INR 7,500" not in localized_price


@pytest.mark.parametrize("corruption", ["drop", "duplicate", "invent_number"])
def test_structured_localization_rejects_corrupted_fact_occurrences(monkeypatch, corruption):
    _large_typology_catalogue(monkeypatch)
    payload = home.build_project_home_type_answer("Do you have 3BHK in Large Project?")
    analysis = TurnAnalysis("property", "Marathi", "latin", "test")

    if corruption in {"drop", "duplicate"}:
        masked, replacements = orchestrator._mask_translation_facts(payload["answer"], ["Large Project"])
        token = next(iter(replacements))
        unsafe = masked.replace(token, "", 1) if corruption == "drop" else masked + " " + token
        assert orchestrator._restore_valid_translation(
            payload["answer"], unsafe, replacements, analysis,
        ) == ""
        return

    masked, replacements = orchestrator._mask_translation_facts(payload["answer"], ["Large Project"])
    assert orchestrator._restore_valid_translation(
        payload["answer"], masked + " 999", replacements, analysis,
    ) == ""


def test_romanized_marathi_inventory_answer_has_json_stream_parity(monkeypatch, no_amenity_lookup):
    _large_typology_catalogue(monkeypatch)
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", "false")
    monkeypatch.setattr(
        orchestrator, "analyze_turn",
        lambda *_a: TurnAnalysis(
            "property", "Marathi", "latin", "test", "Do you have 3BHK in Large Project?",
        ),
    )
    monkeypatch.setattr(orchestrator, "generate_qwen_chat_response", _romanized_marathi_translator)
    monkeypatch.setattr(assist, "_enforce_live_property_data", lambda payload, *_a: payload)
    monkeypatch.setattr(assist, "evaluate_rag_response", lambda *_a: {})
    histories = {}

    class Session:
        def __init__(self, _cookie, conversation_id): self.conversation_id = conversation_id
        def set_cookie(self, *_a): pass
        def load(self):
            return list(histories.setdefault(self.conversation_id, [
                {"sender": "bot", "text": "Selected" + build_current_project_marker("Large Project")},
            ]))
        def append(self, question, answer, marker=""):
            histories[self.conversation_id].extend([
                {"sender": "customer", "text": question},
                {"sender": "bot", "text": answer + marker},
            ])

    monkeypatch.setattr(assist, "ConversationSession", Session)
    answers = []
    with TestClient(api) as client:
        for endpoint in ("/api/support/assist", "/api/support/assist/stream"):
            response = client.post(endpoint, json={
                "issue": "Ya project madhye 3BHK aahe ka?",
                "conversation_id": "marathi-" + endpoint.rsplit("/", 1)[-1],
            })
            assert response.status_code == 200
            payload = response.json() if not endpoint.endswith("stream") else next(
                event["response"] for event in map(json.loads, response.text.splitlines())
                if event["type"] == "done"
            )
            assert payload["reply_language"] == "Marathi"
            assert payload["source_status"] == "live_api"
            assert {reply["action"] for reply in payload["quick_replies"]} == {
                "browse_projects", "site_visit", "ticket",
            }
            answers.append(payload["answer"])
    assert answers[0] == answers[1]
    assert answers[0].startswith("Large Project madhil gharanche prakar:")


def test_localization_falls_back_when_an_immutable_fact_is_dropped(monkeypatch):
    _large_typology_catalogue(monkeypatch)
    payload = home.build_project_home_type_answer("Do you have 3BHK in Large Project?")

    def unsafe_translate(**kwargs):
        source = kwargs["user_prompt"].split("ENGLISH MESSAGE:\n", 1)[1]
        return re.sub(r"ZXQ[A-Z]+QXZ", "", source, count=1)

    monkeypatch.setattr(orchestrator, "generate_qwen_chat_response", unsafe_translate)
    localized = orchestrator.localize_response(payload, TurnAnalysis("property", "Marathi", "native", "test"))
    assert localized["answer"] == payload["answer"]


@pytest.mark.parametrize("endpoint", ["/api/support/assist", "/api/support/assist/stream"])
def test_large_home_type_summary_has_endpoint_parity_and_terminal_actions(endpoint, monkeypatch, no_amenity_lookup):
    _large_typology_catalogue(monkeypatch)
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", "false")
    history = []
    monkeypatch.setattr(orchestrator, "analyze_turn", lambda *_a: TurnAnalysis("property", "English", "latin", "test"))
    monkeypatch.setattr(assist, "_enforce_live_property_data", lambda payload, *_a: payload)
    monkeypatch.setattr(assist, "evaluate_rag_response", lambda *_a: {})

    class Session:
        def __init__(self, *_a): pass
        def set_cookie(self, *_a): pass
        def load(self): return list(history)
        def append(self, question, answer, marker=""):
            history.extend([{"sender": "customer", "text": question},
                            {"sender": "bot", "text": answer + marker}])

    monkeypatch.setattr(assist, "ConversationSession", Session)
    with TestClient(api) as client:
        response = client.post(endpoint, json={"issue": "Do you have 3BHK in Large Project?"})
        followup_response = client.post(endpoint, json={"issue": "show all details"})
    assert response.status_code == 200
    payload = response.json() if not endpoint.endswith("stream") else next(
        event["response"] for event in map(json.loads, response.text.splitlines()) if event["type"] == "done")
    followup = followup_response.json() if not endpoint.endswith("stream") else next(
        event["response"] for event in map(json.loads, followup_response.text.splitlines()) if event["type"] == "done")
    assert "5 distinct area/rate variants" in payload["answer"]
    assert followup["answer"].count("available unit(s) linked to this variant") == 5
    assert {reply["action"] for reply in payload["quick_replies"]} == {
        "browse_projects", "site_visit", "ticket",
    }
    assert get_current_project_context(history[-1]["text"]) == {"project": "Large Project"}


@pytest.mark.parametrize("endpoint", ["/api/support/assist", "/api/support/assist/stream"])
@pytest.mark.parametrize("discovery_enabled", ["true", "false"])
def test_contextual_duplex_then_price_has_endpoint_and_flag_parity(endpoint, discovery_enabled, monkeypatch):
    _large_typology_catalogue(monkeypatch)
    monkeypatch.setenv("ACROBUILD_DISCOVERY_SLOTS", discovery_enabled)
    marker = build_current_project_marker("Large Project") + build_home_type_scope_marker(
        {"project": "Large Project", "config": ["3"]},
    )
    history = [{"sender": "customer", "text": "Do you have 3BHK in Large Project?"},
               {"sender": "bot", "text": "3BHK summary" + marker}]
    monkeypatch.setattr(orchestrator, "analyze_turn", lambda *_a: TurnAnalysis("property", "English", "latin", "test"))
    monkeypatch.setattr(assist, "_enforce_live_property_data", lambda payload, *_a: payload)
    monkeypatch.setattr(assist, "evaluate_rag_response", lambda *_a: {})

    class Session:
        def __init__(self, *_a): pass
        def set_cookie(self, *_a): pass
        def load(self): return list(history)
        def append(self, question, answer, marker=""):
            history.extend([{"sender": "customer", "text": question},
                            {"sender": "bot", "text": answer + marker}])

    monkeypatch.setattr(assist, "ConversationSession", Session)

    def ask(client, question):
        response = client.post(endpoint, json={"issue": question, "conversation_id": "scope-parity"})
        assert response.status_code == 200
        return response.json() if not endpoint.endswith("stream") else next(
            event["response"] for event in map(json.loads, response.text.splitlines()) if event["type"] == "done")

    with TestClient(api) as client:
        duplex = ask(client, "only duplex")
        price = ask(client, "how much?")

    assert "3BHK Duplex" in duplex["answer"] and "3BHK 1000" not in duplex["answer"]
    assert "Pricing for 3BHK Duplex in Large Project" in price["answer"]
    assert "INR 4,000 to INR 8,000" in price["answer"]
    assert "INR 7,500" not in price["answer"]
    assert latest_home_type_scope(history) == {
        "project": "Large Project", "config": ["3"], "subtype": "duplex",
    }


def test_home_type_project_selection_preserves_original_question_intent(catalogue):
    state = {"kind": "selection", "entity": "project", "original_issue": "Do you have 3BHK?",
             "options": ["Vishwajeet Empire", "Vishwajeet Empire NX"], "scope": {},
             "purpose": "home_type_search"}
    assert clarification.resume_selection(state, "Vishwajeet Empire NX") == (
        "Do you have 3BHK? Selected project: Vishwajeet Empire NX"
    )


def test_catalogue_home_type_filter_lists_only_matching_projects(catalogue):
    for question in ("what properties have 3bhk?", "which project has 3 BHK?"):
        result = home.build_catalogue_home_type_answer(question)
        assert result["pending_project_lookup"]["options"] == ["Vishwajeet Empire"]
        assert "Vishwajeet Empire NX" not in result["answer"]
    state = result["pending_project_lookup"]
    assert clarification.resume_selection(state, "Vishwajeet Empire") == (
        "which project has 3 BHK? Selected project: Vishwajeet Empire"
    )


def test_catalogue_home_type_filter_has_honest_no_match(catalogue):
    result = home.build_catalogue_home_type_answer("which projects have 4bhk?")
    assert "None of the projects" in result["answer"]
    assert not result.get("pending_project_lookup")
    assert not result.get("quick_replies")


def test_validator_checks_all_types_and_suffix(catalogue):
    failures = pipeline.validate_support_answer("2BHK and 3BHK in Vishwajeet Empire NX", "2BHK in Vishwajeet Empire")
    assert "3 BHK" in failures and "requested project" in failures
    assert "requested project" in pipeline.validate_support_answer(
        "2BHK in Vishwajeet Empire", "2BHK in Vishwajeet Empire NX")


def test_explicit_new_project_and_portfolio_search(catalogue):
    history = [{"sender": "customer", "text": "Vishwajeet Empire NX"}]
    for issue in ["3BHK in Vishwajeet Empire", "Which projects have 3BHK?"]:
        assert pipeline.resolve_contextual_support_issue(issue, history) == issue


def test_durable_current_project_survives_answers_that_omit_its_name(catalogue):
    marker = build_current_project_marker("Vishwajeet Empire NX")
    assert get_current_project_context("Short answer" + marker) == {"project": "Vishwajeet Empire NX"}
    history = [
        {"sender": "bot", "text": "Overview" + marker},
        {"sender": "customer", "text": "is there a 3bhk in this project?"},
        {"sender": "bot", "text": "I could not find a 3 BHK option in the latest project data."},
    ]
    assert pipeline.resolve_contextual_support_issue("2bhk?", history).endswith(
        "Requested project: Vishwajeet Empire NX"
    )


def test_catalogue_marker_explicitly_clears_older_project(catalogue):
    history = [
        {"sender": "bot", "text": "Overview" + build_current_project_marker("Vishwajeet Empire NX")},
        {"sender": "bot", "text": "Choose a matching project" + build_current_project_marker("")},
    ]
    assert pipeline._conversation_project_name(history) == ""


@pytest.mark.parametrize("endpoint", ["/api/support/assist", "/api/support/assist/stream"])
def test_endpoint_followups_and_handoff(endpoint, catalogue, monkeypatch):
    monkeypatch.setattr(orchestrator, "analyze_turn", lambda *_a: TurnAnalysis("property", "English", "latin", "test"))
    monkeypatch.setattr(assist, "_enforce_live_property_data", lambda payload, *_a: payload)
    monkeypatch.setattr(assist, "evaluate_rag_response", lambda *_a: {})
    history = [{"sender": "customer", "text": "Tell me about Vishwajeet Empire NX"},
               {"sender": "bot", "text": "Vishwajeet Empire NX overview"}]

    class Session:
        def __init__(self, *_a): pass
        def set_cookie(self, *_a): pass
        def load(self): return history
        def append(self, question, answer, marker="", **_kw):
            history.extend([{"sender": "customer", "text": question}, {"sender": "bot", "text": answer + marker}])

    monkeypatch.setattr(assist, "ConversationSession", Session)
    with TestClient(api) as client:
        for question in ["2bhk matrame cheppu", "indhulo 2bk and 3bhk details cheppu", "3bhk levva?"]:
            response = client.post(endpoint, json={"issue": question})
            assert response.status_code == 200
            payload = response.json() if not endpoint.endswith("stream") else next(
                e["response"] for e in map(json.loads, response.text.splitlines()) if e["type"] == "done")
            assert "Vishwajeet Empire NX" in payload["answer"]
            assert not payload.get("pending_project_lookup")
            assert {o["action"] for o in payload["quick_replies"]} == {"ticket", "site_visit", "browse_projects"}
            assert next(o for o in payload["quick_replies"] if o["action"] == "site_visit")["project_name"] == "Vishwajeet Empire NX"
            for number in home.requested_home_types(question):
                assert f"{number}BHK:" in payload["answer"]


@pytest.mark.parametrize("endpoint", ["/api/support/assist", "/api/support/assist/stream"])
def test_real_selection_sequence_and_bare_followup(endpoint, catalogue, monkeypatch, no_amenity_lookup):
    history = []
    monkeypatch.setattr(orchestrator, "analyze_turn", lambda *_a: TurnAnalysis("property", "English", "latin", "test"))
    monkeypatch.setattr(assist, "_enforce_live_property_data", lambda payload, *_a: payload)
    monkeypatch.setattr(assist, "evaluate_rag_response", lambda *_a: {})

    overview = {
        "answer": "Full overview for Vishwajeet Empire NX", "route": "property",
        "source_status": "live_api", "agent_mode": "knowledge_retrieval", "used_llm": False,
        "matched_chunks": [{"record_kind": "company_api", "project": PROJECTS[1], "body_text": "overview"}],
    }
    monkeypatch.setattr(assist, "run_support_orchestration", lambda **_kw: dict(overview))
    monkeypatch.setattr(assist, "stream_support_orchestration_events",
                        lambda **_kw: iter([{"type": "done", "response": dict(overview)}]))

    class Session:
        def __init__(self, *_a): pass
        def set_cookie(self, *_a): pass
        def load(self): return list(history)
        def append(self, question, answer, marker=""):
            # Reproduce the clean response that omitted the project name while
            # retaining server-only state.
            visible = ("I could not find a 3 BHK option in the latest project data."
                       if question == "is there a 3bhk in this project?" else answer)
            history.extend([{"sender": "customer", "text": question},
                            {"sender": "bot", "text": visible + marker}])

    monkeypatch.setattr(assist, "ConversationSession", Session)

    def ask(client, question):
        response = client.post(endpoint, json={"issue": question, "conversation_id": "selection-sequence"})
        assert response.status_code == 200
        return response.json() if not endpoint.endswith("stream") else next(
            event["response"] for event in map(json.loads, response.text.splitlines()) if event["type"] == "done")

    with TestClient(api) as client:
        choices = ask(client, "what projects do you have?")
        selected_name = next(choice["value"] for choice in choices["quick_replies"]
                             if choice["value"] == "Vishwajeet Empire NX")
        selected = ask(client, selected_name)
        assert not selected.get("pending_project_lookup")
        assert get_current_project_context(history[-1]["text"]) == {"project": selected_name}
        ask(client, "is there a 3bhk in this project?")
        assert "Vishwajeet Empire NX" not in history[-1]["text"].split("\u2063", 1)[0]
        bare = ask(client, "2bhk?")
        assert "Home types in Vishwajeet Empire NX" in bare["answer"]
        assert not bare.get("pending_project_lookup")


@pytest.mark.parametrize("endpoint", ["/api/support/assist", "/api/support/assist/stream"])
def test_catalogue_filter_then_selection_over_http(endpoint, catalogue, monkeypatch, no_amenity_lookup):
    history = []
    monkeypatch.setattr(orchestrator, "analyze_turn", lambda *_a: TurnAnalysis("property", "English", "latin", "test"))
    monkeypatch.setattr(assist, "_enforce_live_property_data", lambda payload, *_a: payload)
    monkeypatch.setattr(assist, "evaluate_rag_response", lambda *_a: {})

    class Session:
        def __init__(self, *_a): pass
        def set_cookie(self, *_a): pass
        def load(self): return list(history)
        def append(self, question, answer, marker=""):
            history.extend([{"sender": "customer", "text": question},
                            {"sender": "bot", "text": answer + marker}])

    monkeypatch.setattr(assist, "ConversationSession", Session)
    with TestClient(api) as client:
        def ask(question):
            response = client.post(endpoint, json={"issue": question, "conversation_id": "type-filter"})
            payload = response.json() if not endpoint.endswith("stream") else next(
                event["response"] for event in map(json.loads, response.text.splitlines()) if event["type"] == "done")
            return payload

        filtered = ask("what properties have 3bhk?")
        assert [choice["value"] for choice in filtered["quick_replies"]] == ["Vishwajeet Empire"]
        assert get_current_project_context(history[-1]["text"]) == {"project": ""}
        selected = ask("Vishwajeet Empire")
        assert "3BHK:" in selected["answer"]
        assert "could not verify one live answer" not in selected["answer"].lower()
        assert not selected.get("pending_project_lookup")


def test_detail_dispatch_does_not_erase_home_types(monkeypatch):
    from services import ai_agent_service as agent
    chunk = {"source_key": "acrobuild-cs-project-2", "project_name": "Vishwajeet Empire NX"}
    received = []
    monkeypatch.setattr(agent, "_legacy_build_company_api_direct_answer",
                        lambda issue, *_a, **_kw: received.append(issue) or "answer")
    issue = "2BHK and 3BHK details in Vishwajeet Empire NX"
    agent.build_company_api_direct_answer(issue, [chunk])
    assert received == [issue]


def test_compound_scope_survives_repeated_inventory_failures(catalogue, monkeypatch):
    from services import property_clarification_service as clarification
    original = "Show 2BHK and 3BHK details"
    state = {"kind": "selection", "entity": "project", "original_issue": original,
             "options": [p["projectName"] for p in PROJECTS], "scope": {}}
    effective = clarification.resume_selection(state, "Vishwajeet Empire NX")

    def unavailable(_id):
        raise RuntimeError("temporarily unavailable")

    monkeypatch.setattr(home, "get_wing_inventory", unavailable)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            home.build_project_home_type_answer(effective)
        state = get_pending_project_lookup(assist._project_lookup_marker(
            {"source_status": "failed"}, state, original, shortcut_failed=True))
        assert state["original_issue"] == original
        assert state["scope"]["project"] == "Vishwajeet Empire NX"
        assert clarification.resume_selection(state, "retry") == effective
    monkeypatch.setattr(home, "get_wing_inventory", lambda _id: [])
    answer = home.build_project_home_type_answer(effective)["answer"]
    assert "2BHK:" in answer and "3BHK:" in answer


# -----------------------------------
# NUMBERLESS "WHAT BHKS ARE AVAILABLE" FOLLOW-UPS
# -----------------------------------
# A BHK question with no specific number ("what bhks are available") named no
# type, so requested_home_types() found nothing and the query fell through
# every numbered builder straight to the general pipeline -- which could
# re-ask "which project?" (offering only the one project already in scope)
# instead of the missing wing.


@pytest.mark.parametrize("issue,expected", [
    ("what bhks are available in this project ?", True),
    ("which home types are available?", True),
    ("what configurations does it have?", True),
    ("what bhk options are there?", True),
    ("what is the price of 2bhk?", False),  # numbered -- existing builders own this
    ("which projects have bhk options available?", False),  # catalogue-wide, not one project
    ("hello", False),
])
def test_generic_home_type_query_detection(issue, expected):
    assert home.is_generic_home_type_query(issue) is expected


def test_generic_home_type_query_asks_for_wing_not_project(catalogue, monkeypatch):
    # Multiple named wings and no wing named in the question or history --
    # the missing piece is the wing, not the (already unambiguous) project.
    # apply_clarification_contract()/live_options() resolve wings through
    # services/property_clarification_service.py's own imported binding, a
    # separate name from project_home_type_service's.
    monkeypatch.setattr(clarification, "get_project_wings", lambda _id: [
        {"id": 30, "name": "Venus A"}, {"id": 31, "name": "Jupiter C"},
    ])
    history = [{"sender": "customer", "text": "Vishwajeet Empire NX"},
               {"sender": "bot", "text": "Choose a wing in Vishwajeet Empire NX."}]
    result = home.build_generic_home_type_answer(
        "what bhks are available in this project ?", history)
    assert result["clarification_entity"] == "wing"
    assert result["answer"].splitlines()[0] == "Which wing should I check in Vishwajeet Empire NX?"
    assert [choice["value"] for choice in result["quick_replies"]] == ["Venus A", "Jupiter C"]


def test_generic_home_type_query_resolves_directly_with_one_wing(catalogue, monkeypatch):
    # A single wing is auto-selected, so the question resolves straight to
    # the live home types instead of asking to choose a wing.
    monkeypatch.setattr(clarification, "get_project_wings", lambda _id: [{"id": 30, "name": "Only Wing"}])
    monkeypatch.setattr(clarification, "get_wing_inventory", lambda _id: [
        {"unitNumber": "101", "floorNumber": 1, "typologyName": "1BHK"},
        {"unitNumber": "102", "floorNumber": 1, "typologyName": "2BHK"},
    ])
    history = [{"sender": "customer", "text": "Vishwajeet Empire NX"}]
    result = home.build_generic_home_type_answer(
        "what bhks are available in this project ?", history)
    assert result["clarification_entity"] == "home_type"
    assert "2BHK" in result["answer"]


@pytest.mark.parametrize("endpoint", ["/api/support/assist", "/api/support/assist/stream"])
def test_generic_bhk_followup_over_http_asks_for_wing(endpoint, catalogue, monkeypatch, no_amenity_lookup):
    monkeypatch.setattr(orchestrator, "analyze_turn", lambda *_a: TurnAnalysis("property", "English", "latin", "test"))
    monkeypatch.setattr(assist, "_enforce_live_property_data", lambda payload, *_a: payload)
    monkeypatch.setattr(assist, "evaluate_rag_response", lambda *_a: {})
    monkeypatch.setattr(assist, "get_current_data_api_logs", lambda: [])
    monkeypatch.setattr(clarification, "get_project_wings", lambda _id: [
        {"id": 30, "name": "Venus A"}, {"id": 31, "name": "Jupiter C"},
    ])
    # The general pipeline must never be reached: this question is fully
    # resolved by the grounded shortcut chain.
    monkeypatch.setattr(assist, "run_support_orchestration",
                        lambda **_kw: (_ for _ in ()).throw(AssertionError("fell through to general pipeline")))
    monkeypatch.setattr(assist, "stream_support_orchestration_events",
                        lambda **_kw: (_ for _ in ()).throw(AssertionError("fell through to general pipeline")))

    marker = build_current_project_marker("Vishwajeet Empire NX")
    history = [{"sender": "customer", "text": "Vishwajeet Empire NX"},
               {"sender": "bot", "text": "Choose a wing in Vishwajeet Empire NX." + marker}]

    class Session:
        def __init__(self, *_a): pass
        def set_cookie(self, *_a): pass
        def load(self): return list(history)
        def append(self, *_a, **_kw): pass

    monkeypatch.setattr(assist, "ConversationSession", Session)
    with TestClient(api) as client:
        response = client.post(endpoint, json={
            "issue": "what bhks are available in this project ?",
            "conversation_id": "generic-bhk-followup", "conversation_messages": history,
        })
        assert response.status_code == 200
        payload = response.json() if not endpoint.endswith("stream") else next(
            event["response"] for event in map(json.loads, response.text.splitlines()) if event["type"] == "done")

    assert payload["clarification_entity"] == "wing"
    assert payload["answer"].splitlines()[0] == "Which wing should I check in Vishwajeet Empire NX?"
    assert [choice["value"] for choice in payload["quick_replies"]] == ["Venus A", "Jupiter C"]
