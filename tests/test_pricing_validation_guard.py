import unittest

from graph.haystack_conversation_pipeline import validate_support_answer


class PricingValidationGuardTests(unittest.TestCase):
    def test_general_cost_question_is_not_flagged_as_a_pricing_mismatch(self):
        failures = validate_support_answer(
            "what is the average cost of living in the US",
            "Cost of living in the US varies widely by city and lifestyle.",
        )
        self.assertNotIn("pricing", failures)

    def test_general_interest_rate_question_is_not_flagged(self):
        failures = validate_support_answer(
            "what is a good interest rate on a savings account",
            "A good savings rate depends on the current market and your goals.",
        )
        self.assertNotIn("pricing", failures)

    def test_actual_property_price_question_without_inr_is_still_flagged(self):
        failures = validate_support_answer(
            "what is the price of a 2 bhk flat",
            "I do not have that information right now.",
        )
        self.assertIn("pricing", failures)

    def test_property_price_question_with_inr_answer_is_not_flagged(self):
        failures = validate_support_answer(
            "what is the price of a 2 bhk flat",
            "A 2 BHK flat is priced at INR 45 lakh.",
        )
        self.assertNotIn("pricing", failures)


if __name__ == "__main__":
    unittest.main()
