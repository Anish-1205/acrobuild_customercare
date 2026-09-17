import unittest
from unittest.mock import patch

from graph import main_orchestrator as orchestrator
from services.reply_language import (
    build_reply_language_directive,
    heuristic_reply_language,
    looks_confidently_english,
    strip_reply_language_directive,
)
from services.turn_analysis_service import TurnAnalysis, _parse_analysis, analyze_turn


class HeuristicReplyLanguageTests(unittest.TestCase):
    def test_romanized_indian_languages(self):
        cases = {
            "aapke paas konse projects available hai?": "Hindi",
            "nee peru enti ?": "Telugu",
            "nee yenna pandre": "Tamil",
            "neevu hegiddira": "Kannada",
            "ningalude peru enthanu": "Malayalam",
            "tumhi kase aahat": "Marathi",
            "tumi kemon acho": "Bengali",
            "tamne shu joie che": "Gujarati",
            "tusi kiddan ho": "Punjabi",
        }
        for text, language in cases.items():
            with self.subTest(text=text):
                self.assertEqual(heuristic_reply_language(text), (language, "latin"))

    def test_native_scripts(self):
        self.assertEqual(heuristic_reply_language("भारत की राजधानी क्या है"), ("Hindi", "native"))
        self.assertEqual(heuristic_reply_language("మీకు ఏ ప్రాజెక్ట్‌లు ఉన్నాయి?"), ("Telugu", "native"))
        self.assertEqual(heuristic_reply_language("உங்கள் பெயர் என்ன"), ("Tamil", "native"))

    def test_native_devanagari_marathi_is_not_misread_as_hindi(self):
        self.assertEqual(
            heuristic_reply_language("ठाण्यात तुमच्या कोणत्या मालमत्ता आहेत?"), ("Marathi", "native")
        )
        self.assertEqual(heuristic_reply_language("मुझे 2 BHK फ्लैट चाहिए"), ("Hindi", "native"))

    def test_explicit_language_request_wins(self):
        self.assertEqual(heuristic_reply_language("marathi madhe bol"), ("Marathi", "latin"))
        self.assertEqual(heuristic_reply_language("english lo cheppu"), ("English", "latin"))

    def test_english_and_unknown(self):
        self.assertEqual(heuristic_reply_language("What flats do you have in Mumbai?"), ("English", "latin"))
        self.assertTrue(looks_confidently_english("who's the cm of telangana ?"))
        self.assertEqual(heuristic_reply_language("3"), ("", ""))
        self.assertEqual(heuristic_reply_language("3", "Telugu"), ("Telugu", "latin"))


class ReplyLanguageDirectiveTests(unittest.TestCase):
    def test_directive_never_reads_as_a_location(self):
        for language, script in (("English", "latin"), ("Telugu", "latin"), ("Tamil", "native"), ("", "")):
            directive = build_reply_language_directive(language, script)
            with self.subTest(language=language):
                self.assertNotRegex(directive, r"\b(?:in|near|at|around)\s+[A-Z]")
                self.assertEqual(strip_reply_language_directive(f"rate entha ?{directive}"), "rate entha ?")


class TurnAnalysisTests(unittest.TestCase):
    def test_parses_model_json_with_surrounding_text(self):
        self.assertEqual(
            _parse_analysis('Sure: {"intent": "general", "reply_language": "tamil", "script": "latin", '
                            '"english": "what are you doing?"}'),
            ("general", "Tamil", "latin", "what are you doing?"),
        )
        self.assertIsNone(_parse_analysis('{"intent": "weather", "reply_language": "Tamil"}'))
        self.assertIsNone(_parse_analysis("not json"))

    def test_native_script_is_taken_from_the_characters_not_the_model(self):
        with patch("qwen.generate_qwen_chat_response",
                   return_value='{"intent": "property", "reply_language": "Telugu", "script": "latin"}'):
            analysis = analyze_turn("మీకు ఏ ప్రాజెక్ట్‌లు ఉన్నాయి?", [])
        self.assertEqual((analysis.intent, analysis.reply_language, analysis.script), ("property", "Telugu", "native"))

    def test_clear_message_language_overrides_a_sticky_conversation_language(self):
        history = [{"sender": "customer", "text": "telugu vaccha ?"}, {"sender": "bot", "text": "Avunu."}]
        sticky = '{"intent": "general", "reply_language": "Telugu", "script": "latin", "english": "x"}'
        with patch("qwen.generate_qwen_chat_response", return_value=sticky):
            self.assertEqual(analyze_turn("nee yenna pandre", history).reply_language, "Tamil")
            self.assertEqual(analyze_turn("who's the cm of telangana ?", history).reply_language, "English")

    def test_mixed_message_labelled_english_keeps_its_indian_language(self):
        english = ('{"intent": "property", "reply_language": "English", "script": "latin", '
                   '"english": "what documents are needed for possession"}')
        with patch("qwen.generate_qwen_chat_response", return_value=english):
            self.assertEqual(analyze_turn("possession ki documents em kavali", []).reply_language, "Telugu")

    def test_documents_question_is_not_rewritten_into_construction_status(self):
        from graph.haystack_conversation_pipeline import resolve_contextual_support_issue
        history = [
            {"sender": "customer", "text": "tell me about Vishwajeet Paradise"},
            {"sender": "bot", "text": "Vishwajeet Paradise has 2 wings. Would you like to explore Vishwajeet Paradise?"},
        ]
        question = "what documents are needed for possession"
        self.assertEqual(resolve_contextual_support_issue(question, history), question)

    def test_documents_question_does_not_inherit_a_project_from_history(self):
        import services.ai_agent_service as service
        history = [{"sender": "customer", "text": "tell me about Vishwajeet Paradise"}]
        with patch.object(service, "_legacy_build_company_api_direct_answer", return_value="Docs answer") as legacy:
            service.build_company_api_direct_answer("what documents are needed for possession", [], history)
        self.assertEqual(legacy.call_args.kwargs["conversation_messages"], [])

    def test_acks_keep_the_conversation_language(self):
        history = [{"sender": "customer", "text": "telugu vaccha ?"}, {"sender": "bot", "text": "Avunu."}]
        english = '{"intent": "general", "reply_language": "English", "script": "latin", "english": "ok"}'
        with patch("qwen.generate_qwen_chat_response", return_value=english):
            self.assertEqual(analyze_turn("ok", history).reply_language, "Telugu")

    def test_falls_back_to_heuristics_when_the_model_fails(self):
        with patch("qwen.generate_qwen_chat_response", side_effect=RuntimeError("down")), \
                patch("graph.haystack_conversation_pipeline.search_company_knowledge", return_value=[]):
            analysis = analyze_turn("nee yenna pandre", [])
        self.assertEqual((analysis.source, analysis.intent, analysis.reply_language), ("heuristic", "general", "Tamil"))


class OrchestratorLanguageTests(unittest.TestCase):
    def test_general_reply_gets_the_analyzed_language_directive(self):
        analysis = TurnAnalysis("general", "Marathi", "latin", "llm")
        with patch.object(orchestrator, "generate_qwen_chat_response", return_value="Mi Acrobuild Support aahe.") as generate:
            response = orchestrator._build_live_general_llm_response("marathi madhe bol", [], analysis)
        user_prompt = generate.call_args.kwargs["user_prompt"]
        self.assertIn("[Reply language: Marathi", user_prompt)
        self.assertIn("languages you speak", generate.call_args.kwargs["system_prompt"])
        self.assertEqual(response["reply_language"], "Marathi")

    def test_english_canned_answers_are_skipped_for_other_languages(self):
        analysis = TurnAnalysis("general", "Telugu", "latin", "llm")
        with patch.object(orchestrator, "generate_qwen_chat_response", return_value="Nenu bagunnanu."):
            response = orchestrator._build_live_general_llm_response("how are you", [], analysis)
        self.assertEqual(response["answer"], "Nenu bagunnanu.")

    def test_english_template_answer_is_localized_keeping_numbers(self):
        analysis = TurnAnalysis("property", "Telugu", "latin", "llm")
        with patch.object(orchestrator, "generate_qwen_chat_response",
                          return_value="Vishwajeet Prime rate INR 4,000 - INR 8,000 per sq. ft. undi."):
            answer = orchestrator._localize_answer("Vishwajeet Prime: INR 4,000 - INR 8,000 per sq. ft.", analysis)
        self.assertIn("undi", answer)

    def test_localization_that_drops_a_number_is_rejected(self):
        analysis = TurnAnalysis("property", "Hindi", "latin", "llm")
        original = "Vishwajeet Prime: INR 4,000 - INR 8,000 per sq. ft."
        with patch.object(orchestrator, "generate_qwen_chat_response", return_value="Vishwajeet Prime ka rate 4,000 hai."):
            self.assertEqual(orchestrator._localize_answer(original, analysis), original)

    def test_already_localized_or_english_answers_are_left_alone(self):
        with patch.object(orchestrator, "generate_qwen_chat_response") as generate:
            self.assertEqual(
                orchestrator._localize_answer("Rate entha ante project meeda depend avtundi.",
                                              TurnAnalysis("property", "Telugu", "latin", "llm")),
                "Rate entha ante project meeda depend avtundi.",
            )
            self.assertEqual(
                orchestrator._localize_answer("Hello", TurnAnalysis("general", "English", "latin", "llm")),
                "Hello",
            )
        generate.assert_not_called()

    def test_hard_property_signal_overrides_a_general_label(self):
        general = TurnAnalysis("general", "Hindi", "latin", "llm")
        with patch.object(orchestrator, "analyze_turn", return_value=general), \
                patch.object(orchestrator, "resolve_contextual_support_issue", side_effect=lambda issue, _: issue), \
                patch.object(orchestrator, "get_live_project_names", return_value=["Vishwajeet Prime"]):
            self.assertTrue(orchestrator.prepare_turn("2 bhk ka rate?").analysis.is_property)
            self.assertTrue(orchestrator.prepare_turn("vishwajeet prime kaisa hai").analysis.is_property)
            self.assertFalse(orchestrator.prepare_turn("aap kaise ho").analysis.is_property)

    def test_non_english_messages_are_resolved_and_answered_via_the_english_rendering(self):
        analysis = TurnAnalysis("property", "Tamil", "latin", "llm", "Where is Vishwajeet Empire?")
        with patch.object(orchestrator, "analyze_turn", return_value=analysis), \
                patch.object(orchestrator, "resolve_contextual_support_issue", side_effect=lambda issue, _: issue) as resolve:
            turn = orchestrator.prepare_turn("vishwajeet empire enga irukku")
        self.assertEqual(resolve.call_args.args[0], "Where is Vishwajeet Empire?")
        self.assertEqual(turn.property_issue, "Where is Vishwajeet Empire?")
        self.assertEqual(turn.analysis.reply_language, "Tamil")

    def test_stream_emits_route_first(self):
        analysis = TurnAnalysis("general", "Tamil", "latin", "llm")
        turn = orchestrator.TurnContext([], "nee yenna pandre", analysis, "nee yenna pandre")
        with patch.object(orchestrator, "stream_qwen_chat_response", return_value=iter(["Naan ", "nalla irukken."])):
            events = list(orchestrator.stream_support_orchestration_events("nee yenna pandre", turn=turn))
        self.assertEqual(events[0], {"type": "route", "route": "general", "reply_language": "Tamil", "reply_script": "latin"})
        self.assertEqual(events[-1]["response"]["answer"], "Naan nalla irukken.")


if __name__ == "__main__":
    unittest.main()
