"""Regression tests for LLM capability-overstatement post-processing.

Covers AMN-003 and related cases where the LLM proactively promises
unavailable capabilities in its generated responses.
"""

import pytest

from api_context import strip_capability_overstatements


# ── AMN-003: floor plans in amenity follow-up ──────────────────────


class TestAMN003FloorPlanRemoval:
    """The chatbot must not promise floor-plan retrieval."""

    def test_amn003_exact_phrase(self):
        text = "I can pull up the full amenity breakdown, floor plans, and pricing for either project."
        result = strip_capability_overstatements(text)
        assert "floor plan" not in result.lower()
        assert "amenity breakdown" in result.lower()
        assert "pricing" in result.lower()

    def test_floor_plan_in_standalone_sentence(self):
        text = "I can show you the floor plans for this project."
        assert strip_capability_overstatements(text) == ""

    def test_floor_plan_with_also(self):
        text = "I can also pull up floor plans and brochures."
        assert strip_capability_overstatements(text) == ""

    def test_floor_plan_removed_but_context_preserved(self):
        text = (
            "I have the amenity details for both projects. "
            "I can also pull up floor plans and brochures. "
            "Would you like to know more?"
        )
        result = strip_capability_overstatements(text)
        assert "floor plan" not in result.lower()
        assert "brochure" not in result.lower()
        assert "amenity details" in result.lower()
        assert "would you like" in result.lower()


# ── Blocked capability families ────────────────────────────────────


class TestBlockedDocuments:
    @pytest.mark.parametrize("text", [
        "I can show you the brochure for this project.",
        "Let me check the brochure for you.",
        "I'll get the floor plan for you.",
        "I can also show you the master plan.",
    ])
    def test_document_claims_removed(self, text):
        assert strip_capability_overstatements(text) == ""


class TestBlockedOffers:
    @pytest.mark.parametrize("text", [
        "I can check the current offers for this project.",
        "I can also look up live offers and discounts.",
        "Let me check the latest promotions for Vishwajeet Prime.",
    ])
    def test_offer_claims_removed(self, text):
        assert strip_capability_overstatements(text) == ""


class TestBlockedNearbyPlaces:
    @pytest.mark.parametrize("text", [
        "I can also show you nearby hospitals and schools.",
        "I can check nearby hospitals for this location.",
        "I can provide distances to key landmarks.",
    ])
    def test_nearby_claims_removed(self, text):
        assert strip_capability_overstatements(text) == ""


class TestBlockedCustomerFinance:
    @pytest.mark.parametrize("text", [
        "I can retrieve your payment status.",
        "I can check your payment history and outstanding balance.",
        "I can also look up your outstanding balance.",
    ])
    def test_finance_claims_removed(self, text):
        assert strip_capability_overstatements(text) == ""


class TestBlockedBookingStatus:
    def test_booking_status_removed(self):
        text = "I can check your booking status."
        assert strip_capability_overstatements(text) == ""


# ── List-item removal in mixed sentences ───────────────────────────


class TestListItemRemoval:
    def test_blocked_item_removed_from_list(self):
        text = "I can provide amenity details, floor plans, brochures, and pricing information."
        result = strip_capability_overstatements(text)
        assert "floor plan" not in result.lower()
        assert "brochure" not in result.lower()
        assert "amenity details" in result.lower()
        assert "pricing" in result.lower()

    def test_multiple_blocked_items_removed(self):
        text = "I can show you pricing, floor plans, offers, and availability."
        result = strip_capability_overstatements(text)
        assert "floor plan" not in result.lower()
        assert "offer" not in result.lower()
        assert "pricing" in result.lower()
        assert "availability" in result.lower()


# ── Supported capabilities must NOT be stripped ────────────────────


class TestSupportedCapabilitiesPreserved:
    @pytest.mark.parametrize("text", [
        "I can check the pricing and availability for this project.",
        "I can help you with a site visit request.",
        "I can also check the pricing for this project.",
        "Here are the amenity details for Vishwajeet Prime.",
        "I can show you the pricing, availability, and amenities.",
        "I can help with your support ticket.",
        "I can look up the project location for you.",
        "Let me check the configuration options.",
        "I can check the available BHK options.",
    ])
    def test_supported_capability_preserved(self, text):
        assert strip_capability_overstatements(text) == text


# ── Follow-up prompt phrases ───────────────────────────────────────


class TestFollowUpPhrases:
    """After amenity shortlist or project detail, the bot's follow-up
    should only mention supported capabilities."""

    def test_what_about_details_response(self):
        text = (
            "Sure! I can pull up the full amenity breakdown, floor plans, "
            "and pricing for either project."
        )
        result = strip_capability_overstatements(text)
        assert "floor plan" not in result.lower()
        assert "amenity breakdown" in result.lower()

    def test_what_else_can_you_show_response(self):
        text = (
            "I can show you detailed amenities, floor plans, brochures, "
            "pricing, and location information."
        )
        result = strip_capability_overstatements(text)
        assert "floor plan" not in result.lower()
        assert "brochure" not in result.lower()
        assert "amenities" in result.lower() or "pricing" in result.lower()

    def test_what_can_you_check_response(self):
        text = (
            "For this project I can check pricing, availability, amenities, "
            "floor plans, and nearby schools."
        )
        result = strip_capability_overstatements(text)
        assert "floor plan" not in result.lower()
        assert "nearby" not in result.lower()
        assert "pricing" in result.lower()
        assert "amenities" in result.lower()


# ── Edge cases ─────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_string(self):
        assert strip_capability_overstatements("") == ""

    def test_none_input(self):
        assert strip_capability_overstatements(None) is None

    def test_no_capability_claims(self):
        text = "Vishwajeet Prime is located in Kothrud, Pune."
        assert strip_capability_overstatements(text) == text

    def test_all_sentences_removed_yields_empty(self):
        text = "I can show you the floor plans. I can also check nearby hospitals."
        assert strip_capability_overstatements(text) == ""

    def test_supported_mentions_of_blocked_terms_not_in_promise(self):
        """When the bot DISCUSSES a blocked topic without promising to PROVIDE it,
        the text should remain unchanged."""
        text = "Floor plans are typically available at the sales office."
        assert strip_capability_overstatements(text) == text

    def test_customer_asking_about_documents_not_stripped(self):
        """The guard only strips bot PROMISES, not customer-like text."""
        text = "The brochure will be available at the sales office."
        assert strip_capability_overstatements(text) == text


# ── Capability question answer ─────────────────────────────────────


class TestCapabilityQuestionAnswer:
    """The deterministic 'what can you do?' answer must only list
    genuinely supported capabilities."""

    def test_no_blocked_capabilities_in_answer(self):
        from graph.haystack_conversation_pipeline import build_deterministic_conversation_answer
        answer = build_deterministic_conversation_answer("what can you do")
        lower = answer.lower()
        assert "document" not in lower
        assert "floor plan" not in lower
        assert "brochure" not in lower
        assert "payment" not in lower
        assert "handover" not in lower
        assert "maintenance" not in lower
        assert "construction update" not in lower

    def test_supported_capabilities_in_answer(self):
        from graph.haystack_conversation_pipeline import build_deterministic_conversation_answer
        answer = build_deterministic_conversation_answer("what can you do")
        lower = answer.lower()
        assert "project" in lower
        assert "pricing" in lower
        assert "availability" in lower
        assert "site-visit" in lower or "site visit" in lower
        assert "ticket" in lower
