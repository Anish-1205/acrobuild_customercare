import unittest
from unittest.mock import patch

import api_context
from routers import assist as assist_router
from services.conversation_store_service import (
    build_pending_project_lookup_marker,
    get_pending_project_lookup,
)


PROJECTS = [
    {"id": 51, "projectName": "Vishwajeet Paradise", "address": "Ambernath"},
    {"id": 53, "projectName": "Vishwajeet Heights", "address": "Ambernath"},
]
AMENITIES = [
    {"iconName": "Swimming Pool", "type": "Amenities"},
    {"iconName": "Gymnasium", "type": "Facilities"},
]


class PendingProjectLookupTests(unittest.TestCase):
    def _pending_request(self, issue, marker):
        return api_context.SupportAssistRequest(
            issue=issue,
            conversation_messages=[
                {"sender": "customer", "text": "vishwajeet lo em em amenities vunnai?"},
                {"sender": "bot", "text": "Please choose a project." + marker},
            ],
        )

    def test_project_name_alone_resumes_amenities_lookup(self):
        marker = build_pending_project_lookup_marker("amenities")
        request = self._pending_request("paradise", marker)
        pending = assist_router._pending_project_lookup(request.conversation_messages)
        resumed, effective_issue = assist_router._resume_project_lookup_request(
            request, pending, request.issue,
        )

        self.assertEqual(effective_issue, "What amenities are available in paradise?")
        with patch.object(api_context, "get_company_projects", return_value=PROJECTS), \
                patch.object(api_context, "get_project_amenities", return_value=AMENITIES):
            response = api_context.build_grounded_project_amenities_assist(resumed)

        self.assertIn("Vishwajeet Paradise", response["answer"])
        self.assertIn("Swimming Pool", response["answer"])
        self.assertNotIn("Which project", response["answer"])

    def test_timeout_preserves_intent_and_selector_across_retries(self):
        initial = {"kind": "amenities", "selector": "", "retry_count": 0}
        marker = assist_router._project_lookup_marker(
            {"answer": "Live property data is unavailable."},
            pending=initial,
            customer_issue="paradise",
            shortcut_failed=True,
        )
        pending_retry = get_pending_project_lookup(marker)

        self.assertEqual(pending_retry, {
            "kind": "amenities", "selector": "paradise", "retry_count": 1,
        })
        request = self._pending_request("retry", marker)
        resumed, effective_issue = assist_router._resume_project_lookup_request(
            request, pending_retry, request.issue,
        )
        self.assertEqual(effective_issue, "What amenities are available in paradise?")

        expired = assist_router._project_lookup_marker(
            {"answer": "Still unavailable."},
            pending=pending_retry,
            customer_issue="retry",
            shortcut_failed=True,
        )
        self.assertEqual(get_pending_project_lookup(expired), {
            "kind": "amenities", "selector": "paradise", "retry_count": 2,
        })


if __name__ == "__main__":
    unittest.main()
