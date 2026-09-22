"""Customer-facing project lists must exclude fake/test records like the
known "GBK Group" one (address="palvinder@gbkgroup.in" -- the company's
own contact email, not a street address).

isPublished is NOT used as the signal: confirmed live against the real CS
API that it is False for every project, including every legitimate one --
filtering on it would empty every project list. The signal used instead:
reject any record whose address field contains "@".
"""
import unittest
from unittest.mock import patch

import api_context
from services import acrobuild_company_service
from services import amenity_search_service
from services.ai_agent_service import build_company_api_direct_answer

_PROJECTS_WITH_FAKE_RECORD = [
    {"id": 53, "projectName": "Vishwajeet Heights", "city": "Thane", "address": "Ashele, Ambernath, Thane"},
    {"id": 55, "projectName": "GBK Group", "city": "Thane", "address": "palvinder@gbkgroup.in"},
    {"id": 50, "projectName": "Vishwajeet Empire", "city": "Thane", "address": "Pale Village, Ambernath East"},
]


class FakeProjectRecordFilterTests(unittest.TestCase):
    def test_helper_excludes_email_address_record_and_keeps_real_ones(self):
        filtered = api_context._customer_facing_projects(_PROJECTS_WITH_FAKE_RECORD)
        names = [project["projectName"] for project in filtered]
        self.assertNotIn("GBK Group", names)
        self.assertIn("Vishwajeet Heights", names)
        self.assertIn("Vishwajeet Empire", names)
        self.assertEqual(len(filtered), 2)

    def test_location_shortcut_excludes_fake_record_from_thane_list(self):
        request = api_context.SupportAssistRequest(issue="properties in Thane")
        with patch.object(api_context, "get_company_projects", return_value=_PROJECTS_WITH_FAKE_RECORD):
            response = api_context.build_grounded_project_location_assist(request)

        self.assertIsNotNone(response)
        answer = response["answer"]
        self.assertNotIn("GBK Group", answer)
        self.assertIn("Vishwajeet Heights", answer)
        self.assertIn("Vishwajeet Empire", answer)
        self.assertIn("2 projects", answer)

    def test_amenities_project_selection_list_excludes_fake_record(self):
        request = api_context.SupportAssistRequest(issue="What amenities are available?")
        # The ambiguous-project path builds its amenity index via
        # services/amenity_search_service.py's own get_project_amenities
        # import, a separate binding from api_context's -- leaving that call
        # live made this test flaky/network-dependent even though it is only
        # asserting the fake-record filter, not real amenity data.
        with patch.object(api_context, "get_company_projects", return_value=_PROJECTS_WITH_FAKE_RECORD), \
                patch.object(amenity_search_service, "get_company_projects", return_value=_PROJECTS_WITH_FAKE_RECORD), \
                patch.object(amenity_search_service, "get_project_amenities", return_value=[{"iconName": "Gym"}]):
            response = api_context.build_grounded_project_amenities_assist(request)

        self.assertIsNotNone(response)
        # build_amenity_project_choices() offers the shortlist as quick
        # replies / the pending selection's options, not a "projects" key on
        # matched_chunks (that shape belongs to the ambiguous-name path).
        names = [choice["value"] for choice in response["quick_replies"]]
        self.assertNotIn("GBK Group", names)
        self.assertIn("Vishwajeet Heights", names)

    def test_generic_numbered_project_list_excludes_fake_record(self):
        real_projects = [
            {"id": index, "projectName": f"Project {index}", "address": f"Street {index}"}
            for index in range(1, 10)
        ]
        api_projects = [*real_projects, _PROJECTS_WITH_FAKE_RECORD[1]]
        # search_company_knowledge() gates on is_cs_api_configured() before
        # ever reaching the (mocked) request layer below -- these three
        # module constants must look configured regardless of the real
        # environment's credentials.
        with patch.object(acrobuild_company_service, "CS_API_BASE_URL", "https://example.invalid"), \
                patch.object(acrobuild_company_service, "CS_API_KEY", "test-key"), \
                patch.object(acrobuild_company_service, "CS_API_COMPANY_ID", "1"), \
                patch.object(acrobuild_company_service, "_cached_request", return_value=api_projects):
            chunks = acrobuild_company_service.search_company_knowledge("what projects do you have")

        answer = build_company_api_direct_answer("what projects do you have", chunks)
        self.assertIn("9 projects", answer)
        self.assertNotIn("GBK Group", answer)
        self.assertEqual(answer.count("\n") - 3, 9)


if __name__ == "__main__":
    unittest.main()
