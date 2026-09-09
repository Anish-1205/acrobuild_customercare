import os
from functools import lru_cache
import logging
from threading import Event, Lock, Thread
from time import monotonic

import torch
from dotenv import load_dotenv
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer, StoppingCriteria, StoppingCriteriaList

logger = logging.getLogger(__name__)

from services.observability import get_logger, kv, preview

llm_logger = get_logger("llm")
QWEN_WARMUP_ERROR = ""

load_dotenv()

DEFAULT_QWEN_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
DEFAULT_QWEN_CPU_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
DEFAULT_QWEN_MAX_TOKENS = 64
DEFAULT_LLM_PROVIDER = "qwen"
MODEL_LOCK = Lock()
RUNTIME_LOAD_LOCK = Lock()


def normalize_qwen_text(value):
    return str(value or "").strip()


def get_llm_provider():
    provider = normalize_qwen_text(os.getenv("LLM_PROVIDER", DEFAULT_LLM_PROVIDER)).lower()
    if provider in {"sarvam", "runpod", "remote"}:
        return "sarvam"
    return "qwen"


def get_local_qwen_model_name():
    configured_model = normalize_qwen_text(os.getenv("QWEN_MODEL"))

    if configured_model:
        return configured_model

    if not torch.cuda.is_available():
        return (
            normalize_qwen_text(os.getenv("QWEN_CPU_MODEL"))
            or DEFAULT_QWEN_CPU_MODEL
        )

    return DEFAULT_QWEN_MODEL


def get_qwen_model_name():
    """Active chat model name for the configured LLM provider."""
    if get_llm_provider() == "sarvam":
        from sarvam_client import get_sarvam_model_name

        return get_sarvam_model_name()
    return get_local_qwen_model_name()


def get_llm_source_label():
    if get_llm_provider() == "sarvam":
        return "RunPod Sarvam"
    return "Live local Qwen"


def get_llm_agent_mode(success=True):
    if not success:
        return "live_llm_error"
    if get_llm_provider() == "sarvam":
        return "live_remote_llm"
    return "live_local_llm"


def get_qwen_max_tokens():
    try:
        return max(int(os.getenv("QWEN_MAX_TOKENS", DEFAULT_QWEN_MAX_TOKENS)), 32)
    except (TypeError, ValueError):
        return DEFAULT_QWEN_MAX_TOKENS


@lru_cache(maxsize=1)
def load_qwen_runtime():
    model_name = get_local_qwen_model_name()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
    model_options = {
        "torch_dtype": torch.float16 if device == "cuda" else torch.float32,
    }

    model_options["device_map"] = (
        "auto" if device == "cuda" else "cpu"
    )

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        local_files_only=True,
        **model_options,
    )


    model.eval()
    return tokenizer, model


def get_qwen_runtime():
    cpu_enabled = normalize_qwen_text(os.getenv("QWEN_ENABLE_CPU")).lower() in {
        "1", "true", "yes", "on"
    }
    if not torch.cuda.is_available() and not cpu_enabled:
        raise RuntimeError(
            "Qwen CPU generation is disabled for responsive chat. Set QWEN_ENABLE_CPU=true to enable it."
        )

    with RUNTIME_LOAD_LOCK:
        return load_qwen_runtime()


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


def _generate_local_qwen_chat_response(
    system_prompt,
    user_prompt,
    conversation_messages=None,
    model_name="",
    temperature=0.1,
):
    active_model = get_local_qwen_model_name()
    if model_name and normalize_qwen_text(model_name) != active_model:
        raise ValueError("Qwen is already configured with a different model.")

    tokenizer, model = get_qwen_runtime()
    messages = build_qwen_messages(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        conversation_messages=conversation_messages,
    )

    with MODEL_LOCK:
        inputs = tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
        ).to(model.device)
        generation_options = {
            "max_new_tokens": get_qwen_max_tokens(),
            "do_sample": temperature > 0,
            "pad_token_id": tokenizer.eos_token_id,
        }

        if temperature > 0:
            generation_options["temperature"] = max(float(temperature), 0.01)

        with torch.inference_mode():
            outputs = model.generate(**inputs, **generation_options)

    generated_tokens = outputs[0][inputs["input_ids"].shape[-1]:]
    answer = normalize_qwen_text(
        tokenizer.decode(generated_tokens, skip_special_tokens=True)
    )

    if not answer:
        raise RuntimeError("Qwen returned an empty response.")

    return answer


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
    from services.provider_resilience_service import guarded_generation
    provider = get_llm_provider()
    operation = _generate_sarvam_chat_response if provider == "sarvam" else _generate_local_qwen_chat_response
    history = len(conversation_messages or [])
    llm_logger.info(
        "llm call %s",
        kv(provider=provider, model=get_qwen_model_name(), mode="generate", temperature=temperature,
           history_turns=history, prompt=preview(user_prompt, 160)),
    )
    llm_logger.debug("llm system prompt %s", kv(text=system_prompt))
    started = monotonic()
    try:
        answer = guarded_generation(provider, lambda: operation(
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


def stream_qwen_chat_response(
    system_prompt,
    user_prompt,
    conversation_messages=None,
    model_name="",
    temperature=0.1,
):
    provider = get_llm_provider()
    llm_logger.info(
        "llm call %s",
        kv(provider=provider, model=get_qwen_model_name(), mode="stream", temperature=temperature,
           history_turns=len(conversation_messages or []), prompt=preview(user_prompt, 160)),
    )
    llm_logger.debug("llm system prompt %s", kv(text=system_prompt))
    started = monotonic()

    if provider == "sarvam":
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
        return

    active_model = get_local_qwen_model_name()
    if model_name and normalize_qwen_text(model_name) != active_model:
        raise ValueError("Qwen is already configured with a different model.")

    tokenizer, model = get_qwen_runtime()
    messages = build_qwen_messages(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        conversation_messages=conversation_messages,
    )
    inputs = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_tensors="pt",
        return_dict=True,
    ).to(model.device)
    streamer = TextIteratorStreamer(
        tokenizer,
        skip_prompt=True,
        skip_special_tokens=True,
        timeout=60.0,
    )
    generation_options = {
        **inputs,
        "max_new_tokens": get_qwen_max_tokens(),
        "do_sample": temperature > 0,
        "pad_token_id": tokenizer.eos_token_id,
        "streamer": streamer,
    }

    if temperature > 0:
        generation_options["temperature"] = max(float(temperature), 0.01)

    generation_error = []
    cancelled = Event()

    class StopWhenCancelled(StoppingCriteria):
        def __call__(self, input_ids, scores, **kwargs):
            return cancelled.is_set()

    generation_options["stopping_criteria"] = StoppingCriteriaList([StopWhenCancelled()])

    def run_generation():
        try:
            with MODEL_LOCK:
                with torch.inference_mode():
                    model.generate(**generation_options)
        except Exception as error:
            generation_error.append(error)
            streamer.on_finalized_text("", stream_end=True)

    generation_thread = Thread(target=run_generation, daemon=True)
    generation_thread.start()

    chunks = 0
    chars = 0
    try:
        for content_chunk in streamer:
            if content_chunk:
                chunks += 1
                chars += len(content_chunk)
                yield content_chunk
    finally:
        cancelled.set()
        generation_thread.join(timeout=5)

    if generation_error:
        llm_logger.warning(
            "llm stream failed %s",
            kv(provider="qwen", chunks=chunks, duration_ms=round((monotonic() - started) * 1000, 1),
               error=generation_error[0]),
        )
        raise RuntimeError("Qwen generation failed.") from generation_error[0]
    llm_logger.info(
        "llm stream done %s",
        kv(provider="qwen", chunks=chunks, reply_chars=chars,
           duration_ms=round((monotonic() - started) * 1000, 1)),
    )


def warm_qwen_model_async():
    if get_llm_provider() != "qwen":
        return

    def warm_runtime():
        global QWEN_WARMUP_ERROR
        try:
            get_qwen_runtime()
            QWEN_WARMUP_ERROR = ""
        except RuntimeError as error:
            QWEN_WARMUP_ERROR = type(error).__name__
            logger.exception("Qwen model warm-up failed")

    Thread(target=warm_runtime, daemon=True).start()


if __name__ == "__main__":
    print(
        generate_qwen_chat_response(
            system_prompt="You are a helpful customer support assistant.",
            user_prompt="Introduce yourself in one sentence.",
        )
    )
