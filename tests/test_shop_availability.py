import unittest

from services.ai_agent_service import build_company_api_direct_answer, _is_project_catalogue_question


def project_chunk(name, project_id, units):
    return {
        "source_key": f"acrobuild-cs-project-{project_id}",
        "project_name": name,
        "project": {"id": project_id, "projectName": name},
        "inventory_loaded": True,
        "available_inventory": units,
    }


class ShopAvailabilityTests(unittest.TestCase):
    def test_shop_count_is_not_misclassified_as_project_catalogue(self):
        issue = "In your total all projects how many shops are available"
        self.assertFalse(_is_project_catalogue_question(issue.lower()))

    def test_common_shop_and_availability_misspellings_still_use_count_intent(self):
        chunks = [project_chunk("Project A", 1, [
            {"id": 1, "wingId": 2, "unitNumber": 4, "typologyType": "Shop"},
        ])]
        for issue in (
            "How many shopes are avaibale in all projects?",
            "total shops avilable?",
            "count commercial units across projects",
        ):
            with self.subTest(issue=issue):
                answer = build_company_api_direct_answer(issue, chunks, [])
                self.assertIn("1 available shop unit", answer)

    def test_counts_available_shops_across_projects(self):
        chunks = [
            project_chunk("Vishwajeet Empire", 50, [
                {"id": 1, "wingId": 55, "unitNumber": 2, "typologyType": "Shop2"},
                {"id": 2, "wingId": 55, "unitNumber": 3, "typologyType": "2BHK"},
            ]),
            project_chunk("Vishwajeet Heights", 53, [
                {"id": index, "wingId": 56, "unitNumber": index, "typologyName": "Shop 315(SQ.FT)"}
                for index in range(10, 31)
            ]),
        ]
        answer = build_company_api_direct_answer(
            "In your total all projects how many shops are available", chunks, [],
        )
        self.assertIn("22 available shop units", answer)
        self.assertIn("Vishwajeet Empire: 1 available shop unit", answer)
        self.assertIn("Vishwajeet Heights: 21 available shop units", answer)
        self.assertNotIn("projects available to explore", answer)

    def test_duplicate_inventory_rows_are_not_double_counted(self):
        duplicate = {"id": 9, "wingId": 2, "unitNumber": 4, "typologyType": "Shop"}
        chunks = [project_chunk("Project A", 1, [duplicate, dict(duplicate)])]
        answer = build_company_api_direct_answer("How many shops are available?", chunks, [])
        self.assertIn("1 available shop unit", answer)

    def test_reports_when_live_inventory_is_unavailable(self):
        chunks = [{"project_name": "Project A", "inventory_loaded": False}]
        answer = build_company_api_direct_answer("How many shops are available?", chunks, [])
        self.assertIn("could not load live shop inventory", answer.lower())


if __name__ == "__main__":
    unittest.main()
