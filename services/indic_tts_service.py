import io
import asyncio
import os
from functools import lru_cache
from threading import Lock

import torch
from huggingface_hub import snapshot_download


DEFAULT_INDIC_TTS_MODEL = "ai4bharat/indic-parler-tts"
DEFAULT_VOICE_DESCRIPTION = (
    "A warm Indian speaker talks naturally in a conversational tone at a moderate pace. "
    "The recording is very clear and close, with no background noise."
)
_generation_lock = Lock()

EDGE_VOICES = {
    "bn-IN": "bn-IN-TanishaaNeural", "gu-IN": "gu-IN-DhwaniNeural",
    "hi-IN": "hi-IN-SwaraNeural", "kn-IN": "kn-IN-SapnaNeural",
    "ml-IN": "ml-IN-SobhanaNeural", "mr-IN": "mr-IN-AarohiNeural",
    "ne-NP": "ne-NP-HemkalaNeural", "ta-IN": "ta-IN-PallaviNeural",
    "te-IN": "te-IN-ShrutiNeural", "ur-IN": "ur-IN-GulNeural",
}


async def _generate_edge_speech(text, voice):
    import edge_tts
    audio_parts = []
    communicator = edge_tts.Communicate(text, voice, rate="-4%")
    async for chunk in communicator.stream():
        if chunk.get("type") == "audio":
            audio_parts.append(chunk["data"])
    if not audio_parts:
        raise RuntimeError("The online neural voice returned no audio.")
    return b"".join(audio_parts)


def generate_fast_indic_speech(text, language=""):
    voice = EDGE_VOICES.get(str(language or "").strip())
    if not voice:
        return None
    return asyncio.run(_generate_edge_speech(str(text or "").strip(), voice))


def get_huggingface_token():
    return (os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN") or "").strip()


def get_indic_tts_device():
    configured_device = os.getenv("INDIC_TTS_DEVICE", "cpu").strip().lower()
    if configured_device.startswith("cuda") and torch.cuda.is_available():
        return configured_device
    return "cpu"


@lru_cache(maxsize=1)
def load_indic_tts_runtime():
    try:
        from parler_tts import ParlerTTSForConditionalGeneration
        from transformers import AutoTokenizer
    except ImportError as error:
        raise RuntimeError(
            "Indic voice dependencies are missing. Install requirements.txt first."
        ) from error

    token = get_huggingface_token() or None

    model_name = os.getenv("INDIC_TTS_MODEL", DEFAULT_INDIC_TTS_MODEL).strip()
    local_model_path = snapshot_download(
        repo_id=model_name,
        token=token,
        local_files_only=True,
    )
    device = get_indic_tts_device()
    model = ParlerTTSForConditionalGeneration.from_pretrained(
        local_model_path,
    ).to(device)
    prompt_tokenizer = AutoTokenizer.from_pretrained(local_model_path)
    description_tokenizer = AutoTokenizer.from_pretrained(
        model.config.text_encoder._name_or_path,
        token=token,
    )
    model.eval()
    return model, prompt_tokenizer, description_tokenizer, device


def generate_indic_speech(text, description=""):
    import soundfile as sf

    cleaned_text = str(text or "").strip()
    if not cleaned_text:
        raise ValueError("Speech text is required.")
    if len(cleaned_text) > 1200:
        raise ValueError("Speech text must be 1200 characters or fewer.")

    model, prompt_tokenizer, description_tokenizer, device = load_indic_tts_runtime()
    voice_description = str(description or "").strip() or DEFAULT_VOICE_DESCRIPTION
    description_inputs = description_tokenizer(
        voice_description,
        return_tensors="pt",
    ).to(device)
    prompt_inputs = prompt_tokenizer(cleaned_text, return_tensors="pt").to(device)

    with _generation_lock, torch.inference_mode():
        generation = model.generate(
            input_ids=description_inputs.input_ids,
            attention_mask=description_inputs.attention_mask,
            prompt_input_ids=prompt_inputs.input_ids,
            prompt_attention_mask=prompt_inputs.attention_mask,
        )

    audio = generation.detach().cpu().float().numpy().squeeze()
    output = io.BytesIO()
    sf.write(output, audio, model.config.sampling_rate, format="WAV")
    output.seek(0)
    return output.getvalue()