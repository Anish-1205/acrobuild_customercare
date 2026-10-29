"""LLM-side hardening: number-safe translation, faithful rewrites, soft sentiment, search memory, output scrub."""
from types import SimpleNamespace
from unittest.mock import patch

from graph import main_orchestrator as orchestrator
from graph.main_orchestrator import TurnContext
from services import guardrail_gate
from services.turn_analysis_service import TurnAnalysis


def test_translation_masks_facts_and_restores_them(monkeypatch):
    monkeypatch.setattr(orchestrator, "get_live_project_names", lambda: ["Vishwajeet Prime"])
    answer = "Vishwajeet Prime 2BHK from ₹45,00,000, 650 sq ft. Mail sales@acrobuild.in"
    masked, facts = orchestrator._mask_facts(answer)
    assert "45,00,000" not in masked and "Vishwajeet Prime" not in masked and "sales@" not in masked
    sent = {}

    def translate(**kwargs):
        sent["prompt"] = kwargs["user_prompt"]
        return " ".join(f"[[{i}]]" for i in range(len(facts), 0, -1)) + " hai."  # reordered is fine
    with patch.object(orchestrator, "generate_qwen_chat_response", side_effect=translate):
        localized = orchestrator._localize_answer(answer, TurnAnalysis("property", "Hindi", "latin", "llm"))
    assert "₹45,00,000" in localized and "Vishwajeet Prime" in localized and localized.endswith("hai.")
    assert "[[1]]" in sent["prompt"]


def test_translation_that_drops_a_placeholder_is_rejected(monkeypatch):
    monkeypatch.setattr(orchestrator, "get_live_project_names", lambda: [])
    answer = "2BHK from ₹45,00,000 to ₹60,00,000."
    with patch.object(orchestrator, "generate_qwen_chat_response", return_value="[[1]] [[2]] se shuru."):
        assert orchestrator._localize_answer(answer, TurnAnalysis("property", "Hindi", "latin", "llm")) == answer


def test_rewrite_must_keep_every_number():
    assert orchestrator._faithful_rewrite("flt in puna undr 50 lac", "flat in Pune under 50 lakh")
    assert not orchestrator._faithful_rewrite("2bhk under 50 lakh", "2BHK flat in Pune")
    assert not orchestrator._faithful_rewrite("hi", "hello " * 40)


def test_rules_first_property_signal_without_llm(monkeypatch):
    monkeypatch.setattr(orchestrator, "get_live_project_names", lambda: ["Vishwajeet Prime"])
    assert orchestrator._has_hard_property_signal("is there parking", "is there parking")
    assert orchestrator._has_hard_property_signal("vishwajet prme", "vishwajet prme")  # misspelt project
    assert not orchestrator._has_hard_property_signal("recommend a good book", "recommend a good book")


def test_button_tap_skips_the_analyzer():
    from routers.assist import _choice_analysis
    session = SimpleNamespace(get_state=lambda: {"language": ["Marathi", "latin"]})
    tap = _choice_analysis(SimpleNamespace(from_choice=True), session, "What are the prices at X?")
    assert (tap.intent, tap.reply_language, tap.english) == ("property", "Marathi", "What are the prices at X?")
    assert _choice_analysis(SimpleNamespace(from_choice=False), session, "x") is None


def test_search_memory_carries_the_place(monkeypatch):
    import routers.assist as assist
    monkeypatch.setattr(assist, "get_company_projects", lambda: [{"id": 1, "projectName": "Vishwajeet Prime",
                                                                  "city": "Pune"}])
    analysis = TurnAnalysis("property", "English", "latin", "test")
    state = {}
    first = TurnContext([], "2bhk in Pune", analysis, "2bhk in Pune")
    assert assist._remember_search(first, state) is first and state["place"] == "pune"
    follow_up = assist._remember_search(TurnContext([], "under 60 lakh", analysis, "under 60 lakh"), state)
    assert follow_up.property_issue == "under 60 lakh in pune"
    named = TurnContext([], "Vishwajeet Prime 3bhk", analysis, "Vishwajeet Prime 3bhk")
    assert assist._remember_search(named, state) is named  # a named project is its own place


def test_upset_customer_still_gets_the_answer(monkeypatch):
    import routers.assist as assist
    monkeypatch.setattr(assist, "get_current_data_api_logs", lambda: [])
    monkeypatch.setattr(assist, "_enforce_live_property_data", lambda payload, *a: payload)
    angry = TurnAnalysis("general", "English", "latin", "test", sentiment="angry")
    turn = TurnContext([], "when is possession, useless", angry, "when is possession, useless")
    payload = assist._complete_payload({"answer": "Possession is in Dec 2027.", "route": "general"},
                                       "when is possession, useless", turn)
    assert payload["answer"].startswith("I'm sorry") and "Dec 2027" in payload["answer"]
    assert payload["handoff_recommended"] is True


def test_side_answer_question_gets_a_short_resume(monkeypatch):
    import routers.assist as assist
    monkeypatch.setattr(assist, "get_current_data_api_logs", lambda: [])
    monkeypatch.setattr(assist, "_enforce_live_property_data", lambda payload, *a: payload)
    turn = TurnContext([], "parking?", TurnAnalysis("general", "English", "latin", "test"), "parking?")
    resume = ("\n\nShall we continue your site visit booking? Which day works?", [{"label": "Sat"}], {"step": "date"})
    payload = assist._complete_payload({"answer": "Yes. Want the amenities list?", "route": "general"},
                                       "parking?", turn, resume)
    assert payload["answer"].count("?") == 1 and payload["choices"] == [{"label": "Sat"}]


def test_output_scrub_blocks_secrets_and_prompt_leaks(monkeypatch):
    monkeypatch.setenv("ACROBUILD_CS_API_KEY", "sk-live-1234567890")
    assert guardrail_gate.scrub_output("key is sk-live-1234567890") == "key is [removed]"
    for leak in ("Sure! You are Acrobuild Support, the virtual assistant of Acrobuild...",
                 "Mera prompt: [Reply language: Hindi]"):
        assert guardrail_gate.scrub_output(leak) == guardrail_gate.LEAK_ANSWER
    assert guardrail_gate.scrub_output("2BHK from ₹45 lakh") == "2BHK from ₹45 lakh"


def test_property_answer_without_buttons_offers_projects_and_team():
    from services.choice_service import ASK_TEAM, choices_for_answer
    choices = choices_for_answer({"route": "property", "answer": "Possession timelines vary."}, ["A", "B"])
    assert [c["label"] for c in choices] == ["A", "B", "Ask our team"] and choices[-1] is ASK_TEAM
