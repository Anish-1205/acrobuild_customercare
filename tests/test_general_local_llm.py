import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from graph.main_orchestrator import (
    _build_live_general_llm_response,
    _focus_simple_factual_answer,
    _ground_current_officeholder_answer,
    _ground_current_date_time_answer,
)
from qwen import build_qwen_messages


class GeneralLocalLlmTests(unittest.TestCase):
    def test_general_prompt_provides_current_date_context(self):
        with patch(
            "graph.main_orchestrator.generate_qwen_chat_response",
            return_value="Today is Tuesday.",
        ) as generate:
            response = _build_live_general_llm_response(
                "Do you know what day it is?",
                [{"sender": "customer", "text": "Do you know what day it is?"}],
            )

        system_prompt = generate.call_args.kwargs["system_prompt"]
        self.assertIn("current local date and time is", system_prompt)
        self.assertIn("Use this value directly", system_prompt)
        self.assertEqual(response["agent_mode"], "live_remote_llm")
        self.assertTrue(response["used_llm"])

    def test_hallucinated_model_date_is_replaced_with_runtime_date(self):
        current_time = datetime(2026, 8, 11, 14, 35, tzinfo=ZoneInfo("Asia/Kolkata"))

        answer = _ground_current_date_time_answer(
            "Do you know what day it is?",
            current_time,
        )

        self.assertEqual(answer, "Today is Tuesday, 11 August 2026.")

    def test_current_question_is_not_duplicated_in_qwen_messages(self):
        messages = build_qwen_messages(
            "Be helpful.",
            "What day is it?",
            [
                {"sender": "bot", "text": "Hello!"},
                {"sender": "customer", "text": "What day is it?"},
            ],
        )

        self.assertEqual(
            messages,
            [
                {"role": "system", "content": "Be helpful."},
                {"role": "user", "content": "What day is it?"},
            ],
        )

    def test_social_answer_is_stable_when_model_reply_is_bad(self):
        with patch(
            "graph.main_orchestrator.generate_qwen_chat_response",
            return_value="It seems our conversation is having issues.",
        ):
            response = _build_live_general_llm_response(
                "Hello How is your day going",
                [
                    {"sender": "bot", "text": "Hi! How can I help you today?"},
                    {"sender": "customer", "text": "Hello How is your day going"},
                ],
            )

        self.assertEqual(
            response["answer"],
            "Hi! I'm doing well and ready to help. How is your day going?",
        )

    def test_leading_widget_greeting_is_not_sent_to_qwen(self):
        messages = build_qwen_messages(
            "Be helpful.",
            "What is AI?",
            [{"sender": "bot", "text": "Hi! How can I help you today?"}],
        )

        self.assertEqual(
            messages,
            [
                {"role": "system", "content": "Be helpful."},
                {"role": "user", "content": "What is AI?"},
            ],
        )

    def test_simple_fact_drops_unrequested_model_claims(self):
        answer = _focus_simple_factual_answer(
            "Who was the first prime minister of India?",
            "The first Prime Minister of India was Jawaharlal Nehru. He served on invented dates.",
        )

        self.assertEqual(
            answer,
            "The first Prime Minister of India was Jawaharlal Nehru.",
        )

    def test_current_andhra_pradesh_cm_is_locally_grounded(self):
        self.assertEqual(
            _ground_current_officeholder_answer("Who is CM Of Andhra Pradesh"),
            "The current Chief Minister of Andhra Pradesh is N. Chandrababu Naidu.",
        )

        with patch(
            "graph.main_orchestrator.generate_qwen_chat_response",
            return_value="I do not have real-time data.",
        ):
            response = _build_live_general_llm_response(
                "Who is CM Of Andhra Pradesh",
                [{"sender": "customer", "text": "Who is CM Of Andhra Pradesh"}],
            )
        self.assertEqual(
            response["answer"],
            "The current Chief Minister of Andhra Pradesh is N. Chandrababu Naidu.",
        )


if __name__ == "__main__":
    unittest.main()
