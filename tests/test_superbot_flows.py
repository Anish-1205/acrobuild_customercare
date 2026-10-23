import json
from datetime import date

import pytest

from test_upgrade_security import workspace  # noqa: F401
from services import action_registry, flow_service, guardrail_gate
from services.conversation_store_service import ConversationSession
from services.turn_analysis_service import TurnAnalysis, heuristic_sentiment

TODAY = date(2026, 10, 23)  # a Friday
PROJECTS = [{"projectName": "Vishwajeet Empire"}, {"projectName": "Vishwajeet Empire NX"}, {"projectName": "Skyline Residency"}]


@pytest.fixture(autouse=True)
def fake_projects(monkeypatch):
    monkeypatch.setattr(flow_service, "_projects", lambda: PROJECTS)


@pytest.fixture
def booked(monkeypatch):
    calls = []
    def submit(request):
        calls.append(request)
        return {"ticket_id": f"T{len(calls)}"}
    monkeypatch.setitem(action_registry.ACTIONS, "book_site_visit", (action_registry.SiteVisitRequest, submit))
    return calls


def run(flow, *messages, **kwargs):
    reply = None
    for message in messages:
        reply, flow = flow_service.step(flow, message, today=TODAY, **kwargs)
    return reply, flow


def test_projects_fetched_once_even_when_cs_api_fails(monkeypatch):
    import services.acrobuild_company_service as company
    monkeypatch.undo()  # drop the autouse fake so the real _projects runs
    calls = []
    def down():
        calls.append(1)
        raise RuntimeError("Could not reach the CS API: timed out")
    monkeypatch.setattr(company, "get_company_projects", down)
    monkeypatch.setattr(flow_service, "_projects_cache", {"at": 0.0, "items": []})
    flow_service.step(None, "book a site visit this Sunday", today=TODAY)
    flow_service.step(None, "book a site visit", today=TODAY)
    assert len(calls) == 1


def test_parsers():
    assert flow_service.parse_date("this sunday morning", TODAY) == "2026-10-25"
    assert flow_service.parse_date("tomorrow", TODAY) == "2026-10-24"
    assert flow_service.parse_date("26/10", TODAY) == "2026-10-26"
    assert flow_service.parse_date("01/01", TODAY) == "2027-01-01"
    assert flow_service.parse_date("2026-10-01", TODAY) is None  # past
    assert flow_service.parse_date("31/02", TODAY) is None
    assert flow_service.parse_time("3pm") == "15:00"
    assert flow_service.parse_time("11", current=True) == "11:00"
    assert flow_service.parse_time("11") is None  # bare numbers only when time is being asked
    assert flow_service.parse_time("9 am") is None  # outside visiting slots
    assert flow_service.parse_phone("Ravi, +91 98765 43210") == "9876543210"
    assert flow_service.parse_phone("12345") is None
    assert flow_service.parse_name("Ravi, 9876543210", current=True) == "Ravi"
    assert flow_service.parse_name("my name is Ravi Kumar", current=True) == "Ravi Kumar"
    assert flow_service.parse_name("is there parking", current=True) is None
    assert flow_service.parse_project("Empire NX please") == "Vishwajeet Empire NX"


def test_full_booking_by_chat(booked):
    reply, flow = run(None, "I want to book a site visit at Skyline this Sunday")
    assert flow["slots"] == {"project": "Skyline Residency", "date": "2026-10-25"}
    assert reply["flow"]["step"] == "time" and {"label": "11:00", "value": "11:00"} in reply["choices"]
    reply, flow = run(flow, "11", "Ravi, 9876543210", "ravi@example.com")
    assert reply["flow"]["step"] == "confirm" and "Skyline Residency" in reply["answer"]
    confirm_value = reply["choices"][0]["value"]
    reply, flow = run(flow, confirm_value)
    assert flow is None and reply["ticket"] == {"ticket_id": "T1"}
    assert booked[0].preferred_time == "11:00" and booked[0].customer_phone == "9876543210"


def test_prefill_skips_known_details(booked):
    reply, flow = run(None, "book a visit to Skyline on 26/10 at 3pm", prefill={"name": "Ravi", "email": "ravi@example.com"})
    assert reply["flow"]["step"] == "phone"


def test_side_question_passes_through_and_resumes():
    _, flow = run(None, "book a site visit")
    reply, flow = flow_service.step(flow, "is there parking at the site?", today=TODAY)
    assert reply is None and flow["asking"] == "project"
    suffix, choices, _ = flow_service.resume_prompt(flow, TODAY)
    assert "continue your site visit booking" in suffix and choices[0]["label"] == "Vishwajeet Empire"


def test_cancel_and_repeated_misses():
    _, flow = run(None, "book a site visit at Skyline")
    reply, flow = run(flow, "cancel")
    assert flow is None and reply["flow"]["step"] == "cancelled"
    _, flow = run(None, "book a site visit at Skyline")
    reply, flow = run(flow, "blah")
    assert "didn't catch" in reply["answer"] and flow is not None
    reply, flow = run(flow, "blah blah")
    assert flow is None and reply["handoff"]


def test_llm_extraction_is_validated():
    _, flow = run(None, "book a site visit at Skyline")
    generate = lambda **kwargs: json.dumps({"date": "2026-10-27", "time": "25:00"})  # noqa: E731
    reply, flow = run(flow, "the coming Tuesday-ish", generate=generate)
    assert flow["slots"]["date"] == "2026-10-27" and "time" not in flow["slots"]
    assert reply["flow"]["step"] == "time"


def test_confirmation_is_single_use_and_expires(booked):
    pending = action_registry.propose("book_site_visit", {
        "customer_name": "Ravi", "customer_email": "r@example.com", "customer_phone": "9876543210",
        "project_name": "Skyline Residency", "preferred_date": "2026-10-25", "preferred_time": "11:00"}, now=1000)
    assert action_registry.confirm(pending, "wrong", now=1001) is None
    assert action_registry.confirm(pending, pending["nonce"], now=1000 + 601) is None
    assert action_registry.confirm(pending, pending["nonce"], now=1001) == {"ticket_id": "T1"}
    _, flow = run(None, "book a visit to Skyline on 26/10 at 3pm", prefill={"name": "Ravi", "email": "r@example.com"})
    reply, flow = run(flow, "9876543210")
    old_value = reply["choices"][0]["value"]
    _, flow = run(flow, old_value)
    reply, flow = run(flow, old_value)  # replayed button after the flow ended starts nothing
    assert reply is None and flow is None and len(booked) == 2


def test_gate():
    calm = TurnAnalysis("general", "English", "latin", "test")
    frustrated = TurnAnalysis("general", "English", "latin", "test", sentiment="frustrated")
    angry = TurnAnalysis("general", "English", "latin", "test", sentiment="angry")
    assert guardrail_gate.check("what are the amenities", calm, {})[0] is None
    assert guardrail_gate.check("let me talk to a person", calm, {})[0] == "human_requested"
    assert guardrail_gate.check("whatever", angry, {})[0] == "angry"
    reason, state = guardrail_gate.check("still not fixed", frustrated, {})
    assert reason is None
    assert guardrail_gate.check("still not fixed", frustrated, state)[0] == "frustrated"
    assert heuristic_sentiment("You people are frauds") == "angry"
    assert heuristic_sentiment("When is possession?") == "calm"
    assert heuristic_sentiment("STILL NO UPDATE ON MY FLAT") == "frustrated"


def test_state_round_trip(workspace):
    session = ConversationSession("", "c1")
    session.set_state({"flow": {"name": "site_visit"}})
    assert ConversationSession(session.token, "c1").get_state() == {"flow": {"name": "site_visit"}}
    session.set_state(None)
    assert session.get_state() == {}


def test_stream_endpoint_runs_booking_and_handoff(workspace, monkeypatch, booked):
    from fastapi.testclient import TestClient
    import app
    import routers.assist as assist
    from graph.main_orchestrator import TurnContext

    monkeypatch.setenv("SUPPORT_FLOWS", "true")
    monkeypatch.setenv("SUPPORT_GATE", "true")

    class FixedDate(date):
        @classmethod
        def today(cls):
            return TODAY
    monkeypatch.setattr(flow_service, "date", FixedDate)
    sentiment = {"value": "calm"}
    monkeypatch.setattr(assist, "prepare_turn", lambda issue, *args, **kwargs: TurnContext(
        [], issue, TurnAnalysis("general", "English", "latin", "test", sentiment=sentiment["value"]), issue))
    monkeypatch.setattr(assist, "localize_response", lambda payload, analysis: payload)

    def orchestrator(**kwargs):
        yield {"type": "delta", "text": "There is covered parking."}
        yield {"type": "done", "response": {"answer": "There is covered parking.", "matched_chunks": [], "route": "general"}}
    monkeypatch.setattr(assist, "stream_support_orchestration_events", orchestrator)

    client = TestClient(app.api)

    def send(issue):
        response = client.post("/api/support/assist/stream", json={"issue": issue, "conversation_id": "s1"})
        assert response.status_code == 200
        return [json.loads(line) for line in response.text.splitlines() if line.strip()][-1]["response"]

    assert send("I want to book a site visit at Skyline on 26/10")["flow"]["step"] == "time"
    side = send("is there parking?")
    assert side["answer"].startswith("There is covered parking.") and "continue your site visit booking" in side["answer"]
    assert side["flow"]["step"] == "time"
    send("11am")
    send("Ravi")
    send("9876543210")
    confirm = send("ravi@example.com")
    assert confirm["flow"]["step"] == "confirm"
    done = send(confirm["choices"][0]["value"])
    assert done["ticket"] == {"ticket_id": "T1"} and len(booked) == 1

    sentiment["value"] = "angry"
    handoff = send("this is unacceptable")
    assert handoff["handoff_recommended"] and handoff["agent_mode"] == "handoff"


def test_flags_turn_layers_off(workspace, monkeypatch):
    monkeypatch.setenv("SUPPORT_FLOWS", "false")
    monkeypatch.setenv("SUPPORT_GATE", "false")
    import routers.assist as assist
    from graph.main_orchestrator import TurnContext
    session = ConversationSession("", "f1")
    turn = TurnContext([], "x", TurnAnalysis("general", "English", "latin", "test", sentiment="angry"), "x")
    request = type("R", (), {"customer_name": "", "customer_email": ""})()
    assert assist._pre_answer(request, turn, "book a site visit, talk to a person", session) == (None, None)
