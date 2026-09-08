import unittest
from unittest.mock import patch

from graph.haystack_conversation_pipeline import (
    build_deterministic_conversation_answer,
    classify_conversation_route,
    resolve_contextual_support_issue,
    run_conversation_pipeline,
    validate_general_answer,
)


class HaystackConversationPipelineTests(unittest.TestCase):
    def run_pipeline(self, issue):
        calls = []

        def support_handler():
            calls.append(issue)
            return {
                "agent_mode": "existing_support",
                "answer": "Vishwajeet Myspace has available 2 BHK homes on floor 3 with a live rate of INR 2,900 per sq. ft.",
            }

        response = run_conversation_pipeline(
            issue=issue,
            conversation_messages=[],
            support_handler=support_handler,
        )
        return response, calls

    def test_joke_uses_haystack_pipeline(self):
        response, calls = self.run_pipeline("Tell me a joke")
        self.assertEqual(response["agent_mode"], "conversation_haystack")
        self.assertIn("next level", response["answer"])
        self.assertEqual(calls, [])

    def test_how_are_you_uses_haystack_pipeline(self):
        response, calls = self.run_pipeline("How are you?")
        self.assertEqual(response["agent_mode"], "conversation_haystack")
        self.assertEqual(calls, [])

    def test_greeting_with_day_question_gets_a_natural_answer(self):
        response, calls = self.run_pipeline("Hi! How is your day?")
        self.assertEqual(response["agent_mode"], "conversation_haystack")
        self.assertIn("doing well", response["answer"])
        self.assertNotIn("same page", response["answer"])
        self.assertEqual(calls, [])

    def test_positive_social_reply_does_not_ask_for_more_detail(self):
        response, calls = self.run_pipeline("Great")
        self.assertEqual(response["agent_mode"], "conversation_haystack")
        self.assertEqual(response["answer"], "Glad to hear it! What can I help you with today?")
        self.assertEqual(calls, [])

    def test_common_mood_replies_receive_human_social_responses(self):
        positive = ("Fine", "I'm fine", "Doing good", "Pretty good", "All good", "OK")
        for issue in positive:
            with self.subTest(issue=issue):
                response, calls = self.run_pipeline(issue)
                self.assertIn("Glad to hear", response["answer"])
                self.assertNotIn("more detail", response["answer"])
                self.assertEqual(calls, [])

        response, calls = self.run_pipeline("Not good")
        self.assertIn("sorry to hear", response["answer"])
        self.assertEqual(calls, [])

    def test_yes_after_project_prompt_continues_support_flow(self):
        calls = []

        response = run_conversation_pipeline(
            issue="Yes",
            conversation_messages=[
                {
                    "sender": "bot",
                    "text": "Would you like to explore Vishwajeet Paradise?",
                },
                {"sender": "customer", "text": "Yes"},
            ],
            support_handler=lambda: calls.append("support") or {
                "agent_mode": "existing_support",
                "answer": "Vishwajeet Paradise project details are ready to explore.",
            },
        )

        self.assertEqual(response["agent_mode"], "existing_support")
        self.assertEqual(calls, ["support"])
    def test_bare_this_defaults_to_the_active_project(self):
        messages = [
            {
                "sender": "bot",
                "text": "Vishwajeet Empire is available. What would you like to know?",
            },
            {"sender": "customer", "text": "Tell me more about this"},
        ]
        with patch(
            "graph.haystack_conversation_pipeline.get_live_project_names",
            return_value=["Vishwajeet Empire"],
        ):
            resolved = resolve_contextual_support_issue("Tell me more about this", messages)
        self.assertEqual(resolved, "Tell me more about project Vishwajeet Empire")
    def test_this_project_does_not_inherit_recommended_wing_or_floor(self):
        messages = [
            {
                "sender": "bot",
                "text": (
                    "The highest-priced home is in Vishwajeet Prime. "
                    "The available option is in B wing, ground floor, unit 5."
                ),
            },
            {"sender": "customer", "text": "Tell me more about this project"},
        ]
        with patch(
            "graph.haystack_conversation_pipeline.get_live_project_names",
            return_value=["Vishwajeet Prime"],
        ):
            resolved = resolve_contextual_support_issue(
                "Tell me more about this project",
                messages,
            )
        self.assertEqual(resolved, "Tell me more about project Vishwajeet Prime")
        self.assertNotIn("B wing", resolved)

    def test_this_wing_retains_the_recommended_wing(self):
        messages = [
            {
                "sender": "bot",
                "text": (
                    "The highest-priced home is in Vishwajeet Prime. "
                    "The available option is in B wing, ground floor, unit 5."
                ),
            },
            {"sender": "customer", "text": "Tell me more about this wing"},
        ]
        with patch(
            "graph.haystack_conversation_pipeline.get_live_project_names",
            return_value=["Vishwajeet Prime"],
        ):
            resolved = resolve_contextual_support_issue(
                "Tell me more about this wing",
                messages,
            )
        self.assertIn("B wing", resolved)
        self.assertIn("Vishwajeet Prime", resolved)
    def test_this_project_follow_up_keeps_the_single_recent_project(self):
        messages = [
            {
                "sender": "customer",
                "text": "Tell me about the project you have more number of floors",
            },
            {
                "sender": "bot",
                "text": "Vishwajeet Precious has the most floors: 16.",
            },
            {
                "sender": "customer",
                "text": "What is special about this project",
            },
        ]
        with patch(
            "graph.haystack_conversation_pipeline.get_live_project_names",
            return_value=["Vishwajeet Paradise", "Vishwajeet Precious"],
        ):
            resolved = resolve_contextual_support_issue(
                "What is special about this project",
                messages,
            )
        self.assertEqual(resolved, "What is special about project Vishwajeet Precious")

    def test_catalogue_with_many_projects_is_not_treated_as_a_selection(self):
        messages = [{
            "sender": "bot",
            "text": "1. Vishwajeet Paradise\n2. Vishwajeet Precious\nChoose a project.",
        }]
        with patch(
            "graph.haystack_conversation_pipeline.get_live_project_names",
            return_value=["Vishwajeet Paradise", "Vishwajeet Precious"],
        ):
            from graph.haystack_conversation_pipeline import _conversation_project_name
            selected = _conversation_project_name(messages)
        self.assertEqual(selected, "")
    def test_letter_wing_selection_uses_the_listed_api_wing(self):
        messages = [
            {"sender": "customer", "text": "Anything about Myspace project?"},
            {
                "sender": "bot",
                "text": (
                    "Vishwajeet Myspace has 4 wings:\n\n"
                    "- Jupiter C: 15 floors\n"
                    "- Jupiter D: 15 floors\n"
                    "- Venus A: 15 floors\n"
                    "- Venus B: 15 floors\n\n"
                    "Choose a wing to continue."
                ),
            },
            {"sender": "customer", "text": "lets go with A"},
        ]
        with patch(
            "graph.haystack_conversation_pipeline.get_live_project_names",
            return_value=["Vishwajeet Myspace"],
        ):
            resolved = resolve_contextual_support_issue("lets go with A", messages)
        self.assertEqual(
            resolved,
            "Show verified details for Venus A wing in Vishwajeet Myspace",
        )
        self.assertNotIn("Jupiter A", resolved)

    def test_yes_retains_selected_project_and_wing(self):
        messages = [
            {"sender": "customer", "text": "Anything about Myspace project?"},
            {
                "sender": "bot",
                "text": "Got it - Venus A wing in Vishwajeet Myspace. It has 15 floors. Would you like details?",
            },
            {"sender": "customer", "text": "yes please"},
        ]
        with patch(
            "graph.haystack_conversation_pipeline.get_live_project_names",
            return_value=["Vishwajeet Myspace"],
        ):
            resolved = resolve_contextual_support_issue("yes please", messages)
        self.assertIn("Venus A wing", resolved)
        self.assertIn("Vishwajeet Myspace", resolved)
    def test_property_question_delegates_to_existing_support(self):
        response, calls = self.run_pipeline("Do you have any 2 BHK homes available?")
        self.assertEqual(response["agent_mode"], "existing_support")
        self.assertEqual(len(calls), 1)

    def test_mixed_greeting_and_property_prefers_support(self):
        response, calls = self.run_pipeline("Hi, show me available homes in Vishwajeet Myspace")
        self.assertEqual(response["agent_mode"], "existing_support")
        self.assertEqual(len(calls), 1)

    def test_ambiguous_natural_property_language_defaults_to_support(self):
        response, calls = self.run_pipeline("Do you have anything in Hyderabad?")
        self.assertEqual(response["agent_mode"], "existing_support")
        self.assertEqual(len(calls), 1)

    def test_general_question_routes_to_conversation(self):
        state = classify_conversation_route({"issue": "What is artificial intelligence?"})
        self.assertEqual(state["route"], "conversation")

    def test_general_topic_routes_to_conversation(self):
        state = classify_conversation_route({"issue": "Tell me about cricket"})
        self.assertEqual(state["route"], "conversation")
    def test_prabhas_question_gets_factual_general_answer(self):
        answer = build_deterministic_conversation_answer("Do you know Actor Prabhas?")
        self.assertIn("Indian film actor", answer)
        self.assertIn("Baahubali", answer)
        self.assertNotIn("Acrobuild technology", answer)

    def test_current_question_discloses_no_live_access(self):
        answer = build_deterministic_conversation_answer("What is the latest cricket score?")
        self.assertIn("do not have live internet access", answer)

    def test_unclear_single_word_requests_more_detail(self):
        answer = build_deterministic_conversation_answer("Explain")
        self.assertIn("add a little more detail", answer)

    def test_high_stakes_question_gets_safe_boundary(self):
        answer = build_deterministic_conversation_answer("What medicine dosage should I take?")
        self.assertIn("qualified professional", answer)

    def test_general_answer_rejects_invented_acrobuild_connection(self):
        answer = validate_general_answer(
            "Who is Prabhas?",
            "Prabhas creates software through Acrobuild technology.",
        )
        self.assertIn("do not have reliable information connecting", answer)

    def test_general_answer_rejects_question_echo(self):
        answer = validate_general_answer("What is AI?", "What is AI?")
        self.assertIn("rephrase", answer)

    def test_irrelevant_best_option_answer_is_rejected(self):
        issue = "Recommend one best 2BHK flat on 3rd floor"
        response = run_conversation_pipeline(
            issue=issue,
            conversation_messages=[],
            support_handler=lambda: {
                "agent_mode": "existing_support",
                "answer": "Here are base rates by project for several 1 BHK homes.",
            },
        )
        self.assertEqual(response["agent_mode"], "relevance_clarification")
        self.assertIn("will not substitute unrelated", response["answer"])

    def test_relevant_single_option_answer_passes(self):
        issue = "Recommend one best 2BHK flat on 3rd floor"
        response = run_conversation_pipeline(
            issue=issue,
            conversation_messages=[],
            support_handler=lambda: {
                "agent_mode": "existing_support",
                "answer": "My best recommendation is one available 2 BHK on floor 3 at INR 2,900 per sq. ft.",
            },
        )
        self.assertEqual(response["agent_mode"], "existing_support")


if __name__ == "__main__":
    unittest.main()
