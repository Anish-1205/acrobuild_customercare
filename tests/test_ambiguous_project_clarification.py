import unittest
from unittest.mock import patch

import api_context
from services.acrobuild_company_service import (
    resolve_project_candidates_from_text,
    resolve_project_from_text,
)


PROJECTS = [
    {"id": 51, "projectName": "Vishwajeet Paradise", "city": "Thane"},
    {"id": 50, "projectName": "Vishwajeet Empire", "city": "Thane"},
    {"id": 57, "projectName": "Vishwajeet Prime", "city": "Thane"},
    {"id": 56, "projectName": "Vishwajeet Empire NX", "city": "Thane"},
    {"id": 54, "projectName": "Vishwajeet Myspace", "city": "Thane"},
    {"id": 53, "projectName": "Vishwajeet Heights", "city": "Thane"},
    {"id": 52, "projectName": "Vishwajeet Precious", "city": "Thane"},
]


def _request(issue):
    return api_context.SupportAssistRequest(issue=issue, conversation_messages=[])


class AmbiguousProjectMatcherTests(unittest.TestCase):
    def test_bare_brand_returns_real_candidates_instead_of_one_project(self):
        candidates = resolve_project_candidates_from_text(
            PROJECTS, "vishvajeet lo amenities em unnai?",
        )

        self.assertGreater(len(candidates), 1)
        self.assertIn("Vishwajeet Heights", [item["projectName"] for item in candidates])
        self.assertIn("Vishwajeet Prime", [item["projectName"] for item in candidates])
        self.assertIsNone(
            resolve_project_from_text(PROJECTS, "vishvajeet lo amenities em unnai?"),
        )


class AmbiguousProjectClarificationTests(unittest.TestCase):
    def _assert_lists_real_candidates(self, response):
        self.assertIsNotNone(response)
        answer = response["answer"]
        # Structural, not word-for-word: the disambiguation copy is tuned for
        # tone (see services/property_clarification_service.py
        # build_project_choice_answer), so these assert what the message must
        # always DO, not the exact sentences it currently uses.
        self.assertIn("Vishwajeet Heights", answer)
        self.assertIn("Vishwajeet Empire NX", answer)
        self.assertIn("Vishwajeet Prime", answer)
        self.assertNotIn("Share the project name", answer)
        self.assertGreaterEqual(answer.count("\n- Vishwajeet"), 3)
        # It must acknowledge the customer may not know the exact name and
        # offer at least one way to narrow down other than picking a name.
        self.assertIn("exact name", answer)
        for alternative in ("area", "amenity"):
            self.assertIn(alternative, answer.lower(), alternative)

    @patch.object(api_context, "get_company_projects", return_value=PROJECTS)
    def test_ambiguous_amenities_question_lists_candidates(self, _get_projects):
        response = api_context.build_grounded_project_amenities_assist(
            _request("vishvajeet lo amenities em unnai?"),
        )
        self._assert_lists_real_candidates(response)

    @patch.object(api_context, "get_company_projects", return_value=PROJECTS)
    def test_ambiguous_cost_question_lists_candidates(self, _get_projects):
        response = api_context.build_grounded_project_cost_clarification_assist(
            _request("What is the cost in vishvajeet?"),
        )
        self._assert_lists_real_candidates(response)

    @patch.object(api_context, "get_company_projects", return_value=PROJECTS)
    def test_ambiguous_location_question_lists_candidates(self, _get_projects):
        response = api_context.build_grounded_project_location_assist(
            _request("Where is vishvajeet located?"),
        )
        self._assert_lists_real_candidates(response)


if __name__ == "__main__":
    unittest.main()
