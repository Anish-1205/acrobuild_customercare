"""_grounded_property_shortcut() must never let a CS API timeout/failure
propagate as a raw unhandled exception.

Confirmed bug (real stack trace, logs/chatbot.log:13518-13582): a
RuntimeError("Could not reach the CS API: timed out") raised from
build_grounded_project_location_assist inside the shortcut or-chain used
to bubble straight to event_stream(), surfacing "I hit an internal
error..." to the customer. The fix: catch it and return None so the
caller falls through to the general orchestration path, whose data-api
trace already recorded the failure -- _enforce_live_property_data() then
produces the existing "Live property data is unavailable" message.
"""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from graph.main_orchestrator import TurnContext
from routers import assist as assist_router
from services.turn_analysis_service import TurnAnalysis

_CS_API_TIMEOUT = RuntimeError("Could not reach the CS API: timed out")

_NO_LLM = patch("qwen.generate_qwen_chat_response", side_effect=RuntimeError("no llm in test"))
_NO_LIVE_COMPANY_CONTEXT = patch(
    "graph.haystack_conversation_pipeline.search_company_knowledge", return_value=[]
)


def _property_turn(issue):
    analysis = TurnAnalysis(intent="property", reply_language="English", script="latin", source="test")
    return TurnContext(
        conversation_messages=[], resolved_issue=issue, analysis=analysis, property_issue=issue,
    )


class GroundedShortcutFailureTests(unittest.TestCase):
    """Unit-level: exercise _grounded_property_shortcut() directly, with each
    shortcut in the or-chain failing in turn."""

    # Deliberately NOT an amenity question any more: reverse amenity search
    # (build_grounded_amenity_search_assist) runs first in the shortcut chain
    # and would answer "do the properties in Thane have a gym?" from live data
    # before the mocked shortcut under test was ever reached. That builder's
    # own failure path is covered by its dedicated test below.
    def _request(self, issue="Where is the project located?"):
        return assist_router.SupportAssistRequest(issue=issue)

    def test_amenity_search_shortcut_failure_returns_none(self):
        request = assist_router.SupportAssistRequest(issue="Which projects have a gym?")
        with patch("routers.assist.build_grounded_amenity_search_assist", side_effect=_CS_API_TIMEOUT):
            result = assist_router._grounded_property_shortcut(request, _property_turn(request.issue))
        self.assertIsNone(result)

    def test_site_visit_shortcut_failure_returns_none(self):
        request = self._request()
        with patch("routers.assist.build_grounded_site_visit_document_assist", side_effect=_CS_API_TIMEOUT):
            result = assist_router._grounded_property_shortcut(request, _property_turn(request.issue))
        self.assertIsNone(result)

    def test_amenities_shortcut_failure_returns_none(self):
        request = self._request()
        with patch("routers.assist.build_grounded_site_visit_document_assist", return_value=None), \
                patch("routers.assist.build_grounded_project_amenities_assist", side_effect=_CS_API_TIMEOUT):
            result = assist_router._grounded_property_shortcut(request, _property_turn(request.issue))
        self.assertIsNone(result)

    def test_location_shortcut_failure_returns_none(self):
        request = self._request()
        with patch("routers.assist.build_grounded_site_visit_document_assist", return_value=None), \
                patch("routers.assist.build_grounded_project_amenities_assist", return_value=None), \
                patch("routers.assist.build_grounded_project_location_assist", side_effect=_CS_API_TIMEOUT):
            result = assist_router._grounded_property_shortcut(request, _property_turn(request.issue))
        self.assertIsNone(result)

    def test_timeout_error_subclass_is_also_caught(self):
        request = self._request()
        with patch("routers.assist.build_grounded_site_visit_document_assist", return_value=None), \
                patch("routers.assist.build_grounded_project_amenities_assist", return_value=None), \
                patch("routers.assist.build_grounded_project_location_assist", side_effect=TimeoutError("timed out")):
            result = assist_router._grounded_property_shortcut(request, _property_turn(request.issue))
        self.assertIsNone(result)

    def test_non_cs_api_exceptions_still_propagate(self):
        """Only RuntimeError/TimeoutError (the CS API failure shapes) are
        swallowed -- a genuine bug elsewhere must not be silently hidden."""
        request = self._request()
        with patch("routers.assist.build_grounded_site_visit_document_assist", side_effect=ValueError("bug")):
            with self.assertRaises(ValueError):
                assist_router._grounded_property_shortcut(request, _property_turn(request.issue))


class GroundedShortcutFailureEndToEndTests(unittest.TestCase):
    """Full HTTP flow: a CS API timeout inside the shortcut chain must never
    reach the customer as the raw internal-error fallback string, in
    English, Hindi, or Marathi."""

    @classmethod
    def setUpClass(cls):
        import app as app_module
        cls.client = TestClient(app_module.api)

    def _assert_graceful(self, issue, conversation_id):
        with _NO_LLM, _NO_LIVE_COMPANY_CONTEXT, \
                patch("routers.assist.build_grounded_site_visit_document_assist", return_value=None), \
                patch("routers.assist.build_grounded_project_amenities_assist", return_value=None), \
                patch("routers.assist.build_grounded_project_location_assist", side_effect=_CS_API_TIMEOUT):
            response = self.client.post(
                "/api/support/assist",
                json={"issue": issue, "conversation_id": conversation_id},
            )
        self.assertEqual(response.status_code, 200)
        answer = response.json().get("answer", "")
        self.assertNotIn("internal error", answer.lower())
        return answer

    def test_english(self):
        self._assert_graceful("Do the properties in Thane have a gym?", "test-cs-api-timeout-en")

    def test_romanized_hindi(self):
        self._assert_graceful("Thane ke projects mein gym hai kya?", "test-cs-api-timeout-hi")

    def test_romanized_marathi(self):
        self._assert_graceful("Thane madhlya properties madhye gym aahe ka?", "test-cs-api-timeout-mr")


if __name__ == "__main__":
    unittest.main()
