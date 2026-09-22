from time import monotonic

from dotenv import load_dotenv

from services.observability import get_logger, kv, preview

llm_logger = get_logger("llm")

load_dotenv()

DEFAULT_LLM_PROVIDER = "sarvam"


def normalize_qwen_text(value):
    return str(value or "").strip()


def get_llm_provider():
    return "sarvam"


def get_qwen_model_name():
    """Active chat model name for the configured LLM provider."""
    from sarvam_client import get_sarvam_model_name

    return get_sarvam_model_name()


def get_llm_source_label():
    return "RunPod Sarvam"


def get_llm_agent_mode(success=True):
    if not success:
        return "live_llm_error"
    return "live_remote_llm"


def build_qwen_messages(system_prompt, user_prompt, conversation_messages=None):
    messages = []
    cleaned_system_prompt = normalize_qwen_text(system_prompt)

    if cleaned_system_prompt:
        messages.append({"role": "system", "content": cleaned_system_prompt})

    history = list(conversation_messages or [])
    cleaned_user_prompt = normalize_qwen_text(user_prompt)
    if history:
        last_message = history[-1]
        if (
            normalize_qwen_text(last_message.get("sender")).lower() != "bot"
            and normalize_qwen_text(last_message.get("text")) == cleaned_user_prompt
        ):
            history = history[:-1]

    has_user_turn = False
    for message in history:
        content = normalize_qwen_text(message.get("text"))

        if not content:
            continue

        is_bot = normalize_qwen_text(message.get("sender")).lower() == "bot"
        # The widget opens with an assistant greeting before the customer has
        # spoken. Small local models can mistake that greeting for a user turn
        # or infer a broken conversation, so it is UI context rather than LLM
        # history.
        if is_bot and not has_user_turn:
            continue

        messages.append(
            {
                "role": "assistant" if is_bot else "user",
                "content": content,
            }
        )
        if not is_bot:
            has_user_turn = True

    messages.append({"role": "user", "content": cleaned_user_prompt})
    return messages


def _generate_sarvam_chat_response(
    system_prompt,
    user_prompt,
    conversation_messages=None,
    model_name="",
    temperature=0.1,
):
    from sarvam_client import generate_sarvam_chat_response, get_sarvam_model_name

    active_model = get_sarvam_model_name()
    if model_name and normalize_qwen_text(model_name) != active_model:
        raise ValueError("Sarvam is already configured with a different model.")

    messages = build_qwen_messages(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        conversation_messages=conversation_messages,
    )
    return generate_sarvam_chat_response(
        messages=messages,
        temperature=temperature,
    )


def generate_qwen_chat_response(
    system_prompt,
    user_prompt,
    conversation_messages=None,
    model_name="",
    temperature=0.1,
):
    from services.provider_resilience_service import guarded_generation, mark_completion
    provider = get_llm_provider()
    mark_completion(provider, provider)
    history = len(conversation_messages or [])
    llm_logger.info(
        "llm call %s",
        kv(provider=provider, model=get_qwen_model_name(), mode="generate", temperature=temperature,
           history_turns=history, prompt=preview(user_prompt, 160)),
    )
    llm_logger.debug("llm system prompt %s", kv(text=system_prompt))
    started = monotonic()
    try:
        answer = guarded_generation(provider, lambda: _generate_sarvam_chat_response(
            system_prompt=system_prompt, user_prompt=user_prompt,
            conversation_messages=conversation_messages, model_name=model_name, temperature=temperature))
    except Exception as error:
        llm_logger.warning(
            "llm call failed %s",
            kv(provider=provider, mode="generate", duration_ms=round((monotonic() - started) * 1000, 1), error=error),
        )
        raise
    llm_logger.info(
        "llm reply %s",
        kv(provider=provider, mode="generate", duration_ms=round((monotonic() - started) * 1000, 1),
           reply_chars=len(answer or ""), reply=preview(answer, 160)),
    )
    return answer


def stream_qwen_chat_response(system_prompt, user_prompt, conversation_messages=None, model_name="", temperature=0.1):
    provider = get_llm_provider()
    llm_logger.info(
        "llm call %s",
        kv(provider=provider, model=get_qwen_model_name(), mode="stream", temperature=temperature,
           history_turns=len(conversation_messages or []), prompt=preview(user_prompt, 160)),
    )
    llm_logger.debug("llm system prompt %s", kv(text=system_prompt))
    started = monotonic()

    from sarvam_client import get_sarvam_client
    chunks = 0
    chars = 0
    try:
        for piece in get_sarvam_client().stream(
            build_qwen_messages(system_prompt, user_prompt, conversation_messages), temperature=temperature):
            chunks += 1
            chars += len(piece)
            yield piece
    except Exception as error:
        llm_logger.warning(
            "llm stream failed %s",
            kv(provider=provider, chunks=chunks, duration_ms=round((monotonic() - started) * 1000, 1), error=error),
        )
        raise
    llm_logger.info(
        "llm stream done %s",
        kv(provider=provider, chunks=chunks, reply_chars=chars,
           duration_ms=round((monotonic() - started) * 1000, 1)),
    )


if __name__ == "__main__":
    print(
        generate_qwen_chat_response(
            system_prompt="You are a helpful customer support assistant.",
            user_prompt="Introduce yourself in one sentence.",
        )
    )
