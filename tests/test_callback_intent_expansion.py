"""Regression tests for expanded callback/call-booking intent detection.

Covers new natural-language phrases, false-positive protection,
and the ACT-005/ACT-006 acceptance sequence.
"""

import unittest
from unittest.mock import patch

from services.turn_analysis_service import _is_call_booking_phrase, analyze_turn
from services.conversation_store_service import PENDING_CALL_BOOKING_MARKER

_NO_LLM = patch("qwen.generate_qwen_chat_response", side_effect=RuntimeError("no llm in test"))
_NO_LIVE_COMPANY_CONTEXT = patch(
    "graph.haystack_conversation_pipeline.search_company_knowledge", return_value=[],
)


class TestNewCallbackPhrases(unittest.TestCase):
    """Common natural callback phrasings that previously fell through."""

    def test_imperative_have_someone_call_me(self):
        for phrase in (
            "Please have someone call me",
            "Have someone call me",
            "Have your team call me",
        ):
            with self.subTest(phrase=phrase):
                self.assertTrue(_is_call_booking_phrase(phrase))

    def test_question_can_someone_call_me(self):
        for phrase in (
            "Can someone call me?",
            "Can your team call me?",
            "Can your sales team call me?",
            "Could someone call me?",
        ):
            with self.subTest(phrase=phrase):
                self.assertTrue(_is_call_booking_phrase(phrase))

    def test_want_need_callback(self):
        for phrase in (
            "I want a callback",
            "I need a callback",
            "I want a call back",
            "I need a call back",
            "I would like a callback",
        ):
            with self.subTest(phrase=phrase):
                self.assertTrue(_is_call_booking_phrase(phrase))

    def test_can_i_get_callback(self):
        for phrase in (
            "Can I get a callback?",
            "Can I get a call?",
            "Could I get a callback?",
            "Can I have a callback?",
            "Can I request a call?",
        ):
            with self.subTest(phrase=phrase):
                self.assertTrue(_is_call_booking_phrase(phrase))

    def test_please_call_me(self):
        self.assertTrue(_is_call_booking_phrase("Please call me"))

    def test_ask_someone_to_call(self):
        self.assertTrue(_is_call_booking_phrase("Ask someone to call me"))

    def test_would_like_someone_to_call(self):
        for phrase in (
            "I would like someone to call me",
            "I want someone to call me",
        ):
            with self.subTest(phrase=phrase):
                self.assertTrue(_is_call_booking_phrase(phrase))

    def test_contact_by_phone(self):
        self.assertTrue(_is_call_booking_phrase("Could someone contact me by phone?"))


class TestExistingPhrasesStillWork(unittest.TestCase):
    """Phrases that already worked must continue working."""

    def test_existing_english(self):
        for phrase in (
            "arrange a call",
            "schedule a callback",
            "book a call",
            "request a callback",
            "call me back",
        ):
            with self.subTest(phrase=phrase):
                self.assertTrue(_is_call_booking_phrase(phrase))

    def test_existing_hindi_marathi(self):
        for phrase in (
            "Mujhe callback chahiye",
            "Callback arrange karo",
            "Wapas call karo",
            "Mala callback pahije",
            "Parat call kara",
        ):
            with self.subTest(phrase=phrase):
                self.assertTrue(_is_call_booking_phrase(phrase))


class TestFalsePositiveProtection(unittest.TestCase):
    """Ordinary uses of 'call' must NOT trigger callback intent."""

    def test_non_callback_call_uses(self):
        for phrase in (
            "What do you call this project?",
            "Call this project Vishwajeet Prime",
            "What is this feature called?",
            "What are the calling hours?",
            "The builder called this phase A",
            "Can you call the API?",
        ):
            with self.subTest(phrase=phrase):
                self.assertFalse(_is_call_booking_phrase(phrase))

    def test_other_intents_not_intercepted(self):
        for phrase in (
            "I want to book a site visit",
            "What amenities does Vishwajeet Prime have?",
            "Hi",
            "What is the price of 3 BHK?",
            "Tell me about Vishwajeet Prime",
            "I want to talk to a human agent",
            "What offers are available?",
            "Where is the project located?",
            "Any discounts right now?",
            "Send me the brochure",
            "How much have I paid?",
        ):
            with self.subTest(phrase=phrase):
                self.assertFalse(_is_call_booking_phrase(phrase))


class TestIntentClassification(unittest.TestCase):
    """New phrases should classify as call_booking via analyze_turn."""

    def test_act005_phrase_classifies_as_call_booking(self):
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT:
            analysis = analyze_turn("Please have someone call me", [])
        self.assertEqual(analysis.intent, "call_booking")

    def test_want_callback_classifies_as_call_booking(self):
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT:
            analysis = analyze_turn("I want a callback", [])
        self.assertEqual(analysis.intent, "call_booking")

    def test_can_someone_call_classifies_as_call_booking(self):
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT:
            analysis = analyze_turn("Can someone call me?", [])
        self.assertEqual(analysis.intent, "call_booking")


class TestCallbackStateFlow(unittest.TestCase):
    """Verify pending state is established and malformed phone stays in flow."""

    _FAKE_TICKET = {
        "ticket_id": "TK999", "assigned_agent": "Agent Test", "priority": "Medium",
        "queue_name": "General Queue", "assignment_method": "Auto-Routed",
        "brand_tag": "Acrobuild", "business_hours_tag": "Business Hours",
        "intent_tag": "General Inquiry",
    }

    def test_act005_creates_pending_state(self):
        from graph import main_orchestrator as orchestrator
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT, \
                patch.object(orchestrator, "run_workflow", return_value=self._FAKE_TICKET):
            response = orchestrator.run_support_orchestration(
                issue="Please have someone call me",
                conversation_id="",
                customer_email="",
                conversation_messages=[],
            )
        self.assertTrue(response.get("pending_call_booking"))

    def test_act006_malformed_phone_stays_in_flow(self):
        from graph import main_orchestrator as orchestrator
        pending_answer = f"Some pending text{PENDING_CALL_BOOKING_MARKER}"
        history = [
            {"sender": "customer", "text": "Please have someone call me"},
            {"sender": "bot", "text": pending_answer},
        ]
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT, \
                patch.object(orchestrator, "run_workflow", return_value=self._FAKE_TICKET):
            response = orchestrator.run_support_orchestration(
                issue="123",
                conversation_id="",
                customer_email="",
                conversation_messages=history,
            )
        self.assertTrue(response.get("pending_call_booking"))
        answer = response.get("answer", "").lower()
        self.assertTrue("phone" in answer or "number" in answer or "digit" in answer)
