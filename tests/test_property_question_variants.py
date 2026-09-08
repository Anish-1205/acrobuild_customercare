import unittest

from services.ai_agent_service import (
    build_company_api_direct_answer,
    is_cross_project_floor_comparison_request,
    is_model_answer_echo,
    mentions_wing_reference,
)


class PropertyQuestionVariantTests(unittest.TestCase):
    def test_natural_floor_comparison_variants_are_recognized(self):
        variants = (
            "Tell me about the project you have more number of floors",
            "Which project has the highest number of floors?",
            "Show the project with most floors",
            "Which property has fewer floors?",
        )
        for question in variants:
            with self.subTest(question=question):
                self.assertTrue(is_cross_project_floor_comparison_request(question))

    def test_single_letter_wing_does_not_match_normal_sentence_letters(self):
        self.assertFalse(mentions_wing_reference("Tell me more about this project", "A"))
        self.assertFalse(mentions_wing_reference("Which project has the costly flat", "B"))

    def test_single_letter_wing_requires_an_explicit_reference(self):
        self.assertTrue(mentions_wing_reference("A wing", "A"))
        self.assertTrue(mentions_wing_reference("wing B", "B"))
        self.assertTrue(mentions_wing_reference("let us go with A", "A"))
    def test_explicit_project_location_ignores_conversational_words(self):
        chunks = [
            {
                "source_key": "acrobuild-cs-projects",
                "projects": [{
                    "id": 99,
                    "projectName": "Vishwajeet Empire",
                    "address": "Behind Anand Sagar Resort, Pale Village",
                    "city": "Thane",
                    "reraNo": "P51700034509",
                }],
            },
            {
                "source_key": "acrobuild-cs-project-99",
                "project_name": "Vishwajeet Empire",
                "project": {"id": 99, "projectName": "Vishwajeet Empire"},
                "wings": [],
                "typologies": [],
                "available_inventory": [],
            },
        ]
        answer = build_company_api_direct_answer(
            "Can you say the location of project Vishwajeet Empire",
            chunks,
            [],
        )
        self.assertIn("Behind Anand Sagar Resort", answer)
        self.assertIn("P51700034509", answer)
        self.assertNotIn("None of their", answer)
    def test_known_city_filters_projects_when_question_omits_in(self):
        chunks = [{
            "source_key": "acrobuild-cs-projects",
            "projects": [
                {
                    "id": 1,
                    "projectName": "Thane Heights",
                    "address": "Ghodbunder Road, Thane",
                    "city": "Thane",
                },
                {
                    "id": 2,
                    "projectName": "Mumbai Heights",
                    "address": "Andheri East, Mumbai",
                    "city": "Mumbai",
                },
            ],
        }]
        answer = build_company_api_direct_answer(
            "Do you which projects are there Thane",
            chunks,
            [],
        )
        self.assertIn("1 match for Thane", answer)
        self.assertIn("Thane Heights", answer)
        self.assertNotIn("Mumbai Heights", answer)

    def test_project_scope_wins_when_project_and_wing_names_are_identical(self):
        chunks = [{
            "source_key": "acrobuild-cs-project-99",
            "project_name": "Vishwajeet Empire",
            "project": {"id": 99, "projectName": "Vishwajeet Empire", "reraNo": "TEST-RERA"},
            "wings": [{"id": 9, "name": "Vishwajeet Empire", "totalFloors": 14}],
            "typologies": [{"typologyType": "2BHK"}],
            "available_inventory": [],
            "inventory_loaded": False,
        }]
        answer = build_company_api_direct_answer(
            "Tell me more about project Vishwajeet Empire",
            chunks,
            [],
        )
        self.assertIn("verified overview of Vishwajeet Empire", answer)
        self.assertIn("RERA number", answer)
        self.assertNotIn("Choose a floor", answer)
        self.assertNotIn("Got it - Vishwajeet Empire wing", answer)
    def test_wrapped_customer_message_is_detected_as_an_echo(self):
        question = "Tell me about the project you have more number of floors"
        answer = f'The latest customer message is: "{question}."'
        self.assertTrue(is_model_answer_echo(question, answer))

    def test_substantive_floor_answer_is_not_treated_as_echo(self):
        question = "Which project has the most floors?"
        answer = "Vishwajeet Myspace has the most floors: 15."
        self.assertFalse(is_model_answer_echo(question, answer))


if __name__ == "__main__":
    unittest.main()