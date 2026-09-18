import json
import os
import unittest
from unittest.mock import MagicMock, patch

from qwen import (
    generate_qwen_chat_response,
    get_llm_agent_mode,
    get_llm_provider,
    get_llm_source_label,
    get_qwen_model_name,
)


class LlmProviderSwitchTests(unittest.TestCase):
    def setUp(self):
        # Routing tests must not inherit an open circuit from failure tests.
        state_patch = patch("services.provider_resilience_service._states", {})
        state_patch.start()
        self.addCleanup(state_patch.stop)

    def test_default_provider_is_qwen(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LLM_PROVIDER", None)
            self.assertEqual(get_llm_provider(), "qwen")
            self.assertEqual(get_llm_source_label(), "Live local Qwen")
            self.assertEqual(get_llm_agent_mode(success=True), "live_local_llm")

    def test_sarvam_provider_labels(self):
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "sarvam",
                "MODEL_NAME": "sarvamai/sarvam-30b-gguf:Q4_K_M",
            },
            clear=False,
        ):
            self.assertEqual(get_llm_provider(), "sarvam")
            self.assertEqual(get_llm_source_label(), "RunPod Sarvam")
            self.assertEqual(get_llm_agent_mode(success=True), "live_remote_llm")
            self.assertEqual(get_qwen_model_name(), "sarvamai/sarvam-30b-gguf:Q4_K_M")

    def test_generate_routes_to_sarvam(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "sarvam"}, clear=False):
            with patch(
                "qwen._generate_sarvam_chat_response",
                return_value="sarvam answer",
            ) as sarvam_generate:
                with patch("qwen._generate_local_qwen_chat_response") as local_generate:
                    answer = generate_qwen_chat_response(
                        system_prompt="Be helpful.",
                        user_prompt="Hello",
                    )

        self.assertEqual(answer, "sarvam answer")
        sarvam_generate.assert_called_once()
        local_generate.assert_not_called()

    def test_generate_routes_to_local_qwen(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "qwen"}, clear=False):
            with patch(
                "qwen._generate_local_qwen_chat_response",
                return_value="qwen answer",
            ) as local_generate:
                with patch("qwen._generate_sarvam_chat_response") as sarvam_generate:
                    answer = generate_qwen_chat_response(
                        system_prompt="Be helpful.",
                        user_prompt="Hello",
                    )

        self.assertEqual(answer, "qwen answer")
        local_generate.assert_called_once()
        sarvam_generate.assert_not_called()

    def test_sarvam_client_builds_openai_compatible_payload(self):
        with patch.dict(
            os.environ,
            {
                "RUNPOD_BASE_URL": "https://example.proxy.runpod.net",
                "RUNPOD_API_KEY": "test-key",
                "MODEL_NAME": "sarvamai/sarvam-30b-gguf:Q4_K_M",
            },
            clear=False,
        ):
            from sarvam_client import SarvamClient, get_sarvam_client

            get_sarvam_client.cache_clear()
            client = SarvamClient()
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "  hello from sarvam  "}}],
            }
            client.client.post = MagicMock(return_value=mock_response)

            answer = client.chat(
                messages=[{"role": "user", "content": "Hi"}],
                temperature=0,
                max_tokens=64,
            )

            self.assertEqual(answer, "hello from sarvam")
            payload = client.client.post.call_args.kwargs["json"]
            self.assertEqual(payload["model"], "sarvamai/sarvam-30b-gguf:Q4_K_M")
            self.assertEqual(payload["messages"][0]["content"], "Hi")
            self.assertNotIn("reasoning_effort", payload)
            get_sarvam_client.cache_clear()

    def _sarvam_client(self):
        from sarvam_client import SarvamClient
        with patch.dict(os.environ, {"RUNPOD_BASE_URL": "https://example.proxy.runpod.net",
                                     "RUNPOD_API_KEY": "test-key"}, clear=False):
            return SarvamClient()

    def _stream(self, pieces):
        client = self._sarvam_client()
        lines = [f'data: {{"choices": [{{"delta": {{"content": {json.dumps(p)}}}}}]}}' for p in pieces]
        response = MagicMock()
        response.iter_lines.return_value = lines + ["data: [DONE]"]
        client.client.stream = MagicMock()
        client.client.stream.return_value.__enter__.return_value = response
        return "".join(client.stream([{"role": "user", "content": "Hi"}]))

    def test_chat_strips_reasoning_block(self):
        client = self._sarvam_client()
        response = MagicMock()
        response.json.return_value = {"choices": [{"message": {"content": "<think>plan</think>\n\nNamaskaram!"}}]}
        client.client.post = MagicMock(return_value=response)
        self.assertEqual(client.chat([{"role": "user", "content": "Hi"}]), "Namaskaram!")

    def test_stream_strips_reasoning_split_across_chunks(self):
        self.assertEqual(self._stream(["<th", "ink>step 1", " step 2</thi", "nk>\n\nNamas", "karam!"]), "Namaskaram!")

    def test_stream_passes_through_answer_without_reasoning(self):
        self.assertEqual(self._stream(["Hello", " there"]), "Hello there")

    def test_stream_truncated_reasoning_yields_nothing(self):
        self.assertEqual(self._stream(["<think>still planning"]), "")


if __name__ == "__main__":
    unittest.main()
