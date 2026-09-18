"""call_booking intent: detection, orchestration routing, and ticket persistence.

Guards the "arrange a call" bug: a call-booking request must never fall through
to the property/general answer path (which could reach
build_support_contact_guidance_line and just print company contact info, or
the general LLM, which could hallucinate a false confirmation, instead of
booking anything) and must actually create a ticket via run_workflow() once a
phone number and time are available.

Continuation across turns (e.g. a bare "9876543210, 5pm" reply with no booking
phrase of its own) must not depend on matching the bot's previous, localized
answer text — services/conversation_store_service.py's invisible
PENDING_CALL_BOOKING_MARKER is the language-independent mechanism for that.
"""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from graph import main_orchestrator as orchestrator
from services.conversation_store_service import PENDING_CALL_BOOKING_MARKER
from services.turn_analysis_service import analyze_turn

# analyze_turn()'s heuristic fallback (used here to avoid a live LLM call) also
# calls matches_live_company_context(), which hits the CS API unless stubbed.
_NO_LIVE_COMPANY_CONTEXT = patch(
    "graph.haystack_conversation_pipeline.search_company_knowledge", return_value=[]
)
_NO_LLM = patch("qwen.generate_qwen_chat_response", side_effect=RuntimeError("no llm in test"))

_FAKE_TICKET = {
    "ticket_id": "TK999", "assigned_agent": "Agent Test", "priority": "Medium",
    "queue_name": "General Queue", "assignment_method": "Auto-Routed",
    "brand_tag": "Acrobuild", "business_hours_tag": "Business Hours",
    "intent_tag": "General Inquiry",
}


class TimeExtractionTests(unittest.TestCase):
    """The hour must never be dropped when a Hindi/Marathi day-part word sits
    next to it — regardless of which side of "baje"/"vajta" it's on."""

    def test_day_part_plus_hour_keeps_the_digit(self):
        cases = {
            "shaam 5 baje call karo": "shaam 5 baje",
            "sandhyakali 5 vajta call kara": "sandhyakali 5 vajta",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                extracted = orchestrator._extract_preferred_time(text)
                self.assertIn(expected, extracted)
                self.assertRegex(extracted, r"\d")

    def test_hour_plus_day_part_reverse_order_also_keeps_the_digit(self):
        for text in ("5 baje shaam call karo", "5 vajta sandhyakali call kara"):
            with self.subTest(text=text):
                self.assertRegex(orchestrator._extract_preferred_time(text), r"\d")

    def test_english_am_pm_is_unaffected(self):
        self.assertEqual(orchestrator._extract_preferred_time("call me at 5pm today"), "5pm")


class CallBookingIntentDetectionTests(unittest.TestCase):
    def test_explicit_english_phrase_is_classified_call_booking(self):
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT:
            analysis = analyze_turn("Can you arrange a callback for me?", [])
        self.assertEqual(analysis.intent, "call_booking")
        self.assertFalse(analysis.is_property)

    def test_romanized_hindi_phrasings_are_classified_call_booking(self):
        for text in (
            "Mujhe callback chahiye",
            "Mujhe call arrange karo",
            "Callback arrange kar do",
            "Wapas call karo",
        ):
            with self.subTest(text=text), _NO_LLM, _NO_LIVE_COMPANY_CONTEXT:
                analysis = analyze_turn(text, [])
            self.assertEqual(analysis.intent, "call_booking", text)

    def test_romanized_marathi_phrasings_are_classified_call_booking(self):
        for text in (
            "Mala callback pahije",
            "Mala call arrange kara",
            "Callback arrange kara",
            "Parat call kara",
        ):
            with self.subTest(text=text), _NO_LLM, _NO_LIVE_COMPANY_CONTEXT:
                analysis = analyze_turn(text, [])
            self.assertEqual(analysis.intent, "call_booking", text)

    def test_generic_agent_request_without_call_wording_stays_property(self):
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT:
            analysis = analyze_turn("I want to talk to a human agent", [])
        self.assertNotEqual(analysis.intent, "call_booking")

    def test_marker_continuation_survives_regardless_of_reply_language(self):
        """The old bug: continuation was keyed to the literal English answer
        text, which is never what gets stored once the answer is localized.
        The marker must fire no matter what language/script the bot's stored
        clarification text is in."""
        for bot_text in (
            f"I can arrange a callback — I just need a phone number and a time.{PENDING_CALL_BOOKING_MARKER}",
            f"Main callback arrange karwa sakta hoon — mujhe number aur samay chahiye.{PENDING_CALL_BOOKING_MARKER}",
            f"Mi callback arrange karu shakto — mala number ani vel havi.{PENDING_CALL_BOOKING_MARKER}",
        ):
            history = [
                {"sender": "customer", "text": "arrange a call please"},
                {"sender": "bot", "text": bot_text},
            ]
            with self.subTest(bot_text=bot_text), _NO_LLM, _NO_LIVE_COMPANY_CONTEXT:
                analysis = analyze_turn("9876543210, 5pm", history)
            self.assertEqual(analysis.intent, "call_booking")

    def test_no_continuation_without_the_marker(self):
        """A bot message that merely resembles the clarification text, but
        without the marker, must not be treated as a pending call booking —
        otherwise any unrelated bot reply mentioning a callback would hijack
        the next turn."""
        history = [
            {"sender": "customer", "text": "arrange a call please"},
            {"sender": "bot", "text": "I can arrange a callback — I just need a phone number and a time."},
        ]
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT:
            analysis = analyze_turn("9876543210, 5pm", history)
        self.assertNotEqual(analysis.intent, "call_booking")


class CallBookingOrchestrationTests(unittest.TestCase):
    def test_call_booking_never_reaches_the_contact_info_answer_path_and_books_a_real_ticket(self):
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT, \
                patch.object(orchestrator, "run_workflow", return_value=_FAKE_TICKET) as run_workflow_mock, \
                patch.object(orchestrator, "build_ai_support_answer") as build_ai_support_answer_mock, \
                patch("services.ai_agent_service.build_support_contact_guidance_line") as contact_line_mock:
            response = orchestrator.run_support_orchestration(
                issue="Please arrange a call, my number is 9876543210, call me at 5pm today",
                conversation_id="",
                customer_email="customer@example.com",
                conversation_messages=[],
            )

        build_ai_support_answer_mock.assert_not_called()
        contact_line_mock.assert_not_called()

        run_workflow_mock.assert_called_once()
        booking_issue = run_workflow_mock.call_args.args[0]
        self.assertIn("Callback request", booking_issue)
        self.assertIn("9876543210", booking_issue)
        self.assertEqual(run_workflow_mock.call_args.args[1], "customer@example.com")

        self.assertEqual(response["route"], "call_booking")
        self.assertEqual(response["ticket_id"], "TK999")
        self.assertIn("TK999", response["answer"])
        self.assertNotIn("pending_call_booking", response)

    def test_missing_phone_or_time_asks_instead_of_booking_and_flags_pending(self):
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT, \
                patch.object(orchestrator, "run_workflow") as run_workflow_mock:
            response = orchestrator.run_support_orchestration(
                issue="Can you arrange a call for me?",
                conversation_id="",
                customer_email="customer@example.com",
                conversation_messages=[],
            )

        run_workflow_mock.assert_not_called()
        self.assertEqual(response["route"], "call_booking")
        self.assertIn("need", response["answer"].lower())
        self.assertTrue(response.get("pending_call_booking"))


class CallBookingFullFlowTests(unittest.TestCase):
    """End-to-end through the real /api/support/assist endpoint, including the
    session-cookie-backed conversation store, in English, romanized Hindi, and
    romanized Marathi — proving the marker (not the localized text) is what
    carries the pending-booking state across turns."""

    @classmethod
    def setUpClass(cls):
        import app as app_module
        cls.client = TestClient(app_module.api)

    def _run_two_turns(self, turn1_issue, turn2_issue, conversation_id):
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT, \
                patch.object(orchestrator, "run_workflow", return_value=dict(_FAKE_TICKET)) as run_workflow_mock:
            first = self.client.post(
                "/api/support/assist",
                json={"issue": turn1_issue, "conversation_id": conversation_id},
            )
            second = self.client.post(
                "/api/support/assist",
                json={"issue": turn2_issue, "conversation_id": conversation_id},
            )
        return first, second, run_workflow_mock

    def test_english_full_flow_books_a_ticket_on_turn_two(self):
        first, second, run_workflow_mock = self._run_two_turns(
            "Can you arrange a call for me?",
            "My number is 9876543210, call me at 5pm today",
            "test-call-booking-flow-english",
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["route"], "call_booking")
        self.assertIsNone(first.json().get("ticket_id"))

        self.assertEqual(second.status_code, 200)
        body = second.json()
        self.assertEqual(body["route"], "call_booking")
        self.assertEqual(body.get("ticket_id"), "TK999")
        run_workflow_mock.assert_called_once()

    def test_romanized_hindi_full_flow_books_a_ticket_on_turn_two_no_hallucination(self):
        first, second, run_workflow_mock = self._run_two_turns(
            "Mujhe callback arrange karna hai",
            "Mera number 9876543210 hai, shaam 5 baje call karo",
            "test-call-booking-flow-hindi",
        )
        self.assertEqual(first.json()["route"], "call_booking")

        body = second.json()
        self.assertEqual(body["route"], "call_booking")
        self.assertEqual(body.get("ticket_id"), "TK999")
        run_workflow_mock.assert_called_once()
        booking_issue = run_workflow_mock.call_args.args[0]
        self.assertIn("9876543210", booking_issue)
        # Regression: the hour must survive alongside the day-part word, not
        # just "Preferred time: shaam" with the "5" silently dropped.
        self.assertIn("Preferred time: shaam 5 baje", booking_issue)

    def test_romanized_marathi_full_flow_books_a_ticket_on_turn_two_no_hallucination(self):
        first, second, run_workflow_mock = self._run_two_turns(
            "Mala callback arrange karayla sanga",
            "Majha number 9876543210 aahe, sandhyakali 5 vajta call kara",
            "test-call-booking-flow-marathi",
        )
        self.assertEqual(first.json()["route"], "call_booking")

        body = second.json()
        self.assertEqual(body["route"], "call_booking")
        self.assertEqual(body.get("ticket_id"), "TK999")
        run_workflow_mock.assert_called_once()
        booking_issue = run_workflow_mock.call_args.args[0]
        self.assertIn("9876543210", booking_issue)
        self.assertIn("Preferred time: sandhyakali 5 vajta", booking_issue)


if __name__ == "__main__":
    unittest.main()
