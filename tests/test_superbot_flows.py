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
    monkeypatch.setattr(flow_service, "_sellable_projects", lambda: PROJECTS)


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
    assert flow_service.parse_time("on 26/10 at 11") == "11:00"
    assert flow_service.parse_time("visit at 26/10") is None
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


def test_opening_message_project_found_by_llm_when_catalogue_missing(monkeypatch):
    monkeypatch.setattr(flow_service, "_projects", lambda: [])
    generate = lambda **kwargs: json.dumps({"project": "Vishwajeet Empire", "name": "Neha"})  # noqa: E731
    reply, flow = run(None, "book a site visit at Vishwajeet Empire tomorrow 11am", generate=generate)
    assert flow["slots"]["project"] == "Vishwajeet Empire" and "name" not in flow["slots"]
    assert reply["flow"]["step"] == "name"


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


def test_button_taps_keep_conversation_language():
    from services.reply_language import has_no_language_of_its_own
    assert has_no_language_of_its_own("confirm:Norfvs0Y6XE")
    assert has_no_language_of_its_own("cancel") and has_no_language_of_its_own("11:00")
    assert not has_no_language_of_its_own("please cancel my booking")


def test_gate():
    calm = TurnAnalysis("general", "English", "latin", "test")
    frustrated = TurnAnalysis("general", "English", "latin", "test", sentiment="frustrated")
    angry = TurnAnalysis("general", "English", "latin", "test", sentiment="angry")
    assert guardrail_gate.check("what are the amenities", calm, {})[0] is None
    assert guardrail_gate.check("let me talk to a person", calm, {})[0] == "human_requested"
    # Upset customers still get their answer (softened in the router), not a bare handoff.
    assert guardrail_gate.check("what is the price, useless bot", angry, {})[0] is None
    assert guardrail_gate.is_upset(angry) and guardrail_gate.is_upset(frustrated)
    assert not guardrail_gate.is_upset(calm)
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
    softened = send("this is unacceptable")  # still answered, with an apology and the team offered
    assert softened["handoff_recommended"] and softened["answer"].startswith("I'm sorry")
    assert "covered parking" in softened["answer"]
    handoff = send("let me talk to a person")
    assert handoff["handoff_recommended"] and handoff["agent_mode"] == "handoff"


def test_flags_turn_layers_off(workspace, monkeypatch):
    monkeypatch.setenv("SUPPORT_FLOWS", "false")
    monkeypatch.setenv("SUPPORT_GATE", "false")
    import routers.assist as assist
    from graph.main_orchestrator import TurnContext
    session = ConversationSession("", "f1")
    turn = TurnContext([], "x", TurnAnalysis("general", "English", "latin", "test", sentiment="angry"), "x")
    request = type("R", (), {"customer_name": "", "customer_email": "", "from_choice": False})()
    assert assist._pre_answer(request, turn, "book a site visit, talk to a person", session)[:2] == (None, None)


def test_button_tap_keeps_conversation_language(workspace, monkeypatch):
    monkeypatch.setenv("SUPPORT_FLOWS", "false")
    monkeypatch.setenv("SUPPORT_GATE", "false")
    import routers.assist as assist
    from graph.main_orchestrator import TurnContext
    session = ConversationSession("", "lang1")
    typed = type("R", (), {"customer_name": "", "customer_email": "", "from_choice": False})()
    tapped = type("R", (), {"customer_name": "", "customer_email": "", "from_choice": True})()
    marathi = TurnContext([], "x", TurnAnalysis("property", "Marathi", "latin", "test"), "x")
    english = TurnContext([], "x", TurnAnalysis("property", "English", "latin", "test"), "x")
    assist._pre_answer(typed, marathi, "tumchya kade projects aahe?", session)
    turn = assist._pre_answer(tapped, english, "What are the prices at Vishwajeet Empire?", session)[2]
    assert turn.analysis.reply_language == "Marathi"
    turn = assist._pre_answer(typed, english, "please answer in English", session)[2]
    assert turn.analysis.reply_language == "English"  # typing still switches language


NAMES = ["Vishwajeet Empire", "Vishwajeet Empire NX", "Vishwajeet Prime"]


def test_choices_for_answers():
    from services.choice_service import choices_for_answer, mentioned_projects
    assert mentioned_projects("We have Vishwajeet Empire NX and Vishwajeet Prime.", NAMES) == ["Vishwajeet Empire NX", "Vishwajeet Prime"]
    listing = choices_for_answer({"route": "property", "answer": "1. Vishwajeet Empire\n2. Vishwajeet Prime"}, NAMES)
    assert [(c["label"], c["action"]) for c in listing] == [("Vishwajeet Empire", "project"), ("Vishwajeet Prime", "project")]
    single = choices_for_answer({"route": "property", "answer": "Vishwajeet Prime is in Thane."}, NAMES)
    assert [c["label"] for c in single] == ["Wings & flats", "Location", "Prices", "Amenities", "Offers",
                                            "Payment plan", "Book a site visit"]
    assert single[-1]["value"] == "Book a site visit at Vishwajeet Prime"
    after_location = choices_for_answer({"route": "property", "answer": "Vishwajeet Prime is in Thane."}, NAMES,
                                        question="Vishwajeet Prime kuthe aahe? Where is Vishwajeet Prime?")
    assert "Location" not in [c["label"] for c in after_location]
    address = choices_for_answer({"route": "property", "answer": "Vishwajeet Empire NX: Vishwajeet Empire, Pale Village"},
                                 NAMES, question="Where is Vishwajeet Empire NX located?")
    assert address[0] == {"label": "Wings & flats", "value": "Vishwajeet Empire NX", "action": "project", "topic": "explore"}
    ask = choices_for_answer({"route": "property", "answer": "Which of our 10 projects would you like?"}, NAMES)
    assert [c["label"] for c in ask] == NAMES
    assert choices_for_answer({"route": "general", "answer": "Vishwajeet Prime"}, NAMES) == []
    assert choices_for_answer({"route": "property", "answer": "Vishwajeet Prime", "handoff_recommended": True}, NAMES) == []


CATALOGUE = {1: [{"name": "Gym", "type": "Amenities"}, {"name": "Pool & Billards", "type": "Amenities"}],
             2: [{"name": "Swimming Pool", "type": "Amenities"}, {"name": "Lift", "type": "Facilities"}],
             3: [{"name": "Baby Swimming Area", "type": "Amenities"}]}
AMENITY_PROJECTS = [{"id": 1, "projectName": "Vishwajeet Heights"}, {"id": 2, "projectName": "Vishwajeet Prime"},
            {"id": 3, "projectName": "Vishwajeet Town"}]


def _request(issue, history=()):
    from api_context import SupportAssistRequest
    return SupportAssistRequest(issue=issue, conversation_messages=[{"sender": "customer", "text": t} for t in history])


@pytest.fixture
def live_amenities(monkeypatch):
    import api_context
    monkeypatch.setattr(api_context, "get_company_projects", lambda: AMENITY_PROJECTS)
    monkeypatch.setattr(api_context, "get_project_amenities", lambda pid: CATALOGUE[pid])
    # Every project has one wing with a 2BHK on sale, so amenity searches have homes to list.
    monkeypatch.setattr(api_context, "_project_listing", lambda project: (
        [{"id": project["id"], "name": "A", "totalFloors": 12}],
        {project["id"]: [{"id": project["id"], "typologyType": "2BHK", "saleableArea": 1000,
                          "minBasePrice": 4000, "maxBasePrice": 5000}]},
        {(project["id"], project["id"]): 4}))
    return api_context


def test_amenity_matching_uses_real_names():
    from api_context import requested_amenities
    names = {"Swimming Pool", "Baby Swimming Area", "Pool & Billiards", "Gym", "Children's Playing Area", "Parking",
             "Visitor Parking", "Lift", "Power Backup Lift"}
    assert requested_amenities("I want a swimming pool", names) == ["Swimming Pool"]
    assert requested_amenities("is there a pool?", names) == ["Swimming Pool"]
    assert requested_amenities("pool and billiards room", names) == ["Pool & Billiards"]
    assert requested_amenities("kids play area", names) == ["Children's Playing Area"]
    assert requested_amenities("parking and lift", names) == ["Lift", "Parking"]
    assert requested_amenities("what is the security deposit?", names) == []


def test_amenity_filter_and_project_answers(live_amenities):
    api = live_amenities
    pool = api.build_grounded_project_amenities_assist(_request("I want a swimming pool"))
    assert pool["choices"] == [{"label": "Vishwajeet Prime", "value": "Vishwajeet Prime", "action": "project"}]
    assert pool["answer"].startswith("Here are homes with Swimming Pool:\n- Vishwajeet Prime")
    parking = api.build_grounded_project_amenities_assist(_request("2bhk with gym under 45 lakh"))
    assert [c["label"] for c in parking["choices"]] == ["Vishwajeet Heights"]
    assert parking["answer"].startswith("Here are 2BHK homes under ₹45 lakh with Gym:")
    details = api.build_grounded_project_details_assist(_request("how many wing and 2bhk size in Vishwajeet Prime"))
    assert "Wings: A (12 floors" in details["answer"] and "- 2BHK, 1,000 sq ft, approx. ₹40 lakh - ₹50 lakh" in details["answer"]
    no = api.build_grounded_project_amenities_assist(_request("does Vishwajeet Heights have a swimming pool?"))
    assert "doesn't list Swimming Pool" in no["answer"] and "Vishwajeet Prime" in no["answer"]
    listing = api.build_grounded_project_amenities_assist(_request("amenities", history=["tell me about Vishwajeet Prime"]))
    assert "Amenities: Swimming Pool" in listing["answer"] and "Facilities: Lift" in listing["answer"]
    assert "Amenities" not in [c["label"] for c in listing["choices"]]
    assert api.build_grounded_project_amenities_assist(_request("is it on the ground floor?")) is None
    pick = api.build_grounded_project_amenities_assist(_request("what amenities do you have?"))
    assert [c["value"] for c in pick["choices"]][1] == "What amenities does Vishwajeet Prime have?"


def test_offers_and_payment_plans(monkeypatch):
    import api_context as api
    monkeypatch.setattr(api, "get_company_projects", lambda: AMENITY_PROJECTS)
    monkeypatch.setattr(api, "get_project_offers", lambda pid: [
        {"name": "Stamp Duty Free", "applies_to": ["Investor", "Loan", "Self-Funding"]},
        {"name": "Rate Discount", "applies_to": ["Loan"]}])
    monkeypatch.setattr(api, "get_project_payment_plans", lambda pid: [
        {"name": "Prime Schedule", "type": "Construction Linked", "booking_amount": 51000.0,
         "milestones": [{"name": f"{i}% on slab {i}", "percentage": i} for i in range(1, 8)]},
        {"name": "Empty", "type": "Freestyle", "booking_amount": 80000.0, "milestones": []}])
    offers = api.build_grounded_project_offers_assist(_request("any offers at Vishwajeet Prime?"))
    assert "- Stamp Duty Free\n- Rate Discount (for Loan buyers)" in offers["answer"]
    assert "Offers" not in [c["label"] for c in offers["choices"]]
    plan = api.build_grounded_project_payment_plan_assist(_request("payment plan for Vishwajeet Prime"))
    assert plan["answer"] == ("Payment plans at Vishwajeet Prime:\n- Prime Schedule (Construction Linked): "
                              "booking amount INR 51,000, then 7 stages linked to construction")
    full = api.build_grounded_project_payment_plan_assist(_request(plan["choices"][0]["value"]))
    assert "- 7% on slab 7" in full["answer"]
    assert "Freestyle" not in plan["answer"]
    assert api.build_grounded_project_offers_assist(_request("what is the price?")) is None


def test_company_service_reads_new_endpoints(monkeypatch):
    from datetime import date
    import services.acrobuild_company_service as cs
    responses = {
        "/api/cs/projects/7/amenities": [{"iconName": "Gym", "type": "Amenities"}, {"iconName": "gym ", "type": "Amenities"}],
        "/api/cs/projects/7/offers": [
            {"offerName": "Stamp Duty Free", "applicableTos": ["Loan"], "startDate": 0, "endDate": None},
            {"offerName": "Stamp  Duty Free", "applicableTos": ["Investor"], "startDate": 0, "endDate": None},
            {"offerName": "Future", "applicableTos": ["Loan"], "startDate": 4102444800000, "endDate": None},
            {"offerName": "Expired", "applicableTos": ["Loan"], "startDate": 0, "endDate": 1}],
        "/api/cs/projects/7/payment-plans": [
            {"scheduleName": "A", "scheduleType": "Construction Linked", "bookingAmount": 51000.0,
             "milestones": [{"name": "10% on plinth", "percentage": 10.0}]},
            {"scheduleName": "A", "scheduleType": "Construction Linked", "bookingAmount": 51000.0,
             "milestones": [{"name": "10% on plinth", "percentage": 10.0}]}],
    }
    monkeypatch.setattr(cs, "_cached_request", lambda path, params=None, ttl_seconds=None: responses[path])
    assert cs.get_project_amenities(7) == [{"name": "Gym", "type": "Amenities"}]
    assert cs.get_project_offers(7, today=date(2026, 10, 29)) == [{"name": "Stamp Duty Free", "applies_to": ["Investor", "Loan"]}]
    assert len(cs.get_project_payment_plans(7)) == 1


def test_cs_api_urls_are_company_scoped(monkeypatch):
    import services.acrobuild_company_service as cs
    monkeypatch.setattr(cs, "CS_API_COMPANY_ID", "16")
    assert cs._company_scoped_path("/api/cs/projects") == "/api/cs/16/projects"
    assert cs._company_scoped_path("/api/cs/wings/55/inventory") == "/api/cs/16/wings/55/inventory"
    monkeypatch.setattr(cs, "CS_API_COMPANY_ID", "")
    assert cs._company_scoped_path("/api/cs/projects") == "/api/cs/projects"


class _FakeOpener:
    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), 0

    def open(self, request, timeout=None):
        import io
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return io.BytesIO(outcome)


def test_cs_client_retries_one_network_blip(monkeypatch):
    import urllib.error
    import urllib.request
    import services.acrobuild_company_service as cs
    logged = []
    monkeypatch.setattr(cs, "CS_API_KEY", "k")
    monkeypatch.setattr(cs, "log_data_api_call", lambda **kw: logged.append(kw["status"]))
    opener = _FakeOpener([TimeoutError(), b"[1, 2]"])
    monkeypatch.setattr(urllib.request, "build_opener", lambda *a: opener)
    assert cs._request_json("/api/cs/projects") == [1, 2]
    assert opener.calls == 2 and logged == ["completed"]  # the recovered blip is not reported as a failure
    opener = _FakeOpener([urllib.error.URLError("down"), urllib.error.URLError("down")])
    monkeypatch.setattr(urllib.request, "build_opener", lambda *a: opener)
    with pytest.raises(RuntimeError, match="Could not reach"):
        cs._request_json("/api/cs/projects")
    import io
    http_error = urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b"{}"))
    opener = _FakeOpener([http_error, b"[]"])
    monkeypatch.setattr(urllib.request, "build_opener", lambda *a: opener)
    with pytest.raises(RuntimeError):
        cs._request_json("/api/cs/projects")
    assert opener.calls == 1  # the server's real answer is not retried


def test_live_guard_ignores_failures_recovered_in_the_same_turn():
    from api_context import _enforce_live_property_data
    chunk = {"record_kind": "company_api"}
    draft = {"route": "property", "answer": "Vishwajeet Empire NX is in Ambernath.", "matched_chunks": [chunk]}
    calls = [{"provider": "Acrobuild CS API", "endpoint": "/api/cs/projects", "status": "failed", "params": {}},
             {"provider": "Acrobuild CS API", "endpoint": "/api/cs/projects", "status": "completed", "params": {}}]
    assert _enforce_live_property_data(dict(draft), "where is NX", calls)["answer"] == draft["answer"]
    still_failing = [dict(calls[0], endpoint="/api/cs/projects/56/wings"), calls[1]]
    assert "unavailable" in _enforce_live_property_data(dict(draft), "where is NX", still_failing)["answer"]


def test_misclassified_general_turn_still_reaches_search(monkeypatch):
    import routers.assist as assist
    from graph.main_orchestrator import TurnContext
    calls = []
    monkeypatch.setattr(assist, "build_grounded_company_contact_assist", lambda r: calls.append("contact"))
    monkeypatch.setattr(assist, "build_grounded_project_amenities_assist", lambda r: calls.append("amenities"))
    monkeypatch.setattr(assist, "build_grounded_home_finder_assist",
                        lambda r: {"answer": "We don't have projects in Mumbai", "choices": []})
    request = type("R", (), {"issue": "property in mumbai", "model_dump": lambda self: {}})()
    turn = TurnContext([], "property in mumbai", TurnAnalysis("general", "English", "latin", "test"), "property in mumbai")
    payload = assist._grounded_property_shortcut(request, turn)
    assert calls == ["contact", "amenities"] and payload["route"] == "property"


def test_finder_skips_the_cs_api_for_chit_chat(monkeypatch):
    import api_context
    monkeypatch.setattr(api_context, "get_company_projects", lambda: (_ for _ in ()).throw(AssertionError("API called")))
    from api_context import SupportAssistRequest
    assert api_context.build_grounded_home_finder_assist(SupportAssistRequest(issue="hi, how are you?")) is None


def test_shortcut_failure_falls_through(monkeypatch):
    import routers.assist as assist
    from graph.main_orchestrator import TurnContext

    def down(request):
        raise RuntimeError("CS API request timed out.")
    monkeypatch.setattr(assist, "build_grounded_project_location_assist", down)
    request = type("R", (), {"issue": "Where is NX?", "model_dump": lambda self: {}})()
    turn = TurnContext([], "Where is NX?", TurnAnalysis("property", "English", "latin", "test"), "Where is NX?")
    for name in ("build_grounded_site_visit_document_assist", "build_grounded_project_payment_plan_assist",
                 "build_grounded_project_offers_assist", "build_grounded_project_amenities_assist"):
        monkeypatch.setattr(assist, name, lambda request: None)
    assert assist._grounded_property_shortcut(request, turn) is None


def test_search_with_best_amenities_ranks_projects(live_amenities):
    api = live_amenities
    ranked = api.build_grounded_project_amenities_assist(_request("show me a 2bhk with best amenities"))
    lines = [line for line in ranked["answer"].splitlines() if line.startswith("- ")]
    # Heights and Prime list 2 amenities, Town 1: the best-equipped come first, with what they offer.
    assert lines[-1].startswith("- Vishwajeet Town") and "1 amenities" in lines[-1]
    assert "2 amenities incl. Swimming Pool, Lift" in ranked["answer"]
    assert "best amenities first" in ranked["answer"]
    # Without a search or "best", a bare amenities question still asks which project.
    ask = api.build_grounded_project_amenities_assist(_request("what amenities do you have"))
    assert ask["answer"] == "Which project's amenities would you like to see?"


def test_several_requests_in_one_message_are_each_answered(monkeypatch):
    import routers.assist as assist
    from graph.main_orchestrator import TurnContext
    monkeypatch.setattr(assist, "get_company_projects", lambda: AMENITY_PROJECTS)
    asked = []

    def single(request, turn):
        asked.append(turn.property_issue)
        if "offers" in turn.property_issue:
            return None
        return {"answer": f"Answer to {turn.property_issue}\n\nPrices are estimates.", "route": "property",
                "choices": [{"label": "Book a site visit", "value": "Book"}], "matched_chunks": [{"id": len(asked)}]}
    monkeypatch.setattr(assist, "_single_shortcut", single)
    text = "price of prime and amenities of heights? any offers"
    turn = TurnContext([], text, TurnAnalysis("general", "English", "latin", "test"), text)
    payload = assist._grounded_property_shortcut(_request(text), turn)
    assert asked == ["price of prime", "amenities of heights", "any offers of Vishwajeet Heights"]
    assert payload["answer"].count("Prices are estimates.") == 1
    assert "Answer to price of prime" in payload["answer"] and "Answer to amenities of heights" in payload["answer"]
    assert '"any offers of Vishwajeet Heights"' in payload["answer"]
    assert [c["label"] for c in payload["choices"]] == ["Book a site visit", "Ask our team"]
    assert len(payload["matched_chunks"]) == 2


def test_answers_carry_only_what_was_asked(monkeypatch, live_amenities):
    api = live_amenities
    monkeypatch.setattr(api, "get_project_offers", lambda pid: [{"name": f"Offer {i}", "applies_to": []} for i in range(9)])
    offers = api.build_grounded_project_offers_assist(_request("any offers at Vishwajeet Prime?"))
    assert offers["answer"].count("\n- ") == 3 and "...and 6 more." in offers["answer"]
    assert offers["choices"][0] == {"label": "All 9 offers", "value": "Show all offers at Vishwajeet Prime"}
    full = api.build_grounded_project_offers_assist(_request(offers["choices"][0]["value"]))
    assert "Offer 8" in full["answer"] and "more." not in full["answer"]

    price = api.build_grounded_project_details_assist(_request("price of Vishwajeet Prime"))
    assert price["answer"].startswith("Vishwajeet Prime prices:\n- 2BHK, approx. ₹40 lakh - ₹50 lakh")
    assert "sq ft" not in price["answer"] and "Wings" not in price["answer"]
    wings = api.build_grounded_project_details_assist(_request("how many wings in Vishwajeet Prime"))
    assert wings["answer"] == "Vishwajeet Prime wings:\n- A (12 floors, 4 flats listed)"
    assert "₹" not in wings["answer"]


def test_long_amenity_lists_show_highlights_first(monkeypatch, live_amenities):
    api = live_amenities
    many = ["Gym", "Swimming Pool", "Lift", "Park", "Parking", "Carrom", "Badminton", "Terrace", "Internet", "Gas Pipe"]
    monkeypatch.setattr(api, "get_project_amenities", lambda pid: [{"name": n, "type": "Amenities"} for n in many])
    short = api.build_grounded_project_amenities_assist(_request("what amenities does Vishwajeet Prime have?"))
    assert short["answer"] == ("Vishwajeet Prime has 10 amenities, including Swimming Pool, Gym, Park, Parking, "
                               "Lift, Carrom.")
    assert short["choices"][0]["label"] == "All 10 amenities"
    full = api.build_grounded_project_amenities_assist(_request(short["choices"][0]["value"]))
    assert "Gas Pipe" in full["answer"]
