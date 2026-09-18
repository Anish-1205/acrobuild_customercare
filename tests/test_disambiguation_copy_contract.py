"""One voice for "which project did you mean?", wherever it is asked.

The project-family disambiguation used to read as a bare lookup failure --
"I found multiple matching projects for your amenities question. Did you mean:
... Please choose one of these project names." -- which asks a customer who
typed "vishwajeet" to pick from nine names they have no way to tell apart.

There were also two independent copies of it: the router grounded shortcuts
(api_context._build_ambiguous_project_response) and the clarification contract
(services/property_clarification_service.apply_clarification_contract). These
tests pin the contract and pin the fact that both sites render it through the
same builder, so the two can't drift apart again.
"""
import unittest
from unittest.mock import patch

import api_context
from services import property_clarification_service as clarification

_NAMES = ["Vishwajeet Empire", "Vishwajeet Empire NX", "Vishwajeet Prime", "Vishwajeet Heights"]
_PROJECTS = [{"id": index, "projectName": name, "address": name, "city": "Thane"}
             for index, name in enumerate(_NAMES, start=1)]


def _assert_contract(test, answer, names=_NAMES):
    # 1. every live candidate is offered, one per bullet, and nothing else is.
    listed = [line[2:].strip() for line in answer.splitlines() if line.startswith("- ")]
    test.assertEqual(listed, list(names))
    # 2. it acknowledges the customer may not know the exact project names.
    test.assertIn("exact name", answer.lower())
    # 3. it offers ways to narrow down that do NOT require knowing a name.
    lowered = answer.lower()
    # Only alternatives the bot can actually act on. Budget is deliberately
    # absent: the live API publishes per-sq-ft rate bands, not total prices.
    for alternative in ("area", "amenity"):
        test.assertIn(alternative, lowered, alternative)
    test.assertNotIn("budget", lowered)
    # 4. it still asks a clear question.
    test.assertIn("?", answer)


class ProjectChoiceCopyTests(unittest.TestCase):
    def test_copy_meets_the_contract(self):
        _assert_contract(self, clarification.build_project_choice_answer(_NAMES, "amenities"))

    def test_shared_family_name_is_taken_from_the_live_names_only(self):
        answer = clarification.build_project_choice_answer(_NAMES, "pricing")
        self.assertIn("Vishwajeet projects", answer)

    def test_unrelated_names_do_not_invent_a_family(self):
        names = ["Green Acres", "Sunrise Towers"]
        answer = clarification.build_project_choice_answer(names, "location")
        self.assertNotIn("Green Acres projects", answer)
        _assert_contract(self, answer, names)

    def test_the_lookup_subject_is_woven_in(self):
        for label, expected in (("amenities", "the amenities"), ("pricing", "the pricing"),
                                ("location", "the location"), ("documents", "the site-visit documents")):
            with self.subTest(label=label):
                self.assertIn(expected, clarification.build_project_choice_answer(_NAMES, label))

    def test_it_works_with_no_lookup_label(self):
        _assert_contract(self, clarification.build_project_choice_answer(_NAMES))


class BothDisambiguationSitesUseTheSameCopyTests(unittest.TestCase):
    """The regression guard: if either site grows its own wording again, the
    two answers stop being identical and this fails."""

    @patch.object(api_context, "get_company_projects", return_value=_PROJECTS)
    def test_router_shortcut_and_clarification_contract_agree(self, _projects):
        shortcut = api_context._build_ambiguous_project_response(_PROJECTS, "amenities")["answer"]
        with patch.object(clarification, "get_company_projects", return_value=_PROJECTS):
            contract = clarification.apply_clarification_contract(
                {"clarification_entity": "project", "route": "property",
                 "pending_project_lookup": "amenities", "answer": ""},
                "vishwajeet lo amenities",
            )["answer"]
        _assert_contract(self, shortcut)
        _assert_contract(self, contract)
        self.assertEqual(shortcut, contract)


class WithinProjectSelectionCopyTests(unittest.TestCase):
    """Wing/floor/flat/home-type selections share the voice but not the
    narrowing offers, which only make sense when choosing between projects."""

    def test_entity_choice_lists_options_and_asks_one_question(self):
        answer = clarification.build_entity_choice_answer("wing", ["A", "B"], "Vishwajeet Empire")
        self.assertIn("- A", answer)
        self.assertIn("- B", answer)
        self.assertIn("Vishwajeet Empire", answer)
        self.assertIn("Which wing", answer)
        self.assertNotIn("Which project", answer)


class LocalizationSafetyTests(unittest.TestCase):
    """The localizer rejects a translation that drops a bulleted item
    (graph/main_orchestrator._localize_answer), so the copy must keep each
    project name on its own "- " line and put no facts anywhere else."""

    def test_project_names_appear_only_as_bullets(self):
        answer = clarification.build_project_choice_answer(_NAMES, "amenities")
        prose = "\n".join(line for line in answer.splitlines() if not line.startswith("- "))
        for name in _NAMES:
            self.assertNotIn(name, prose, name)


class NarrowingOffersActuallyWorkTests(unittest.TestCase):
    """The copy promises two ways to narrow down without naming a project, so
    both have to resolve. Before this, an amenity or area reply fell through
    resume_selection() (no option matched) and the bot simply re-showed the
    same nine names -- the offer was decoration."""

    _PENDING = {"kind": "selection", "entity": "project",
                "original_issue": "what amenities does vishwajeet have",
                "options": [name for name in _NAMES], "scope": {}}

    def test_area_reply_shortlists_and_keeps_the_original_request_pending(self):
        projects = [
            {"id": 1, "projectName": "Vishwajeet Empire", "city": "Thane",
             "locality": "Ambernath", "address": "Ambernath"},
            {"id": 2, "projectName": "Vishwajeet Empire NX", "city": "Thane",
             "locality": "Badlapur", "address": "Badlapur"},
            {"id": 3, "projectName": "Vishwajeet Prime", "city": "Thane",
             "locality": "Badlapur", "address": "Badlapur"},
            {"id": 4, "projectName": "Vishwajeet Heights", "city": "Thane",
             "locality": "Ambernath", "address": "Ambernath"},
        ]
        with patch.object(clarification, "get_company_projects", return_value=projects):
            payload = clarification.narrow_project_choice_by_locality(
                self._PENDING, "the one in Ambernath",
            )
        self.assertIsNotNone(payload)
        listed = [line[2:].strip() for line in payload["answer"].splitlines() if line.startswith("- ")]
        self.assertEqual(listed, ["Vishwajeet Empire", "Vishwajeet Heights"])
        self.assertEqual(payload["source_status"], "live_api")
        # The original question stays pending, now on the shorter list.
        pending = payload["pending_project_lookup"]
        self.assertEqual(pending["original_issue"], "what amenities does vishwajeet have")
        self.assertEqual(pending["options"], ["Vishwajeet Empire", "Vishwajeet Heights"])

    def test_an_area_we_do_not_operate_in_never_matches(self):
        projects = [{"id": 1, "projectName": "Vishwajeet Empire", "city": "Thane",
                     "locality": "Ambernath", "address": "Ambernath"}]
        with patch.object(clarification, "get_company_projects", return_value=projects):
            self.assertIsNone(clarification.narrow_project_choice_by_locality(
                self._PENDING, "the one in Bengaluru",
            ))

    def test_amenity_reply_shortlists_and_keeps_the_original_request_pending(self):
        from services import amenity_search_service as amenity
        projects = [{"id": index, "projectName": name, "city": "Thane", "address": name}
                    for index, name in enumerate(_NAMES, start=1)]
        amenities = {1: [{"iconName": "Swimming Pool"}], 2: [], 3: [{"iconName": "Swimming Pool"}], 4: []}
        with patch.object(amenity, "get_company_projects", return_value=projects),                 patch.object(amenity, "get_project_amenities",
                             side_effect=lambda pid: list(amenities.get(pid, []))):
            payload = api_context.build_grounded_amenity_search_assist(
                api_context.SupportAssistRequest(issue="one with a swimming pool"),
                self._PENDING,
            )
        self.assertIsNotNone(payload)
        listed = [line[2:].strip() for line in payload["answer"].splitlines() if line.startswith("- ")]
        self.assertEqual(listed, ["Vishwajeet Empire", "Vishwajeet Prime"])
        pending = payload["pending_project_lookup"]
        self.assertEqual(pending["original_issue"], "what amenities does vishwajeet have")
        self.assertEqual(pending["options"], ["Vishwajeet Empire", "Vishwajeet Prime"])


if __name__ == "__main__":
    unittest.main()
