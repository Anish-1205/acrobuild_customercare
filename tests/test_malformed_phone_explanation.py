"""The "that doesn't look like a valid phone number" explanation must survive.

Two real problems this file locks down.

1. Only ONE malformed shape was ever explained. _malformed_phone_reason()
   returned a reason only for a run of exactly 10 digits whose first digit was
   wrong. Every other rejected shape -- most importantly the very common
   "0" + valid 10-digit number, and anything too short or too long -- was
   rejected silently, so the bot re-asked for name and phone as if the
   customer had typed nothing. Live transcript of the bug (English):

       customer: Can I talk to a representative?
       bot:      I can connect you with a representative - I just need your
                 name and a phone number. Could you share that?
       customer: 09876543210
       bot:      I can connect you with a representative - I just need your
                 name and a phone number. Could you share that?     <-- no reason

2. It could regress invisibly. The visible sentence is localized into the
   customer's language before it leaves the app, so the pre-existing HTTP
   test could only assert structural fields (route, ticket_id) and explicitly
   gave up on asserting the wording -- which is exactly the thing that went
   missing. The payload now carries `phone_rejection_reason`, a
   language-independent twin of that sentence, and these tests assert on it
   in all four supported languages.
"""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from graph import main_orchestrator as orchestrator
from services.conversation_store_service import (
    PENDING_CALL_BOOKING_MARKER,
    PENDING_HUMAN_CONTACT_MARKER,
)

_NO_LLM = patch("qwen.generate_qwen_chat_response", side_effect=RuntimeError("no llm in test"))
_NO_LIVE_COMPANY_CONTEXT = patch(
    "graph.haystack_conversation_pipeline.search_company_knowledge", return_value=[]
)

_PENDING_CONTACT_BOT_TURN = {
    "sender": "bot",
    "text": "I can connect you with a representative — I just need your name and a "
            f"phone number. Could you share that?{PENDING_HUMAN_CONTACT_MARKER}",
}
_PENDING_BOOKING_BOT_TURN = {
    "sender": "bot",
    "text": "I can arrange a callback — I just need a callback phone number and a "
            f"preferred time. Could you share that?{PENDING_CALL_BOOKING_MARKER}",
}


class MalformedPhoneReasonTests(unittest.TestCase):
    """Unit level: every shape _PHONE_RE refuses must produce a reason, and
    every shape it accepts must produce none."""

    def test_leading_zero_before_a_valid_number_is_explained(self):
        # The regression that started this file: 11 digits, "0" + a perfectly
        # good mobile number. _PHONE_RE cannot match it (the \b never lands
        # between "0" and "9"), and the old reason check skipped it because
        # len(digits) != 10.
        reason = orchestrator._malformed_phone_reason("09876543210")
        self.assertTrue(reason)
        self.assertIn("extra 0", reason)

    def test_ten_digits_with_a_wrong_start_digit_is_explained(self):
        for number in ("0123456789", "5876543210", "+91 5876543210"):
            with self.subTest(number=number):
                reason = orchestrator._malformed_phone_reason(number)
                self.assertTrue(reason, number)
                self.assertIn("6, 7, 8, or 9", reason)

    def test_wrong_length_is_explained_with_the_length(self):
        for number, digits in (("98765432", 8), ("987654321", 9), ("98765432101234", 14)):
            with self.subTest(number=number):
                reason = orchestrator._malformed_phone_reason(number)
                self.assertTrue(reason, number)
                self.assertIn(str(digits), reason)

    def test_separators_do_not_hide_a_malformed_number(self):
        reason = orchestrator._malformed_phone_reason("0 98765 43210")
        self.assertIn("extra 0", reason)

    def test_valid_numbers_produce_no_reason(self):
        for number in ("9876543210", "+91 9876543210", "91 9876543210", "6123456789"):
            with self.subTest(number=number):
                self.assertEqual(orchestrator._malformed_phone_reason(number), "", number)

    def test_ordinary_numbers_in_a_sentence_are_not_read_as_phone_attempts(self):
        for text in ("I want a 2 BHK", "my budget is 45,00,000", "Anish", ""):
            with self.subTest(text=text):
                self.assertEqual(orchestrator._malformed_phone_reason(text), "", text)


class ReasonIsScopedToTheCurrentMessageTests(unittest.TestCase):
    """A bad number from an earlier turn must not be complained about again on
    a later turn that contains no number at all."""

    def test_earlier_bad_number_is_not_re_explained_on_a_later_turn(self):
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT, patch.object(orchestrator, "run_workflow"):
            response = orchestrator.run_support_orchestration(
                issue="Anish",
                conversation_messages=[
                    {"sender": "customer", "text": "Can I talk to a representative?"},
                    _PENDING_CONTACT_BOT_TURN,
                    {"sender": "customer", "text": "09876543210"},
                    _PENDING_CONTACT_BOT_TURN,
                ],
            )
        self.assertEqual(response["route"], "human_contact")
        self.assertNotIn("phone_rejection_reason", response)
        self.assertNotIn("valid phone number", response["answer"])


class MalformedPhoneOverHttpTests(unittest.TestCase):
    """End to end through the real router, in all four supported languages.

    Asserted on `phone_rejection_reason` rather than the answer text: the
    answer is localized, and asserting English wording is precisely what the
    earlier test could not do -- which is how the explanation went missing
    without any test noticing."""

    @classmethod
    def setUpClass(cls):
        import app as app_module
        cls.client = TestClient(app_module.api)

    def _second_turn(self, conversation_id, opener, reply):
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT, patch.object(orchestrator, "run_workflow"):
            self.client.post("/api/support/assist", json={
                "issue": opener, "conversation_id": conversation_id,
            })
            return self.client.post("/api/support/assist", json={
                "issue": reply, "conversation_id": conversation_id,
            }).json()

    def test_every_language_gets_the_explanation_for_a_leading_zero_number(self):
        openers = {
            "english": "Can I talk to a representative?",
            "hindi": "mujhe kisi representative se baat karni hai",
            "marathi": "mala kunitari pratinidhi shi bolaycha aahe",
            "telugu": "nenu okka representative tho matladoccha?",
        }
        for language, opener in openers.items():
            with self.subTest(language=language):
                payload = self._second_turn(
                    f"malformed-phone-{language}", opener, "09876543210",
                )
                self.assertEqual(payload["route"], "human_contact")
                self.assertIsNone(payload.get("ticket_id"))
                self.assertIn("extra 0", payload.get("phone_rejection_reason", ""))

    def test_a_valid_number_is_accepted_with_no_rejection_reason(self):
        payload = self._second_turn(
            "valid-phone-english", "Can I talk to a representative?",
            "I'm Anish, 9876543210",
        )
        self.assertEqual(payload["route"], "human_contact")
        self.assertNotIn("phone_rejection_reason", payload)

    def test_marathi_name_word_is_not_captured_as_part_of_the_name(self):
        """Live transcript bug: "majha naav Anish aahe" booked a ticket for
        "Naav Anish" -- the Marathi word for "name" was not a filler word."""
        name = orchestrator._extract_contact_name(["majha naav Anish aahe"], "")
        self.assertEqual(name, "Anish")

    def test_call_booking_explains_a_malformed_number_too(self):
        """The callback flow had the identical silent rejection."""
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT, patch.object(orchestrator, "run_workflow"):
            response = orchestrator.run_support_orchestration(
                issue="09876543210",
                conversation_messages=[
                    {"sender": "customer", "text": "please arrange a callback"},
                    _PENDING_BOOKING_BOT_TURN,
                ],
            )
        self.assertEqual(response["route"], "call_booking")
        self.assertIn("extra 0", response.get("phone_rejection_reason", ""))


if __name__ == "__main__":
    unittest.main()
