import unittest
from unittest.mock import patch

from graph.haystack_conversation_pipeline import (
    is_property_support_message,
    matches_live_company_context,
)

PROJECT_CHUNKS = [
    {
        "source_key": "acrobuild-cs-projects",
        "project_names": ["Vishwajeet Prime", "Thane Heights"],
        "body_text": "Vishwajeet Prime and Thane Heights are live Acrobuild projects.",
    }
]


class CompanyContextMatchingTests(unittest.TestCase):
    @patch("graph.haystack_conversation_pipeline.search_company_knowledge", return_value=PROJECT_CHUNKS)
    def test_generic_word_shared_with_a_project_name_does_not_match(self, _mock):
        self.assertFalse(matches_live_company_context("who is the current prime minister of India"))

    @patch("graph.haystack_conversation_pipeline.search_company_knowledge", return_value=PROJECT_CHUNKS)
    def test_full_project_name_still_matches(self, _mock):
        self.assertTrue(matches_live_company_context("what floors does Vishwajeet Prime have"))

    @patch("graph.haystack_conversation_pipeline.search_company_knowledge", return_value=PROJECT_CHUNKS)
    def test_distinctive_word_from_project_name_still_matches(self, _mock):
        self.assertTrue(matches_live_company_context("tell me about Vishwajeet"))

    @patch("graph.haystack_conversation_pipeline.search_company_knowledge", return_value=PROJECT_CHUNKS)
    def test_unrelated_general_question_does_not_match(self, _mock):
        self.assertFalse(matches_live_company_context("what is the capital of Australia"))


class PropertySupportTermMatchingTests(unittest.TestCase):
    def test_property_term_embedded_in_an_unrelated_word_does_not_match(self):
        self.assertFalse(is_property_support_message("who is the current president of the united states"))

    def test_whole_word_property_term_still_matches(self):
        self.assertTrue(is_property_support_message("what is the price of unit 402"))

    def test_home_as_a_whole_word_still_matches(self):
        self.assertTrue(is_property_support_message("do you have any homes available"))

    def test_unrelated_general_question_does_not_match(self):
        self.assertFalse(is_property_support_message("what is the capital of Australia"))


if __name__ == "__main__":
    unittest.main()
