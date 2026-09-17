"""RunPod OpenAI-compatible client for Sarvam chat completions."""
import os
import json
from functools import lru_cache
from time import monotonic

import httpx
from dotenv import load_dotenv

load_dotenv()

DEFAULT_SARVAM_MAX_TOKENS = 300
DEFAULT_SARVAM_REASONING_TOKENS = 1536
DEFAULT_SARVAM_TIMEOUT_SECONDS = 120
DEFAULT_SARVAM_DEADLINE_SECONDS = 45
THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"


def strip_reasoning(text):
    # The vLLM deployment ignores enable_thinking and has no reasoning parser, so <think> lands in content.
    text = text or ""
    if THINK_CLOSE in text:
        return text.split(THINK_CLOSE, 1)[1]
    if text.lstrip().startswith(THINK_OPEN):
        return ""
    return text


def get_sarvam_deadline_seconds():
    try:
        return max(int(os.getenv("SARVAM_DEADLINE_SECONDS", DEFAULT_SARVAM_DEADLINE_SECONDS)), 5)
    except (TypeError, ValueError):
        return DEFAULT_SARVAM_DEADLINE_SECONDS


def _normalize_text(value):
    return str(value or "").strip()


def get_sarvam_model_name():
    return _normalize_text(os.getenv("MODEL_NAME")) or "sarvamai/sarvam-30b-gguf:Q4_K_M"


def get_sarvam_max_tokens():
    try:
        return max(int(os.getenv("SARVAM_MAX_TOKENS", DEFAULT_SARVAM_MAX_TOKENS)), 32)
    except (TypeError, ValueError):
        return DEFAULT_SARVAM_MAX_TOKENS


def get_sarvam_request_max_tokens(max_tokens=None):
    # Hidden <think> tokens count against max_tokens, so reserve headroom on top of the answer budget.
    try:
        reasoning = max(int(os.getenv("SARVAM_REASONING_TOKENS", DEFAULT_SARVAM_REASONING_TOKENS)), 0)
    except (TypeError, ValueError):
        reasoning = DEFAULT_SARVAM_REASONING_TOKENS
    return (max_tokens or get_sarvam_max_tokens()) + reasoning


def _raise_for_status_with_body(response):
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        body = _normalize_text(response.text)[:500]
        raise httpx.HTTPStatusError(
            f"{error}. Response body: {body}" if body else str(error),
            request=error.request,
            response=error.response,
        ) from None


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
        try:
            total_timeout = float(os.getenv("SARVAM_TIMEOUT_SECONDS", DEFAULT_SARVAM_TIMEOUT_SECONDS))
        except (TypeError, ValueError):
            total_timeout = DEFAULT_SARVAM_TIMEOUT_SECONDS
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                # api.sarvam.ai requires this in addition to the bearer token;
                # a self-hosted OpenAI-compatible server ignores the extra header.
                "api-subscription-key": self.api_key,
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(total_timeout, connect=10.0),
        )

    def chat(self, messages, temperature=0.3, max_tokens=None):
        deadline = get_sarvam_deadline_seconds()
        response = self.client.post(
            "/v1/chat/completions",
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": get_sarvam_request_max_tokens(max_tokens),
                "chat_template_kwargs": {
                    "enable_thinking": False,
                },
            },
            timeout=httpx.Timeout(deadline, connect=10.0),
        )
        _raise_for_status_with_body(response)
        data = response.json()
        message = data["choices"][0]["message"]
        return _normalize_text(strip_reasoning(message.get("content", "")))

    def stream(self, messages, temperature=0.1, max_tokens=None):
        deadline = get_sarvam_deadline_seconds()
        started = monotonic()
        with self.client.stream("POST", "/v1/chat/completions", json={
            "model": self.model, "messages": messages, "temperature": temperature,
            "max_tokens": get_sarvam_request_max_tokens(max_tokens), "stream": True,
            "chat_template_kwargs": {"enable_thinking": False},
        }) as response:
            if response.is_error:
                response.read()
            _raise_for_status_with_body(response)
            buffer = ""
            passthrough = False
            for line in response.iter_lines():
                if monotonic() - started > deadline:
                    raise RuntimeError(
                        f"Sarvam response exceeded the {deadline}s deadline."
                    )
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                event = json.loads(payload)
                for choice in event.get("choices", []):
                    content = choice.get("delta", {}).get("content")
                    if not content:
                        continue
                    if passthrough:
                        yield content
                        continue
                    buffer += content
                    head = buffer.lstrip()
                    if THINK_OPEN.startswith(head):
                        continue
                    if not head.startswith(THINK_OPEN):
                        passthrough = True
                        yield buffer
                    elif THINK_CLOSE in buffer:
                        passthrough = True
                        answer = buffer.split(THINK_CLOSE, 1)[1].lstrip()
                        if answer:
                            yield answer
            if not passthrough and buffer.strip() and not buffer.lstrip().startswith(THINK_OPEN):
                yield buffer


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
