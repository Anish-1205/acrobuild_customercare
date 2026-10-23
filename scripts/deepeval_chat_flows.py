"""Multi-turn DeepEval run over the booking flow, handoff gate and side questions.

Drives the real FastAPI app in-process against a throwaway SQLite database (test
bookings never touch support_system.db) and scores each conversation with
DeepEval's conversational metrics, using the configured Sarvam endpoint as judge.

    python scripts/deepeval_chat_flows.py [path/to/.env]

Needs LLM_PROVIDER=sarvam with RUNPOD_BASE_URL/RUNPOD_API_KEY in the env file.
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
import uuid
from contextlib import closing
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# Keep conversations local: no DeepEval telemetry or cloud upload.
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("DEEPEVAL_DISABLE_DOTENV", "1")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(sys.argv[1] if len(sys.argv) > 1 else ROOT / ".env", override=True)

from deepeval import evaluate  # noqa: E402
from deepeval.evaluate.configs import AsyncConfig, DisplayConfig, ErrorConfig  # noqa: E402
from deepeval.metrics import (  # noqa: E402
    ConversationalGEval,
    ConversationCompletenessMetric,
    KnowledgeRetentionMetric,
    RoleAdherenceMetric,
    TurnRelevancyMetric,
)
from deepeval.models import DeepEvalBaseLLM  # noqa: E402
from deepeval.test_case import ConversationalTestCase, MultiTurnParams, Turn  # noqa: E402

CONFIRM = "__confirm__"  # replaced with the Confirm button's value from the previous reply
CHATBOT_ROLE = (
    "Customer support assistant for Acrobuild, a real-estate developer. It answers property questions "
    "from live data only and says so plainly when live data is unavailable; books site visits only after "
    "the customer explicitly confirms a summary (the customer tapping 'Confirm' is that confirmation); "
    "and handing an upset customer, or one who asks for a person, to the human team is part of its role."
)
SCENARIOS = [
    {
        "name": "booking_happy_path",
        "scenario": "Customer books a site visit for Sunday morning.",
        "expected_outcome": "Visit booked after an explicit confirmation, with a request ID returned.",
        "messages": ["I want to book a site visit this Sunday", "Vishwajeet Empire", "11am",
                     "my name is Priya Shah", "98765 43210", "priya.shah@example.com", CONFIRM],
        "expect": {"tickets": 1, "step": "done"},
    },
    {
        "name": "side_question_mid_booking",
        "scenario": "Customer starts a booking, asks an unrelated question, then finishes the booking.",
        "expected_outcome": "Side question answered, booking resumed without re-asking known details, then booked.",
        "messages": ["book a site visit tomorrow at 3pm", "which languages can you speak?", "Vishwajeet Empire",
                     "Priya", "9876543210 priya@example.com", CONFIRM],
        "expect": {"tickets": 1, "step": "done"},
    },
    {
        "name": "hinglish_booking",
        "scenario": "Customer books a visit writing in romanized Hindi.",
        "expected_outcome": "Visit booked with the time the customer gave in Hindi.",
        "messages": ["mujhe kal site visit book karna hai", "Vishwajeet Empire", "12 baje", "Amit",
                     "9988776655", "amit@example.com", CONFIRM],
        "expect": {"tickets": 1, "step": "done"},
    },
    {
        "name": "no_booking_without_confirm",
        "scenario": "Customer reaches the confirmation step but asks a question instead of confirming, then confirms.",
        "expected_outcome": "Nothing is booked until the customer confirms; then exactly one booking.",
        "messages": ["book a site visit at Vishwajeet Empire tomorrow 11am", "Neha", "9876501234",
                     "neha@example.com", "before I confirm, how long does a visit usually take?", CONFIRM],
        "expect": {"tickets": 1, "step": "done", "tickets_before_last": 0},
    },
    {
        "name": "change_then_cancel",
        "scenario": "Customer fills in a booking, asks to change it, then cancels.",
        "expected_outcome": "No booking is made and the assistant confirms the cancellation.",
        "messages": ["schedule a visit to Vishwajeet Empire on 26/10 at 11", "Rahul", "9123456789",
                     "rahul@example.com", "change", "cancel"],
        "expect": {"tickets": 0, "step": "cancelled", "saw_step": "confirm"},
    },
    {
        "name": "angry_customer_handoff",
        "scenario": "An angry customer complains about a delayed flat.",
        "expected_outcome": "The assistant apologises and hands the customer to a human instead of arguing.",
        "messages": ["You people are frauds, my flat is 6 months late and nobody answers my calls"],
        "expect": {"tickets": 0, "handoff": True},
    },
    {
        "name": "asks_for_a_person",
        "scenario": "Customer asks to talk to a person.",
        "expected_outcome": "The assistant offers a human handoff.",
        "messages": ["can I speak to a person please"],
        "expect": {"tickets": 0, "handoff": True},
    },
]


class SarvamJudge(DeepEvalBaseLLM):
    """DeepEval judge on the project's Sarvam endpoint, with room for full JSON verdicts."""

    def __init__(self):
        super().__init__("sarvam-judge")

    def load_model(self):
        return self

    def generate(self, prompt: str) -> str:
        from sarvam_client import generate_sarvam_chat_response

        for attempt in range(6):
            try:
                return generate_sarvam_chat_response([{"role": "user", "content": prompt}], temperature=0, max_tokens=2000)
            except Exception as error:  # the hosted Sarvam API rate-limits bursts of judge calls
                if "429" not in str(error) or attempt == 5:
                    raise
                time.sleep(5 * (attempt + 1))
        raise RuntimeError("unreachable")

    async def a_generate(self, prompt: str) -> str:
        return await asyncio.to_thread(self.generate, prompt)

    def get_model_name(self):
        return os.getenv("MODEL_NAME") or "sarvam"


def use_temp_database():
    from services import admin_settings_service as settings
    from services import database_service as database
    from services.migration_service import apply_migrations

    path = str(Path(tempfile.mkdtemp(prefix="deepeval-")) / "support.db")
    database.DB_PATH = settings.DB_PATH = path
    database.initialize_database()
    apply_migrations(path)
    return database


def ticket_count(database):
    with closing(database.open_database_connection()) as conn:
        return conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]


def run_scenario(client_factory, database, scenario):
    client = client_factory()
    conversation_id = f"deepeval-{scenario['name']}-{uuid.uuid4().hex[:6]}"
    turns, last, tickets_before_last, steps = [], {}, 0, []
    for message in scenario["messages"]:
        if message == CONFIRM:
            choice = next((c for c in last.get("choices") or [] if c["value"].startswith("confirm:")), None)
            message = choice["value"] if choice else "confirm"
        tickets_before_last = ticket_count(database)
        response = client.post("/api/support/assist", json={"issue": message, "conversation_id": conversation_id})
        response.raise_for_status()
        last = response.json()
        steps.append((last.get("flow") or {}).get("step"))
        shown = "Confirm" if message.startswith("confirm:") else message  # what the customer saw on the button
        turns += [Turn(role="user", content=shown), Turn(role="assistant", content=str(last.get("answer", "")))]

    expect, failures = scenario["expect"], []
    tickets = ticket_count(database) - scenario["_tickets_at_start"]
    if tickets != expect["tickets"]:
        failures.append(f"tickets {tickets} != {expect['tickets']}")
    if "tickets_before_last" in expect and tickets_before_last - scenario["_tickets_at_start"] != expect["tickets_before_last"]:
        failures.append("booked before the customer confirmed")
    step = (last.get("flow") or {}).get("step")
    if "step" in expect and step != expect["step"]:
        failures.append(f"final step {step!r} != {expect['step']!r}")
    if "saw_step" in expect and expect["saw_step"] not in steps:
        failures.append(f"never reached step {expect['saw_step']!r} (steps: {steps})")
    if expect.get("handoff") and not last.get("handoff_recommended"):
        failures.append("no handoff")
    return turns, failures


def main():
    from fastapi.testclient import TestClient

    import app

    import services.request_security_service as request_security

    database = use_temp_database()
    # Every scripted turn comes from one in-process client; the per-IP 30/min chat budget would 429 the run.
    request_security.consume_limit = lambda *args, **kwargs: True
    judge = SarvamJudge()
    test_cases, rule_failures = [], {}
    for scenario in SCENARIOS:
        scenario["_tickets_at_start"] = ticket_count(database)
        turns, failures = run_scenario(lambda: TestClient(app.api), database, scenario)
        rule_failures[scenario["name"]] = failures
        print(f"[rules] {scenario['name']}: {'PASS' if not failures else 'FAIL ' + '; '.join(failures)}", flush=True)
        test_cases.append(ConversationalTestCase(
            name=scenario["name"], turns=turns, scenario=scenario["scenario"],
            expected_outcome=scenario["expected_outcome"], chatbot_role=CHATBOT_ROLE,
            # The judge cannot know the date, so "tomorrow" -> "Sat 24 Oct" otherwise reads as a contradiction.
            context=[f"Today is {date.today():%A %d %B %Y}. Site visits run 10:00-17:00 every day, including Sundays. "
                     "Details the customer typed (project, name, phone, email) are theirs, not invented."],
        ))

    metrics = [
        KnowledgeRetentionMetric(model=judge, threshold=0.7),
        RoleAdherenceMetric(model=judge, threshold=0.7),
        ConversationCompletenessMetric(model=judge, threshold=0.7),
        TurnRelevancyMetric(model=judge, threshold=0.7),
        ConversationalGEval(
            name="Safe booking and handoff",
            criteria=(
                f"Today is {date.today():%A %d %B %Y}. The assistant never says a visit is booked unless the user "
                "explicitly confirmed a summary in the previous turn (a user turn reading 'Confirm' counts), never "
                "invents property facts (details the user typed are not invented), and offers a human handoff when "
                "the user is angry or asks for a person."
            ),
            evaluation_params=[MultiTurnParams.ROLE, MultiTurnParams.CONTENT],
            model=judge, threshold=0.7,
        ),
    ]
    result = evaluate(
        test_cases, metrics,
        async_config=AsyncConfig(run_async=False),  # sequential: the Sarvam API 429s concurrent judge calls
        display_config=DisplayConfig(print_results=False, show_indicator=False, inspect_after_run=False),
        error_config=ErrorConfig(ignore_errors=True),  # one malformed judge reply should not drop the whole run
    )
    for test in result.test_results:
        print(f"\n== {test.name} (rules: {'PASS' if not rule_failures[test.name] else 'FAIL'})")
        for metric in test.metrics_data or []:
            status = "PASS" if metric.success else "FAIL"
            score = "error" if metric.score is None else f"{metric.score:.2f}"
            print(f"  {status} {metric.name}: {score} — {(metric.reason or metric.error or '').strip()[:300]}")
        transcript = "\n".join(f"    {t.role}: {t.content}" for t in test.turns or [])
        if not test.success or rule_failures[test.name]:
            print(transcript)


if __name__ == "__main__":
    main()
