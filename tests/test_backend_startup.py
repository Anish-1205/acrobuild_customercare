import os
import unittest
from unittest.mock import patch

import api_context as app


class BackendStartupTests(unittest.TestCase):
    @patch("api_context.warm_qwen_model_async")
    @patch("api_context.warm_translation_model_async")
    @patch("api_context.refresh_workspace_index_async")
    def test_heavy_startup_work_is_disabled_by_default(self, refresh_index, warm_translation, warm_qwen):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ACROBUILD_WARM_LOCAL_AI_MODELS", None)
            os.environ.pop("ACROBUILD_REFRESH_INDEX_ON_STARTUP", None)
            app.warm_ai_knowledge_index()
        refresh_index.assert_not_called()
        warm_translation.assert_not_called()
        warm_qwen.assert_not_called()

    @patch("api_context.warm_qwen_model_async")
    @patch("api_context.warm_translation_model_async")
    @patch("api_context.refresh_workspace_index_async")
    def test_heavy_model_preload_can_be_enabled_explicitly(self, refresh_index, warm_translation, warm_qwen):
        with patch.dict(os.environ, {
            "ACROBUILD_WARM_LOCAL_AI_MODELS": "true",
            "ACROBUILD_REFRESH_INDEX_ON_STARTUP": "true",
        }):
            app.warm_ai_knowledge_index()
        refresh_index.assert_called_once()
        warm_translation.assert_called_once()
        warm_qwen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
