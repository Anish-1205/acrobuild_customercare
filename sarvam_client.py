"""RunPod OpenAI-compatible client for Sarvam chat completions."""
import os
from functools import lru_cache

import httpx
from dotenv import load_dotenv

load_dotenv()

DEFAULT_SARVAM_MAX_TOKENS = 300
DEFAULT_SARVAM_TIMEOUT_SECONDS = 120


def _normalize_text(value):
    return str(value or "").strip()


def get_sarvam_model_name():
    return _normalize_text(os.getenv("MODEL_NAME")) or "sarvamai/sarvam-30b-gguf:Q4_K_M"


def get_sarvam_max_tokens():
    try:
        return max(int(os.getenv("SARVAM_MAX_TOKENS", DEFAULT_SARVAM_MAX_TOKENS)), 32)
    except (TypeError, ValueError):
        return DEFAULT_SARVAM_MAX_TOKENS


class SarvamClient:
    def __init__(self):
        base_url = _normalize_text(os.getenv("RUNPOD_BASE_URL"))
        api_key = _normalize_text(os.getenv("RUNPOD_API_KEY"))
        if not base_url:
            raise RuntimeError("RUNPOD_BASE_URL is required when LLM_PROVIDER=sarvam.")
        if not api_key:
            raise RuntimeError("RUNPOD_API_KEY is required when LLM_PROVIDER=sarvam.")

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = get_sarvam_model_name()
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=float(
                os.getenv("SARVAM_TIMEOUT_SECONDS", DEFAULT_SARVAM_TIMEOUT_SECONDS)
            ),
        )

    def chat(self, messages, temperature=0.3, max_tokens=None):
        response = self.client.post(
            "/v1/chat/completions",
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens or get_sarvam_max_tokens(),
                "reasoning_effort": "none",
                "chat_template_kwargs": {
                    "enable_thinking": False,
                },
            },
        )
        response.raise_for_status()
        data = response.json()
        message = data["choices"][0]["message"]
        return _normalize_text(message.get("content", ""))


@lru_cache(maxsize=1)
def get_sarvam_client():
    return SarvamClient()


def generate_sarvam_chat_response(messages, temperature=0.1, max_tokens=None):
    answer = get_sarvam_client().chat(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if not answer:
        raise RuntimeError("Sarvam returned an empty response.")
    return answer
