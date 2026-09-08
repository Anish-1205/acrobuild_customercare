import unittest

from services.ai_agent_service import build_company_api_direct_answer
from graph.haystack_conversation_pipeline import validate_support_node


class ContextualFlatCostTests(unittest.TestCase):
    def test_total_cost_follow_up_uses_flat_from_chat_history(self):
        history = [
            {"sender": "customer", "text": "Flat 206"},
            {
                "sender": "bot",
                "text": (
                    "Flat 206 · 2BHK 806(SQ.FT)\n"
                    "Live price: ₹2,900 – ₹3,500 (Rate Per Sq.Ft.)\n"
                    "Carpet area: 418.5 sq ft\n"
                    "Saleable area: 806 sq ft"
                ),
            },
            {"sender": "customer", "text": "Where it is located"},
            {"sender": "bot", "text": "Vishwajeet Myspace: Pale Ambernath East, Thane"},
        ]

        answer = build_company_api_direct_answer(
            "How much the total cost of this flat",
            [],
            history,
        )

        self.assertIn("For Flat 206", answer)
        self.assertIn("INR 2,337,400", answer)
        self.assertIn("INR 2,821,000", answer)
        self.assertIn("base-price estimate", answer)

    def test_natural_how_much_this_flat_cost_wording_is_supported(self):
        history = [
            {"sender": "customer", "text": "Flat 206"},
            {"sender": "bot", "text": "Flat 206\nLive price: INR 2,900 - INR 3,500\nSaleable area: 806 sq ft"},
            {"sender": "customer", "text": "How much this Flat cost?"},
        ]

        answer = build_company_api_direct_answer("How much this Flat cost?", [], history)

        self.assertIn("For Flat 206", answer)
        self.assertIn("INR 2,337,400", answer)

    def test_bare_how_much_is_this_uses_recent_selected_flat(self):
        history = [
            {"sender": "customer", "text": "Flat 1115"},
            {
                "sender": "bot",
                "text": (
                    "Flat 1115 - 2BHK 819(SQ.FT)\n"
                    "Live price: INR 3,300 - INR 4,200 (Rate Per Sq.Ft.)\n"
                    "Saleable area: 819 sq ft"
                ),
            },
            {"sender": "customer", "text": "how much is this"},
        ]

        answer = build_company_api_direct_answer("how much is this", [], history)

        self.assertIn("For Flat 1115", answer)
        self.assertIn("INR 2,702,700", answer)
        self.assertIn("INR 3,439,800", answer)

    def test_bare_reference_without_selected_flat_is_not_assumed(self):
        answer = build_company_api_direct_answer(
            "how much is this",
            [],
            [{"sender": "bot", "text": "Here are several projects."}],
        )

        self.assertNotIn("estimated base cost", answer.lower())

    def test_unrelated_cost_question_does_not_reuse_old_flat(self):
        answer = build_company_api_direct_answer(
            "What is the total cost of flats in this project?",
            [],
            [{"sender": "customer", "text": "Flat 206"}],
        )

        self.assertNotIn("For Flat 206", answer)

    def test_relevance_guard_keeps_grounded_contextual_flat_calculation(self):
        answer = (
            "For Flat 206, the estimated base cost is INR 2,337,400 to INR 2,821,000 "
            "(806 sq. ft. × INR 2,900–INR 3,500 per sq. ft.).\n\n"
            "This is a base-price estimate, not the final all-inclusive total."
        )
        state = {
            "issue": "How much this flat cost",
            "response": {"answer": answer, "confidence_label": "high"},
        }

        validated = validate_support_node(state)

        self.assertEqual(answer, validated["response"]["answer"])


if __name__ == "__main__":
    unittest.main()
