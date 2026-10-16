"""Regression tests for unsupported-capability intent detection.

Covers: offers, nearby places, documents, customer finance,
investment guarantees — plus negative cases ensuring supported
property queries are NOT intercepted.
"""

import pytest

from api_context import SupportAssistRequest, build_unsupported_capability_assist


def _detect(issue: str) -> dict | None:
    return build_unsupported_capability_assist(SupportAssistRequest(issue=issue))


def _family(issue: str) -> str | None:
    result = _detect(issue)
    return result.get("unsupported_capability") if result else None


# ── Offers / discounts ──────────────────────────────────────────────


class TestOffers:
    @pytest.mark.parametrize("prompt", [
        "What offers are available right now for Vishwajeet Prime?",
        "I heard there is a 5 lakh discount on Vishwajeet Prime. Is that active?",
        "Any discounts right now?",
        "Are there any current promotions?",
        "Is there a festive offer on this project?",
        "Any special pricing available?",
        "Tell me about the latest scheme for Vishwajeet Prime",
    ])
    def test_detects_offer_queries(self, prompt):
        assert _family(prompt) == "offers"

    def test_response_shape(self):
        result = _detect("Any offers on Vishwajeet Prime?")
        assert result is not None
        assert result["source_status"] == "unavailable"
        assert result["retrieval_mode"] == "unsupported_capability"
        assert result["used_llm"] is False
        assert result["confidence_label"] == "high"
        assert "sales team" in result["answer"].lower() or "sales office" in result["answer"].lower()


# ── Nearby places / distances ───────────────────────────────────────


class TestNearbyPlaces:
    @pytest.mark.parametrize("prompt", [
        "Which hospitals are within 3 km of Vishwajeet Prime?",
        "How far is the airport?",
        "Are there any schools nearby?",
        "What is the distance to the railway station?",
        "Is there a metro station close to this project?",
        "How far is the nearest mall from Vishwajeet Prime?",
        "Travel time to the nearest school?",
    ])
    def test_detects_nearby_queries(self, prompt):
        assert _family(prompt) == "nearby_places"

    @pytest.mark.parametrize("prompt", [
        "Where is Vishwajeet Prime located?",
        "What is the address of this project?",
        "Tell me the location of Vishwajeet Prime",
    ])
    def test_location_queries_pass_through(self, prompt):
        assert _detect(prompt) is None


# ── Documents (brochure / floor plan) ──────────────────────────────


class TestDocuments:
    @pytest.mark.parametrize("prompt", [
        "Send me the brochure and floor plan for Vishwajeet Prime.",
        "Can I download the project brochure?",
        "Show me the floor plan",
        "I need the master plan for this project",
        "Can I get the brochure?",
    ])
    def test_detects_document_queries(self, prompt):
        assert _family(prompt) == "documents"


# ── Customer finance / payment ──────────────────────────────────────


class TestCustomerFinance:
    @pytest.mark.parametrize("prompt", [
        "How much have I paid and what is my outstanding amount?",
        "Tell me my outstanding balance. My email is test@example.com.",
        "What's my outstanding amount?",
        "Show me my payment history",
        "What is my payment status?",
        "Check my dues",
        "What is my outstanding balance?",
    ])
    def test_detects_finance_queries(self, prompt):
        assert _family(prompt) == "customer_finance"


# ── Investment guarantees ───────────────────────────────────────────


class TestInvestmentGuarantee:
    @pytest.mark.parametrize("prompt", [
        "Will this project's price definitely double in 3 years?",
        "Is appreciation guaranteed?",
        "Will the property definitely appreciate?",
        "Can you guarantee 15% returns?",
        "Will I definitely make money on this investment?",
    ])
    def test_detects_guarantee_queries(self, prompt):
        assert _family(prompt) == "investment_guarantee"


class TestBookingGuarantee:
    @pytest.mark.parametrize("prompt", [
        "Can you guarantee a 2 BHK is available to book today?",
        "Is the 3BHK guaranteed to be available?",
        "Can you promise I can book a flat today?",
        "Will a 2 BHK definitely be available next week?",
        "Is booking assured if I pay today?",
    ])
    def test_detects_booking_guarantee_queries(self, prompt):
        assert _family(prompt) == "booking_guarantee"

    @pytest.mark.parametrize("prompt", [
        "Is a 2 BHK available to book?",
        "Which units are available for booking?",
        "Can I definitely book a site visit tomorrow?",
        "How do I book a flat?",
    ])
    def test_ordinary_availability_not_intercepted(self, prompt):
        assert _family(prompt) != "booking_guarantee"


# ── Negative / non-regression: supported queries must pass through ─


class TestSupportedQueriesNotIntercepted:
    @pytest.mark.parametrize("prompt", [
        "What is the price of 3 BHK in Vishwajeet Prime?",
        "What is the current pricing?",
        "How much does a 2 BHK cost?",
        "What amenities does Vishwajeet Prime have?",
        "Is 3BHK available in Vishwajeet Prime?",
        "What is the construction status?",
        "Tell me about Vishwajeet Prime",
        "Which projects do you have?",
        "Hi",
        "What will be the total cost?",
        "What is the RERA number?",
        "I want to book a site visit",
        "What are the carpet area options?",
    ])
    def test_supported_query_not_intercepted(self, prompt):
        assert _detect(prompt) is None


# ── Edge: empty / blank issue ──────────────────────────────────────


def test_whitespace_issue_returns_none():
    assert _detect("   ") is None
