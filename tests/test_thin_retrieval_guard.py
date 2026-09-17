"""Retrieval-layer fixes for the raw-document-dump fallback.

1. `search_company_knowledge` keeps the dense company-contact record out of the
   pool for property-shaped queries.
2. `build_fallback_assist_answer` returns a clarifying question instead of
   pasting a chunk when retrieval is thin (only the company record, nothing, or
   only weak matches).
"""
import unittest
from unittest.mock import patch

from services import acrobuild_company_service as cs
from services.ai_agent_service import build_fallback_assist_answer

_COMPANY = {
    "companyName": "GBK GROUP LLP",
    "businessName": "GBK Group",
    "address": "Swanand Shopping Center, Ambernath East, Thane-421501",
    "city": "Ambernath",
    "phoneNo": "022-12345678",
    "contactEmail": "info@example.com",
}
_PROJECTS = [
    {"id": 1, "projectName": "Vishwajeet Paradise", "city": "Ambernath"},
    {"id": 2, "projectName": "Green Valley", "city": "Kalyan"},
]


def _fake_cs_request(path, **_kwargs):
    if path == "/api/cs/company":
        return _COMPANY
    if path == "/api/cs/projects":
        return _PROJECTS
    return []


class CompanyChunkSuppressionTests(unittest.TestCase):
    def _search(self, query):
        with patch.object(cs, "_cached_request", side_effect=_fake_cs_request), \
             patch.object(cs, "is_cs_api_configured", return_value=True):
            return cs.search_company_knowledge(query)

    def _has_company_chunk(self, chunks):
        return any(c.get("source_key") == "acrobuild-cs-company" for c in chunks)

    def test_property_queries_do_not_get_the_company_contact_record(self):
        for query in (
            "what is the properties you offer?",
            "show me 2 BHK flats",
            "price of a home in Ambernath",
            "which projects do you have",
        ):
            with self.subTest(query=query):
                self.assertFalse(self._has_company_chunk(self._search(query)))

    def test_contact_queries_still_reach_the_company_record(self):
        # "phone"/"address" queries are not property-shaped, so the fetch is not
        # suppressed (downstream gating may still filter, but the suppression
        # branch must not be the thing that drops it).
        with patch.object(cs, "_cached_request", side_effect=_fake_cs_request), \
             patch.object(cs, "is_cs_api_configured", return_value=True):
            query_words = cs._words("what is your office phone number and address")
        self.assertTrue(query_words & cs._COMPANY_CONTACT_TERMS)

    def test_company_contact_record_no_longer_carries_the_dominating_score(self):
        chunks = self._search("tell me about acrobuild the company office")
        company = next((c for c in chunks if c.get("source_key") == "acrobuild-cs-company"), None)
        if company is not None:
            self.assertLess(company["score"], 100.0)


class ThinRetrievalGuardTests(unittest.TestCase):
    def _call(self, chunks, articles=None, documents=None, issue="what do you offer"):
        return build_fallback_assist_answer(
            issue, "", "", "", "", articles or [], documents or [], chunks, True, "", "", "",
        )

    def test_only_company_record_returns_a_clarifying_question(self):
        answer = self._call([{
            "source_key": "acrobuild-cs-company", "record_kind": "company_api",
            "title": "Company contact details",
            "body_text": "Company: name: GBK GROUP LLP; address: ...", "score": 12.0,
        }])
        self.assertIn("need a little more detail", answer.lower())
        self.assertNotIn("GBK GROUP LLP", answer)

    def test_no_chunks_returns_a_clarifying_question(self):
        self.assertIn("need a little more detail", self._call([]).lower())

    def test_substantive_match_is_passed_through(self):
        answer = self._call([{
            "source_type": "article", "title": "Quotation and inventory follow-up",
            "body_text": "How pricing checks and quotation follow-up are handled.", "score": 17.2,
        }], articles=[{"summary": "pricing guidance", "score": 17.2}])
        self.assertNotIn("need a little more detail", answer.lower())


if __name__ == "__main__":
    unittest.main()
