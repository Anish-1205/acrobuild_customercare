import unittest

from services.ai_agent_service import (
    _is_portfolio_overview_question,
    _is_project_catalogue_question,
    build_company_api_direct_answer,
)


class PortfolioOverviewTests(unittest.TestCase):
    def setUp(self):
        self.chunks = [
            {
                "source_key": "acrobuild-cs-project-1",
                "project_name": "Project Alpha",
                "project": {"projectName": "Project Alpha", "location": "Alpha Road", "reraNo": "RERA-1"},
                "wings": [{"name": "A", "totalFloors": 12}],
                "typologies": [{"typologyType": "1BHK"}, {"typologyType": "2BHK"}],
            },
            {
                "source_key": "acrobuild-cs-project-2",
                "project_name": "Project Beta",
                "project": {"projectName": "Project Beta", "location": "Beta Road", "reraNo": "RERA-2"},
                "wings": [{"name": "B", "totalFloors": 8}],
                "typologies": [{"typologyType": "Shop"}, {"typologyType": "12BHK+T029"}],
            },
        ]

    def test_explain_all_projects_is_portfolio_overview_not_catalogue(self):
        issue = "Can you explain an overview of all of your projects"
        self.assertTrue(_is_portfolio_overview_question(issue.lower()))

    def test_portfolio_overview_explains_each_project(self):
        answer = build_company_api_direct_answer(
            "Can you explain an overview of all of your projects", self.chunks, [],
        )
        self.assertIn("verified overview of all 2", answer)
        self.assertIn("Project Alpha", answer)
        self.assertIn("Location: Alpha Road", answer)
        self.assertIn("RERA: RERA-1", answer)
        self.assertIn("Configurations: 1BHK, 2BHK", answer)
        self.assertIn("Project Beta", answer)
        self.assertNotIn("12BHK+T029", answer)
        self.assertNotIn("Tell me which project you want to explore", answer)

    def test_email_like_location_is_not_presented_as_project_location(self):
        self.chunks[1]["project"]["location"] = "sales@example.com, Thane"
        self.chunks[1]["project"]["address"] = "sales@example.com"
        self.chunks[1]["project"]["city"] = "Thane"
        answer = build_company_api_direct_answer("Overview of all projects", self.chunks, [])
        self.assertNotIn("sales@example.com", answer)
        self.assertIn("Location: Thane", answer)

    def test_plain_list_request_remains_a_catalogue_request(self):
        self.assertTrue(_is_project_catalogue_question("list all your projects"))

    def test_informal_fetch_request_is_a_catalogue_request(self):
        self.assertTrue(_is_project_catalogue_question("fetch me the projects u have"))
        self.assertFalse(_is_portfolio_overview_question("list all your projects"))


if __name__ == "__main__":
    unittest.main()
