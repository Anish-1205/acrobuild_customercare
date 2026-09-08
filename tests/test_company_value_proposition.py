import unittest

from services.ai_agent_service import build_company_value_proposition_answer


class CompanyValuePropositionTests(unittest.TestCase):
    def test_answers_why_buy_from_your_company_as_acrobuild(self):
        answer = build_company_value_proposition_answer(
            "Why should I buy a flat in your company?"
        )

        self.assertIn("Acrobuild home", answer)
        self.assertIn("verified projects", answer)
        self.assertNotIn("GBK", answer)

    def test_does_not_intercept_specific_inventory_question(self):
        answer = build_company_value_proposition_answer(
            "Which 2 BHK flats are available?"
        )

        self.assertEqual(answer, "")


if __name__ == "__main__":
    unittest.main()
