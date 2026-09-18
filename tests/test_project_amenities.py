"""build_grounded_project_amenities_assist() must read real amenity data from
GET /api/cs/projects/{id}/amenities, not the always-empty unitAmenities field
on typologies (confirmed empty for every typology of every one of the 10 live
projects in the catalogue by direct API inspection).
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import api_context

_PROJECTS = [{"id": 53, "projectName": "Vishwajeet Heights", "city": "Thane"}]

_REAL_AMENITIES = [
    {"id": 11, "iconName": "Cricket Pitch", "type": "Amenities", "url": "https://example/cricket_pitch.svg"},
    {"id": 36, "iconName": "Lift", "type": "Facilities", "url": "https://example/lift.svg"},
    {"id": 51, "iconName": "CCTV Coverage", "type": "Facilities", "url": "https://example/cctv.svg"},
]


def _fake_request(issue):
    return SimpleNamespace(issue=issue, conversation_messages=[])


class ProjectAmenitiesAnswerTests(unittest.TestCase):
    def test_real_amenities_are_listed_not_the_no_data_fallback(self):
        with patch.object(api_context, "get_company_projects", return_value=_PROJECTS), \
                patch.object(api_context, "get_project_amenities", return_value=_REAL_AMENITIES) as get_amenities_mock:
            response = api_context.build_grounded_project_amenities_assist(
                _fake_request("What amenities does Vishwajeet Heights have?")
            )

        self.assertIsNotNone(response)
        get_amenities_mock.assert_called_once_with(53)
        answer = response["answer"]
        self.assertIn("Cricket Pitch", answer)
        self.assertIn("Lift", answer)
        self.assertIn("CCTV Coverage", answer)
        self.assertNotIn("does not currently list amenities", answer)

    def test_amenities_and_facilities_are_merged_into_one_flat_list(self):
        with patch.object(api_context, "get_company_projects", return_value=_PROJECTS), \
                patch.object(api_context, "get_project_amenities", return_value=_REAL_AMENITIES):
            response = api_context.build_grounded_project_amenities_assist(
                _fake_request("What amenities does Vishwajeet Heights have?")
            )
        answer = response["answer"]
        # One flat bullet list under one heading, no separate "Facilities:" section.
        self.assertNotIn("Facilities:", answer)
        self.assertEqual(answer.count("\n- "), len(_REAL_AMENITIES))

    def test_zero_selected_amenities_still_says_no_data_honestly(self):
        with patch.object(api_context, "get_company_projects", return_value=_PROJECTS), \
                patch.object(api_context, "get_project_amenities", return_value=[]):
            response = api_context.build_grounded_project_amenities_assist(
                _fake_request("What amenities does Vishwajeet Heights have?")
            )
        self.assertIn("does not currently list amenities", response["answer"])
        self.assertNotIn("Cricket Pitch", response["answer"])


if __name__ == "__main__":
    unittest.main()
