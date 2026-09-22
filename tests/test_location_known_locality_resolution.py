"""build_grounded_project_location_assist() must resolve the requested
location against real city/locality values from live project data, never
raw regex-captured text.

Root cause (confirmed live, logs/chatbot.log, this session): the old regex
`\\b(?:in|at|near)\\s+([a-z][a-z .'-]*?)(?:\\?|\\.|$)` only stops at a
literal "?", "." or end-of-string, so a non-deterministic English
rendering like "Is there a gym and clubhouse in the properties in Thane?"
captured "the properties in thane" as the "location", and that raw
fragment leaked untranslated into the localized answer ("Nahi, sadhya The
Properties In Thane madhe..."). Trailing-word blacklisting is fragile
against the LLM's non-deterministic phrasing (also confirmed live: the
same bug also produced "With You" for "...in Pune with you?"). Fix:
match the captured candidate text against the actual set of city/locality
values pulled from get_company_projects(), and only ever answer with one
of those real values.
"""
import unittest
from unittest.mock import patch

import api_context

_PROJECTS = [
    {"id": 53, "projectName": "Vishwajeet Heights", "city": "Thane", "locality": "Ambernath",
     "address": "Ashele, Ambernath, Thane"},
    {"id": 51, "projectName": "Vishwajeet Paradise", "city": "Thane", "locality": "Chikhloli",
     "address": "Chikhloli, Ambernath West"},
    {"id": 89, "projectName": "Vishwajeet Precious Phase-V", "city": "Pune", "locality": "",
     "address": "Kalyan-Murbad Road, near Sacred Heart School, Varap, Kalyan West, Maharashtra"},
]


def _request(issue, conversation_messages=None):
    return api_context.SupportAssistRequest(
        issue=issue, conversation_messages=conversation_messages or [],
    )


class KnownLocalityResolutionTests(unittest.TestCase):
    def test_resolve_known_location_ignores_noise_around_the_real_city(self):
        localities = api_context._known_localities(_PROJECTS)
        self.assertEqual(
            api_context._resolve_known_location("the properties in thane", localities), "Thane",
        )
        self.assertEqual(
            api_context._resolve_known_location("pune with you", localities), "Pune",
        )

    def test_unresolvable_candidate_returns_none(self):
        localities = api_context._known_localities(_PROJECTS)
        self.assertIsNone(api_context._resolve_known_location("mars colony", localities))


class LocationShortcutRegressionTests(unittest.TestCase):
    """The exact failing turns from the live session, reproduced."""

    def test_gym_and_clubhouse_in_thane_resolves_to_thane_not_garbage(self):
        request = _request("Is there a gym and clubhouse in the properties in Thane?")
        with patch.object(api_context, "get_company_projects", return_value=_PROJECTS):
            response = api_context.build_grounded_project_location_assist(request)

        self.assertIsNotNone(response)
        answer = response["answer"]
        self.assertNotIn("The Properties In Thane", answer)
        self.assertNotIn("Have A Gym And Clubhouse", answer)
        self.assertIn("Thane", answer)
        self.assertIn("Vishwajeet Heights", answer)
        self.assertIn("Vishwajeet Paradise", answer)

    def test_which_project_in_pune_with_you_resolves_to_pune_not_with_you(self):
        request = _request("Which project is there in Pune with you?")
        with patch.object(api_context, "get_company_projects", return_value=_PROJECTS):
            response = api_context.build_grounded_project_location_assist(request)

        self.assertIsNotNone(response)
        answer = response["answer"]
        self.assertNotIn("With You", answer)
        self.assertIn("Pune", answer)
        self.assertIn("Vishwajeet Precious Phase-V", answer)

    def test_unmatchable_location_lists_available_projects_instead_of_generic_city_prompt(self):
        request = _request("Do you have any projects in Wakanda?")
        with patch.object(api_context, "get_company_projects", return_value=_PROJECTS):
            response = api_context.build_grounded_project_location_assist(request)

        self.assertIsNotNone(response)
        answer = response["answer"]
        self.assertNotIn("Wakanda", answer)
        self.assertNotIn("no projects", answer.lower())
        self.assertIn("Vishwajeet Heights", answer)
        self.assertIn("Vishwajeet Paradise", answer)
        # One concise line, then every live project as a choice.
        self.assertLess(len(answer.splitlines()[0]), 120)
        self.assertEqual([choice["value"] for choice in response["quick_replies"]],
                         [project["projectName"] for project in _PROJECTS])
        self.assertEqual(response["pending_project_lookup"]["entity"], "project")


if __name__ == "__main__":
    unittest.main()
