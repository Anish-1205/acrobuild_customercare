"""human_contact intent: detection, orchestration routing, and ticket
persistence.

Closes a real hallucinated-confirmation bug (this session, logs/chatbot.log,
conversation 968c9f64-8156-45d8-91fd-6f9f94573551): a Telugu "talk to a
representative" request ("nenu okka representative tho matladoccha?") fell
through to the pure-LLM general chat path (_build_live_general_llm_response),
which claimed a ticket was created and a representative would call, with
zero DB rows actually created -- confirmed via direct sqlite inspection.

This intent, detected deterministically (language-independent phrase
matching, same architecture as call_booking), must never let that request
reach the general LLM path, and must call run_workflow() for real before
ever confirming anything to the customer.
"""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from graph import main_orchestrator as orchestrator
from services.conversation_store_service import PENDING_HUMAN_CONTACT_MARKER
from services.turn_analysis_service import analyze_turn

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


class HumanContactIntentDetectionTests(unittest.TestCase):
    def test_original_telugu_bug_phrase_is_classified_human_contact(self):
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT:
            analysis = analyze_turn("nenu okka representative tho matladoccha?", [])
        self.assertEqual(analysis.intent, "human_contact")
        self.assertFalse(analysis.is_property)

    def test_english_phrasings_are_classified_human_contact(self):
        for text in (
            "Can I talk to a representative?",
            "I want to speak to a human",
            "connect me to your team",
            "I want to speak to someone at Acrobuild",
        ):
            with self.subTest(text=text), _NO_LLM, _NO_LIVE_COMPANY_CONTEXT:
                analysis = analyze_turn(text, [])
            self.assertEqual(analysis.intent, "human_contact", text)

    def test_romanized_hindi_phrasings_are_classified_human_contact(self):
        for text in (
            "mujhe kisi representative se baat karni hai",
            "kisi insaan se baat karni hai",
            "apni team se connect karo",
        ):
            with self.subTest(text=text), _NO_LLM, _NO_LIVE_COMPANY_CONTEXT:
                analysis = analyze_turn(text, [])
            self.assertEqual(analysis.intent, "human_contact", text)

    def test_romanized_marathi_phrasings_are_classified_human_contact(self):
        for text in (
            "mala pratinidhishi bolaycha aahe",
            "mala agent shi bolaycha aahe",
        ):
            with self.subTest(text=text), _NO_LLM, _NO_LIVE_COMPANY_CONTEXT:
                analysis = analyze_turn(text, [])
            self.assertEqual(analysis.intent, "human_contact", text)

    def test_romanized_telugu_phrasings_are_classified_human_contact(self):
        for text in (
            "nenu okka representative tho matladali",
            "meeku team tho connect avvocha",
        ):
            with self.subTest(text=text), _NO_LLM, _NO_LIVE_COMPANY_CONTEXT:
                analysis = analyze_turn(text, [])
            self.assertEqual(analysis.intent, "human_contact", text)

    def test_vague_talk_to_someone_without_a_role_or_company_stays_general(self):
        """Distinct from human_contact: no role noun and no company reference
        -- this is the genuinely vague case the "unsure" action menu handles,
        not an explicit human-contact request."""
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT:
            analysis = analyze_turn("I want to talk to someone", [])
        self.assertNotEqual(analysis.intent, "human_contact")

    def test_explicit_call_scheduling_with_representative_wording_stays_call_booking(self):
        """Distinct from call_booking: an explicit scheduling ask keeps going
        to the more specific, already-existing flow."""
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT:
            analysis = analyze_turn("arrange a call with a representative", [])
        self.assertEqual(analysis.intent, "call_booking")

    def test_marker_continuation_survives_regardless_of_reply_language(self):
        for bot_text in (
            f"I can connect you with a representative — I just need your name and a phone number. Could you share that?{PENDING_HUMAN_CONTACT_MARKER}",
            f"Nenu mimmulni representative tho connect cheyagalanu — mee peru mariyu number kavali.{PENDING_HUMAN_CONTACT_MARKER}",
        ):
            history = [
                {"sender": "customer", "text": "nenu okka representative tho matladoccha?"},
                {"sender": "bot", "text": bot_text},
            ]
            with self.subTest(bot_text=bot_text), _NO_LLM, _NO_LIVE_COMPANY_CONTEXT:
                analysis = analyze_turn("anish, 9876543210", history)
            self.assertEqual(analysis.intent, "human_contact")

    def test_no_continuation_without_the_marker(self):
        history = [
            {"sender": "customer", "text": "nenu okka representative tho matladoccha?"},
            {"sender": "bot", "text": "I can connect you with a representative — I just need your name and a phone number."},
        ]
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT:
            analysis = analyze_turn("anish, 9876543210", history)
        self.assertNotEqual(analysis.intent, "human_contact")


class ContactNameExtractionTests(unittest.TestCase):
    """The trigger phrase itself must never leak into the extracted name --
    found live: "nenu okka representative tho matladoccha?" alone (Telugu
    "I"/"with" not on the original filler list) used to extract a bogus name
    ("Nenu Tho"), which made the first clarification ask only for a phone
    number instead of name + phone."""

    def test_telugu_trigger_phrase_alone_yields_no_bogus_name(self):
        text = "nenu okka representative tho matladoccha?"
        phone = orchestrator._extract_phone_number(text)
        name = orchestrator._extract_contact_name([text], phone)
        self.assertEqual(name, "")

    def test_first_turn_with_only_the_trigger_phrase_asks_for_both_name_and_phone(self):
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT, \
                patch.object(orchestrator, "run_workflow") as run_workflow_mock:
            response = orchestrator.run_support_orchestration(
                issue="nenu okka representative tho matladoccha?",
                conversation_id="",
                customer_email="",
                conversation_messages=[],
            )
        run_workflow_mock.assert_not_called()
        answer_lower = response["answer"].lower()
        self.assertIn("name", answer_lower)
        self.assertIn("phone", answer_lower)


class StuckLoopRegressionTests(unittest.TestCase):
    """The exact stuck-loop bug reported live in Telugu: once a valid phone
    is accepted, name extraction only ever looked at the current message, so
    if the customer's later replies never happened to also contain a name
    (e.g. more phone-number retries), the flow could never progress -- even
    though phone extraction itself scans a multi-turn window. Also covers
    the malformed-phone silence: a leading-zero number is correctly
    rejected by _PHONE_RE, but the bot used to re-ask for both fields with
    no explanation, as if the input had never been read."""

    def test_leading_zero_phone_gets_a_clear_reason_not_a_silent_both_fields_reask(self):
        # A pending-marker bot turn, exactly as routers/assist.py persists it,
        # so this message is correctly read as a human_contact continuation
        # (matches production behavior -- without the marker it would fall
        # through to the general LLM path instead, which is a different,
        # already-covered scenario).
        pending_bot_text = (
            f"I can connect you with a representative — I just need your name and a "
            f"phone number. Could you share that?{PENDING_HUMAN_CONTACT_MARKER}"
        )
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT, \
                patch.object(orchestrator, "run_workflow") as run_workflow_mock:
            response = orchestrator.run_support_orchestration(
                issue="0123456789",
                conversation_id="",
                customer_email="",
                conversation_messages=[
                    {"sender": "customer", "text": "nenu okka representative tho matladoccha?"},
                    {"sender": "bot", "text": pending_bot_text},
                ],
            )
        run_workflow_mock.assert_not_called()
        self.assertEqual(response["route"], "human_contact")
        answer_lower = response["answer"].lower()
        self.assertIn("doesn't look like a valid phone number", answer_lower)
        self.assertIn("6, 7, 8, or 9", answer_lower)

    def test_labeled_number_string_extracts_the_phone_and_no_name(self):
        """Extraction-level check: "number : 9876541230" alone yields a valid
        phone (the label word is filtered) and no name (a labeled phone
        reply is not a name)."""
        phone = orchestrator._extract_phone_number(
            orchestrator._call_booking_search_text("number : 9876541230", [])
        )
        self.assertEqual(phone, "9876541230")
        name = orchestrator._extract_contact_name(
            orchestrator._human_contact_name_candidates("number : 9876541230", []), phone,
        )
        self.assertEqual(name, "")

    def test_exact_reported_four_turn_sequence_then_progresses_once_a_name_is_given(self):
        """Reproduces the live bug report turn for turn (none of those 4
        messages ever contains a name, so correctly asking for it each time
        is NOT the bug -- the bug is failing to progress once a name
        finally is given). A 5th turn supplies the name and must succeed."""
        import app as app_module
        client = TestClient(app_module.api)
        conversation_id = "test-stuck-loop-four-turn-repro"

        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT, \
                patch.object(orchestrator, "run_workflow", return_value=dict(_FAKE_TICKET)) as run_workflow_mock:
            turn1 = client.post("/api/support/assist", json={
                "issue": "nenu okka representative tho matladoccha?", "conversation_id": conversation_id,
            })
            turn2 = client.post("/api/support/assist", json={
                "issue": "0123456789", "conversation_id": conversation_id,
            })
            turn3 = client.post("/api/support/assist", json={
                "issue": "9102345678", "conversation_id": conversation_id,
            })
            turn4 = client.post("/api/support/assist", json={
                "issue": "number : 9876541230", "conversation_id": conversation_id,
            })
            turn5 = client.post("/api/support/assist", json={
                "issue": "Anish", "conversation_id": conversation_id,
            })

        # Answers are localized to the customer's language for this endpoint
        # (heuristic-detected as Telugu here), so assertions below check
        # structural fields (route, ticket_id) rather than English wording
        # that would not survive translation.
        for turn in (turn1, turn2, turn3, turn4):
            self.assertEqual(turn.status_code, 200)
            self.assertEqual(turn.json()["route"], "human_contact")
            self.assertIsNone(turn.json().get("ticket_id"))
        self.assertEqual(turn5.status_code, 200)

        run_workflow_mock.assert_called_once()
        self.assertEqual(turn5.json().get("ticket_id"), "TK999")
        contact_issue = run_workflow_mock.call_args.args[0]
        self.assertIn("Anish", contact_issue)
        # Either of the two valid phone numbers given across the conversation
        # is acceptable here -- which one the shared, pre-existing
        # call_booking search-window picks when the final turn supplies no
        # phone of its own is out of this fix's scope; what matters is that
        # the flow progresses and books a real ticket instead of staying stuck.
        self.assertTrue(
            "9102345678" in contact_issue or "9876541230" in contact_issue,
            contact_issue,
        )


class HumanContactOrchestrationTests(unittest.TestCase):
    def test_human_contact_never_reaches_the_general_llm_path_and_books_a_real_ticket(self):
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT, \
                patch.object(orchestrator, "run_workflow", return_value=_FAKE_TICKET) as run_workflow_mock, \
                patch.object(orchestrator, "_build_live_general_llm_response") as general_llm_mock:
            response = orchestrator.run_support_orchestration(
                issue="Can I talk to a representative? I'm Anish, my number is 9876543210",
                conversation_id="",
                customer_email="customer@example.com",
                conversation_messages=[],
            )

        general_llm_mock.assert_not_called()
        run_workflow_mock.assert_called_once()
        contact_issue = run_workflow_mock.call_args.args[0]
        self.assertIn("Human contact request", contact_issue)
        self.assertIn("Anish", contact_issue)
        self.assertIn("9876543210", contact_issue)
        self.assertEqual(run_workflow_mock.call_args.args[1], "customer@example.com")

        self.assertEqual(response["route"], "human_contact")
        self.assertEqual(response["ticket_id"], "TK999")
        self.assertIn("TK999", response["answer"])
        self.assertNotIn("pending_human_contact", response)

    def test_missing_name_or_phone_asks_instead_of_booking_and_flags_pending(self):
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT, \
                patch.object(orchestrator, "run_workflow") as run_workflow_mock:
            response = orchestrator.run_support_orchestration(
                issue="Can I talk to a representative?",
                conversation_id="",
                customer_email="customer@example.com",
                conversation_messages=[],
            )

        run_workflow_mock.assert_not_called()
        self.assertEqual(response["route"], "human_contact")
        self.assertIn("name", response["answer"].lower())
        self.assertTrue(response.get("pending_human_contact"))


class HumanContactFullFlowTests(unittest.TestCase):
    """End-to-end through the real /api/support/assist endpoint, reproducing
    the exact original Telugu conversation from this session."""

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

    def test_original_telugu_conversation_now_books_a_real_ticket(self):
        first, second, run_workflow_mock = self._run_two_turns(
            "nenu okka representative tho matladoccha?",
            "anish, 9876543210",
            "test-human-contact-flow-telugu",
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["route"], "human_contact")
        self.assertIsNone(first.json().get("ticket_id"))

        self.assertEqual(second.status_code, 200)
        body = second.json()
        self.assertEqual(body["route"], "human_contact")
        self.assertEqual(body.get("ticket_id"), "TK999")
        run_workflow_mock.assert_called_once()
        contact_issue = run_workflow_mock.call_args.args[0]
        self.assertIn("Anish", contact_issue)
        self.assertIn("9876543210", contact_issue)

    def test_english_full_flow(self):
        first, second, run_workflow_mock = self._run_two_turns(
            "Can I talk to a representative?",
            "My name is Anish, number is 9876543210",
            "test-human-contact-flow-english",
        )
        self.assertEqual(first.json()["route"], "human_contact")
        body = second.json()
        self.assertEqual(body.get("ticket_id"), "TK999")
        run_workflow_mock.assert_called_once()

    def test_romanized_hindi_full_flow(self):
        first, second, run_workflow_mock = self._run_two_turns(
            "mujhe kisi representative se baat karni hai",
            "mera naam Anish hai, number 9876543210",
            "test-human-contact-flow-hindi",
        )
        self.assertEqual(first.json()["route"], "human_contact")
        body = second.json()
        self.assertEqual(body.get("ticket_id"), "TK999")
        run_workflow_mock.assert_called_once()

    def test_romanized_marathi_full_flow(self):
        first, second, run_workflow_mock = self._run_two_turns(
            "mala pratinidhishi bolaycha aahe",
            "Anish, 9876543210",
            "test-human-contact-flow-marathi",
        )
        self.assertEqual(first.json()["route"], "human_contact")
        body = second.json()
        self.assertEqual(body.get("ticket_id"), "TK999")
        run_workflow_mock.assert_called_once()


class GeneralLlmGuardrailTests(unittest.TestCase):
    """Backstop check: even when a phrasing the new detector doesn't catch
    still reaches the general LLM path, the system prompt must forbid a
    false completed-action claim. We can't control what a live model says,
    so this checks the guardrail text itself is present and unambiguous."""

    def test_system_prompt_forbids_false_completed_action_claims(self):
        prompt = orchestrator._general_chat_system_prompt("Friday, 18 September 2026 at 02:00 PM IST")
        lowered = prompt.lower()
        self.assertIn("cannot yourself create a ticket", lowered)
        self.assertIn("never say, in any language, that you have created a ticket", lowered)
        self.assertIn("never state or imply a reference/ticket number", lowered)
        self.assertIn("never invent a new or different one", lowered)


if __name__ == "__main__":
    unittest.main()
