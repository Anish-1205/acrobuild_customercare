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
        self.assertIn("1 project available", answer)
        self.assertIn("Thane Heights", answer)
        self.assertNotIn("Mumbai Heights", answer)

    def test_plain_location_availability_question_is_answered_deterministically(self):
        """The legacy LLM-backed engine has been observed to deny availability in a
        city the live catalogue actually lists (e.g. "no property in Thane" right
        after confirming Thane is a live city), especially for non-"project" wording
        ("property"/"asset") or non-English phrasing. This bypasses it for plain
        location-availability questions so the answer is always grounded."""
        chunks = [{
            "source_key": "acrobuild-cs-projects",
            "projects": [
                {"id": 1, "projectName": "Vishwajeet Heights", "address": "Ambernath, Thane", "city": "Thane"},
                {"id": 2, "projectName": "Vishwajeet Prime", "address": "Ambernath, Thane", "city": "Thane"},
                {"id": 3, "projectName": "Vishwajeet Precious Phase-V", "address": "Varap, Kalyan West, Pune", "city": "Pune"},
            ],
        }]
        for question in (
            "In Thane, which properties do you have?",
            "Which properties do you have in Thane?",
            "Thane mein kaunsi property hai",
        ):
            with self.subTest(question=question):
                answer = build_company_api_direct_answer(question, chunks, [])
                self.assertIn("Vishwajeet Heights", answer)
                self.assertIn("Vishwajeet Prime", answer)
                self.assertNotIn("Precious Phase-V", answer)
                self.assertNotIn("no propert", answer.lower())

    def test_location_availability_with_specifics_still_reaches_the_full_engine(self):
        """A budget/BHK-qualified location question needs the richer engine, not the
        plain catalogue listing, so it must not be intercepted."""
        from services.ai_agent_service import _is_location_availability_question

        self.assertFalse(_is_location_availability_question(
            "2 bhk in thane under 90 lakh", [],
        ))

    def test_generic_availability_questions_list_projects_first(self):
        chunks = [{
            "source_key": "acrobuild-cs-projects",
            "project_names": ["Thane Heights", "Mumbai Heights"],
            "projects": [
                {"id": 1, "projectName": "Thane Heights", "city": "Thane"},
                {"id": 2, "projectName": "Mumbai Heights", "city": "Mumbai"},
            ],
        }]
        for question in (
            "aapke paas konse projects available hai ?",
            "kaunse projects hai aapke paas",
            "aapke paas kya flats available hai ?",
            "what flats are available?",
        ):
            with self.subTest(question=question):
                answer = build_company_api_direct_answer(question, chunks, [])
                self.assertIn("2 projects available to explore", answer)
                self.assertIn("Mumbai Heights", answer)

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