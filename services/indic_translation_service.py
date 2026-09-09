import logging
import os
from pathlib import Path
from functools import lru_cache
from threading import Lock, Thread

from dotenv import load_dotenv
from huggingface_hub import snapshot_download

load_dotenv()
logger = logging.getLogger(__name__)
TRANSLATION_WARMUP_ERROR = ""

_WORKSPACE_HF_MODULES_CACHE = Path(__file__).resolve().parents[1] / "data" / "hf_modules"
_WORKSPACE_HF_MODULES_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_MODULES_CACHE", str(_WORKSPACE_HF_MODULES_CACHE))


DEFAULT_INDIC_TRANSLATION_MODEL = "ai4bharat/indictrans2-en-indic-dist-200M"
_LANGUAGE_CODES = {
    "assamese": "asm_Beng",
    "bengali": "ben_Beng",
    "bodo": "brx_Deva",
    "dogri": "doi_Deva",
    "gujarati": "guj_Gujr",
    "hindi": "hin_Deva",
    "kannada": "kan_Knda",
    "konkani": "gom_Deva",
    "maithili": "mai_Deva",
    "malayalam": "mal_Mlym",
    "manipuri": "mni_Beng",
    "marathi": "mar_Deva",
    "nepali": "npi_Deva",
    "odia": "ory_Orya",
    "punjabi": "pan_Guru",
    "sanskrit": "san_Deva",
    "santali": "sat_Olck",
    "sindhi": "snd_Arab",
    "tamil": "tam_Taml",
    "telugu": "tel_Telu",
    "urdu": "urd_Arab",
}
_TARGET_SCRIPT_CODES = {
    "asm_Beng": "as", "ben_Beng": "bn", "brx_Deva": "hi", "doi_Deva": "hi",
    "guj_Gujr": "gu", "hin_Deva": "hi", "kan_Knda": "kn", "gom_Deva": "hi",
    "mai_Deva": "hi", "mal_Mlym": "ml", "mni_Beng": "bn", "mar_Deva": "mr",
    "npi_Deva": "ne", "ory_Orya": "or", "pan_Guru": "pa", "san_Deva": "sa",
    "tam_Taml": "ta", "tel_Telu": "te",
}
_translation_lock = Lock()


def get_huggingface_token():
    return (os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN") or "").strip()


@lru_cache(maxsize=1)
def load_translation_pipeline():
    from transformers import pipeline

    token = get_huggingface_token() or None

    model_name = os.getenv(
        "INDIC_TRANSLATION_MODEL",
        DEFAULT_INDIC_TRANSLATION_MODEL,
    ).strip()
    local_model_path = snapshot_download(
        repo_id=model_name,
        token=token,
        local_files_only=True,
    )
    return pipeline(
        "translation",
        model=local_model_path,
        tokenizer=local_model_path,
        trust_remote_code=True,
        device=-1,
    )


@lru_cache(maxsize=256)
def translate_english_to_indic(text, language_name):
    cleaned_text = str(text or "").strip()
    target_language = _LANGUAGE_CODES.get(str(language_name or "").strip().lower())

    if not cleaned_text or not target_language:
        return cleaned_text

    translator = load_translation_pipeline()
    with _translation_lock:
        tagged_input = f"eng_Latn {target_language} {cleaned_text}"
        result = translator(
            tagged_input,
            max_length=320,
            num_beams=2,
        )

    if not result:
        raise RuntimeError("IndicTrans2 returned no translation.")

    translation = str(result[0].get("translation_text") or "").strip()
    script_code = _TARGET_SCRIPT_CODES.get(target_language)

    if translation and script_code and script_code != "hi":
        from indicnlp.transliterate.unicode_transliterate import UnicodeIndicTransliterator
        translation = UnicodeIndicTransliterator.transliterate(
            translation,
            "hi",
            script_code,
        )

    return translation or cleaned_text

def warm_translation_model_async():

    def warm_runtime():
        global TRANSLATION_WARMUP_ERROR
        try:
            load_translation_pipeline()
            TRANSLATION_WARMUP_ERROR = ""
        except Exception as error:
            TRANSLATION_WARMUP_ERROR = type(error).__name__
            logger.exception("Translation model warm-up failed")

    Thread(target=warm_runtime, daemon=True).start()
