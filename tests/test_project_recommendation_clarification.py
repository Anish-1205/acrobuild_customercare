import unittest

from services.ai_agent_service import (
    _is_vague_project_recommendation,
    build_company_api_direct_answer,
)


class ProjectRecommendationClarificationTests(unittest.TestCase):
    def test_vague_best_project_request_asks_for_decision_criteria(self):
        answer = build_company_api_direct_answer(
            "Can you suggest me your best project",
            [{"source_key": "acrobuild-cs-company", "body_text": "private company contact dump"}],
            [],
        )
        self.assertIn("no single best project", answer)
        self.assertIn("budget", answer)
        self.assertIn("preferred configuration", answer)
        self.assertIn("preferred location", answer)
        self.assertNotIn("private company contact dump", answer)

    def test_common_vague_recommendation_phrasings_are_detected(self):
        prompts = (
            "What is your best project?",
            "Recommend a project",
            "Suggest your best project",
            "Which project should I choose?",
        )
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertTrue(_is_vague_project_recommendation(prompt.lower()))

    def test_recommendation_with_criteria_is_not_intercepted(self):
        prompts = (
            "Suggest the best affordable project",
            "Recommend a 2 BHK project in Ambernath",
            "Which is the best ready possession project for a family?",
        )
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertFalse(_is_vague_project_recommendation(prompt.lower()))


if __name__ == "__main__":
    unittest.main()
