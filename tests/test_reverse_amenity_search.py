"""Reverse amenity search: "which projects have a gym".

The bot could already answer "what amenities does project X have"; it could
not answer the reverse. services/amenity_search_service.py + the
build_grounded_amenity_search_assist router shortcut add it.

The grounding rule these tests exist to protect: the ONLY amenity names the
feature will ever talk about are iconName values the live
/api/cs/projects/{id}/amenities endpoint returned. A customer word that does
not resolve to a live value must produce no match at all -- the turn falls
through to the normal path -- never a guessed one.
"""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import api_context
from routers import assist as assist_router
from services import amenity_search_service as amenity

# A stand-in catalogue with the shape of the live one. Fixed here so the
# assertions stay meaningful when the real catalogue changes; the live data is
# exercised separately by the HTTP tests below.
_PROJECTS = [
    {"id": 1, "projectName": "Vishwajeet Precious", "city": "Thane", "locality": "Varap", "address": "Varap"},
    {"id": 2, "projectName": "Vishwajeet Prime", "city": "Thane", "locality": "", "address": "Thane"},
    {"id": 3, "projectName": "Vishwajeet Town", "city": "Pune", "locality": "Baner", "address": "Baner"},
]
_AMENITIES = {
    1: [{"iconName": "Gym", "type": "Amenities"},
        {"iconName": "Swimming Pool", "type": "Amenities"},
        {"iconName": "Jogging Track", "type": "Amenities"},
        {"iconName": "Baby Swimming Area", "type": "Amenities"}],
    2: [{"iconName": "Swimming Pool", "type": "Amenities"},
        {"iconName": "Badminton", "type": "Amenities"}],
    3: [{"iconName": "Gym", "type": "Amenities"},
        {"iconName": "Children's Playing Area", "type": "Amenities"}],
}


def _fake_catalogue():
    return (
        patch.object(amenity, "get_company_projects", return_value=list(_PROJECTS)),
        patch.object(amenity, "get_project_amenities", side_effect=lambda pid: list(_AMENITIES.get(pid, []))),
    )


class _FakeCatalogueTest(unittest.TestCase):
    def setUp(self):
        self._patches = _fake_catalogue()
        for item in self._patches:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in self._patches])
        self.index = amenity.live_amenity_index()
        self.names = amenity.live_amenity_names(self.index)


class AmenityTermMatchingTests(_FakeCatalogueTest):
    def test_direct_name_and_common_synonyms_resolve_to_live_names(self):
        for text, expected in (
            ("which projects have a gym", ["Gym"]),
            ("where can I find a swimming pool", ["Swimming Pool"]),
            ("any project with a fitness centre", ["Gym"]),
            ("which projects have a jogging track", ["Jogging Track"]),
            ("which projects have a kids play area", ["Children's Playing Area"]),
        ):
            with self.subTest(text=text):
                self.assertEqual(amenity.match_amenity_terms(text, self.names), expected)

    def test_an_amenity_nobody_lists_never_matches(self):
        """The anti-hallucination case: no live project has a helipad, so the
        feature must not claim one, and must not match something adjacent."""
        for text in ("which projects have a helipad",
                     "which projects have a bowling alley",
                     "which projects have a rooftop bar"):
            with self.subTest(text=text):
                self.assertEqual(amenity.match_amenity_terms(text, self.names), [])
                self.assertFalse(amenity.is_amenity_lookup_query(text, self.names))

    def test_a_more_specific_live_name_wins_over_a_looser_one(self):
        # "swimming pool" must not also drag in "Baby Swimming Area".
        self.assertEqual(
            amenity.match_amenity_terms("projects with a swimming pool", self.names),
            ["Swimming Pool"],
        )

    def test_forward_amenity_question_is_not_treated_as_a_reverse_search(self):
        self.assertFalse(amenity.is_reverse_amenity_query("what amenities does Vishwajeet Prime have"))

    def test_non_amenity_chat_is_never_an_amenity_lookup(self):
        for text in ("hello", "which projects are in Pune", "what is my ticket status"):
            with self.subTest(text=text):
                self.assertFalse(amenity.is_amenity_lookup_query(text, self.names))


class AmenityToProjectsTests(_FakeCatalogueTest):
    def test_single_amenity_returns_only_projects_that_actually_list_it(self):
        matches, _ = amenity.projects_with_amenities(self.index, ["Gym"])
        self.assertEqual({p["projectName"] for p in matches},
                         {"Vishwajeet Precious", "Vishwajeet Town"})

    def test_multiple_amenities_require_all_of_them(self):
        matches, per_term = amenity.projects_with_amenities(self.index, ["Gym", "Badminton"])
        self.assertEqual(matches, [])
        self.assertEqual({p["projectName"] for p in per_term["Badminton"]}, {"Vishwajeet Prime"})

    def test_locality_scoping_does_not_answer_from_the_whole_catalogue(self):
        scoped, locality = amenity.scope_index_to_locality(self.index, "which projects in Pune have a gym")
        self.assertEqual(locality, "Pune")
        matches, _ = amenity.projects_with_amenities(scoped, ["Gym"])
        self.assertEqual([p["projectName"] for p in matches], ["Vishwajeet Town"])


class AmenitySearchAssistTests(_FakeCatalogueTest):
    def _answer(self, issue):
        payload = api_context.build_grounded_amenity_search_assist(
            assist_router.SupportAssistRequest(issue=issue),
        )
        return payload, (payload or {}).get("answer", "")

    def test_reverse_search_lists_the_matching_project_names(self):
        payload, answer = self._answer("which projects have a gym?")
        self.assertIsNotNone(payload)
        self.assertEqual(payload["source_status"], "live_api")
        self.assertIn("- Vishwajeet Precious", answer)
        self.assertIn("- Vishwajeet Town", answer)
        self.assertNotIn("Vishwajeet Prime", answer)

    def test_where_phrasing_is_handled_too(self):
        _, answer = self._answer("where can I find a swimming pool")
        self.assertIn("- Vishwajeet Precious", answer)
        self.assertIn("- Vishwajeet Prime", answer)

    def test_unknown_amenity_falls_through_instead_of_guessing(self):
        payload, _ = self._answer("which projects have a helipad?")
        self.assertIsNone(payload)

    def test_no_project_has_all_requested_amenities_is_stated_honestly(self):
        _, answer = self._answer("which projects have a gym and badminton")
        self.assertIn("No project", answer)
        self.assertIn("Badminton: Vishwajeet Prime", answer)

    def test_single_project_yes_no_form_answers_from_live_records(self):
        _, yes = self._answer("does Vishwajeet Precious have a gym?")
        self.assertTrue(yes.startswith("Yes"), yes)
        _, no = self._answer("does Vishwajeet Prime have a gym?")
        self.assertNotIn("Yes —", no)
        self.assertIn("does not list", no)
        # ...and it points at the projects that DO list it, from live data.
        self.assertIn("- Vishwajeet Precious", no)

    def test_every_project_named_in_an_answer_exists_in_the_catalogue(self):
        """Blanket anti-hallucination check over a spread of phrasings."""
        real = {p["projectName"] for p in _PROJECTS}
        for issue in ("which projects have a gym", "where can I find a swimming pool",
                      "any project with badminton", "show me projects with a jogging track"):
            with self.subTest(issue=issue):
                _, answer = self._answer(issue)
                listed = [line[2:].strip() for line in answer.splitlines() if line.startswith("- ")]
                self.assertTrue(listed, answer)
                for name in listed:
                    self.assertIn(name, real, name)


class AmenitySearchOverHttpTests(unittest.TestCase):
    """Through the real router against the real CS API, in all four supported
    languages. Asserts grounding (every project named is a live project)
    rather than exact wording, which is localized."""

    @classmethod
    def setUpClass(cls):
        import app as app_module
        cls.client = TestClient(app_module.api)
        from services.acrobuild_company_service import customer_facing_projects, get_company_projects
        cls.live_names = {
            str(p["projectName"]).strip() for p in customer_facing_projects(get_company_projects())
        }

    def test_reverse_amenity_search_is_grounded_in_every_language(self):
        questions = {
            "english": "which projects have a gym?",
            "hindi": "kaunse project mein gym hai?",
            "marathi": "konatya project madhe gym aahe?",
            "telugu": "ye projects lo gym undi?",
        }
        for language, issue in questions.items():
            with self.subTest(language=language):
                payload = self.client.post("/api/support/assist", json={
                    "issue": issue, "conversation_id": f"amenity-search-{language}",
                }).json()
                listed = [line[2:].strip() for line in
                          str(payload.get("answer", "")).splitlines() if line.startswith("- ")]
                for name in listed:
                    self.assertIn(name, self.live_names, f"{language}: {name}")


if __name__ == "__main__":
    unittest.main()
