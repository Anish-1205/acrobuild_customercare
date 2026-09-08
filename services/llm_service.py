import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

DEFAULT_LLM_PROVIDER = "qwen"


def get_llm_provider():
    from qwen import get_llm_provider as _get_llm_provider

    return _get_llm_provider()


def get_llm_model_name():
    """Returns the active LLM model name for the configured provider."""
    from qwen import get_qwen_model_name

    return get_qwen_model_name()


@lru_cache(maxsize=1)
def get_llm_client():
    """
    Returns None for local Qwen; Sarvam uses sarvam_client.get_sarvam_client().
    Kept for backwards compatibility. Prefer generate_qwen_chat_response().
    """
    if get_llm_provider() == "sarvam":
        from sarvam_client import get_sarvam_client

        return get_sarvam_client()
    return None


def is_llm_available():
    """True when the configured provider can be used."""
    provider = get_llm_provider()
    if provider == "sarvam":
        api_key = str(os.getenv("RUNPOD_API_KEY") or "").strip()
        base_url = str(os.getenv("RUNPOD_BASE_URL") or "").strip()
        return bool(base_url and api_key)
    return True
