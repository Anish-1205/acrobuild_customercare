import unittest
from unittest.mock import patch

from services.acrobuild_company_service import resolve_project_from_text, search_company_knowledge
from services.ai_agent_service import _find_requested_project


PROJECTS = [
    {"id": 51, "projectName": "Vishwajeet Paradise"},
    {"id": 50, "projectName": "Vishwajeet Empire"},
    {"id": 57, "projectName": "Vishwajeet Prime"},
    {"id": 55, "projectName": "GBK Group"},
    {"id": 56, "projectName": "Vishwajeet Empire NX"},
    {"id": 54, "projectName": "Vishwajeet Myspace"},
    {"id": 53, "projectName": "Vishwajeet Heights"},
    {"id": 52, "projectName": "Vishwajeet Precious"},
    {"id": 58, "projectName": "Vishwajeet Town"},
]

TEMPLATES = [
    "Tell me more about {name}", "Give me an overview of {name}", "Where is {name}?",
    "Show the location of {name}", "What wings does {name} have?", "Floors in {name}",
    "Which homes are in {name}?", "Show 1 BHK in {name}", "Show 2 BHK in {name}",
    "Availability at {name}", "Any units available in {name}?", "Pricing for {name}",
    "What is the rate at {name}?", "Book a site visit for {name}", "Amenities at {name}",
    "RERA number for {name}", "Project details: {name}", "I choose {name}",
    "Select {name}", "Let's explore {name}", "Deep dive into {name}", "About the {name} project",
    "Could you explain {name}?", "I need information on {name}", "Is {name} published?",
    "Construction status of {name}", "Possession date for {name}", "Configurations in {name}",
    "Typologies in {name}", "What can I buy in {name}?", "Are shops listed in {name}?",
    "Compare units inside {name}", "Lowest price in {name}", "Highest price in {name}",
    "Best available home in {name}", "Do you know {name}?", "Please open {name}",
    "Continue with {name}", "Take me to {name}", "Information about {name}, please",
    "Can we discuss {name}?", "I meant {name}", "The project is {name}",
    "My selected property is {name}", "Tell me everything verified about {name}",
    "Show API details for {name}", "What is special about {name}?", "Does {name} have inventory?",
    "How many wings in {name}?", "How many floors in {name}?", "Homes and prices at {name}",
    "Location and availability for {name}", "Overview and RERA for {name}",
    "I want a site visit at {name}", "Can you help with {name}?", "{name}",
]


class ProjectEntityResolution500Tests(unittest.TestCase):
    def test_empire_nx_never_collapses_to_empire(self):
        variants = [
            "Vishwajeet Empire NX", "Empire NX", "empire nx", "Tell me about Empire NX",
            "I select NX", "NX project details", "pricing in the Vishwajeet Empire NX project",
        ]
        for prompt in variants:
            with self.subTest(prompt=prompt):
                resolved = resolve_project_from_text(PROJECTS, prompt)
                self.assertEqual(resolved["id"], 56)

    def test_base_empire_still_resolves_to_base_empire(self):
        resolved = resolve_project_from_text(PROJECTS, "Tell me about Vishwajeet Empire")
        self.assertEqual(resolved["id"], 50)

    def test_answer_builder_selects_nx_chunk(self):
        chunks = [
            {"source_key": f"acrobuild-cs-project-{project['id']}", "project_name": project["projectName"]}
            for project in PROJECTS
        ]
        selected = _find_requested_project("tell me more about vishwajeet empire nx", chunks)
        self.assertEqual(selected["project_name"], "Vishwajeet Empire NX")

    @patch("services.acrobuild_company_service._cached_request")
    def test_retrieval_fetches_only_nx_details(self, cached_request):
        def response(path, **kwargs):
            if path == "/api/cs/company":
                return {}
            if path == "/api/cs/projects":
                return PROJECTS
            if path == "/api/cs/projects/56/wings" or path == "/api/cs/projects/56/typologies":
                return []
            self.fail(f"Unexpected project detail request: {path}")
        cached_request.side_effect = response
        with patch("services.acrobuild_company_service.is_cs_api_configured", return_value=True):
            chunks = search_company_knowledge("Tell me more about Vishwajeet Empire NX")
        detail_names = [chunk.get("project_name") for chunk in chunks if chunk.get("project_name")]
        self.assertEqual(detail_names, ["Vishwajeet Empire NX"])


def _make_resolution_test(project, template):
    def test(self):
        prompt = template.format(name=project["projectName"])
        resolved = resolve_project_from_text(PROJECTS, prompt)
        self.assertIsNotNone(resolved, prompt)
        self.assertEqual(resolved["id"], project["id"], prompt)
    return test


for project_index, project in enumerate(PROJECTS, start=1):
    for template_index, template in enumerate(TEMPLATES, start=1):
        test_name = f"test_prompt_{project_index:02d}_{template_index:02d}"
        setattr(ProjectEntityResolution500Tests, test_name, _make_resolution_test(project, template))


if __name__ == "__main__":
    unittest.main()
