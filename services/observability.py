"""Central logging setup and chatbot pipeline tracing helpers.

One turn of the assistant is traceable end to end by its ``request_id``:
every log line emitted while handling a request carries the same id, so
``grep "<id>" logs/chatbot.log`` reconstructs the whole pipeline.

Environment knobs (all optional):
    LOG_LEVEL           root/uvicorn level                 (default INFO)
    CHATBOT_LOG_LEVEL   level for our own loggers          (default INFO; use DEBUG
                        to log full prompts, retrieved chunks and raw LLM output)
    LOG_FILE            rotating file path, "" disables     (default logs/chatbot.log)
    LOG_JSON            "true" -> one JSON object per line  (default false)
    LOG_COLOR           "true"/"false" force ANSI colour    (default: auto/tty)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from time import monotonic

# --- request correlation -------------------------------------------------

_request_id: ContextVar[str] = ContextVar("request_id", default="-")
_conversation_id: ContextVar[str] = ContextVar("conversation_id", default="-")

# Loggers we consider "ours"; they get CHATBOT_LOG_LEVEL and are the ones
# that carry pipeline detail.
_APP_LOGGERS = ("chatbot", "routers", "graph", "qwen", "sarvam_client", "services")


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def set_request_id(value: str) -> str:
    _request_id.set(value or "-")
    return value or "-"


def get_request_id() -> str:
    return _request_id.get()


def set_conversation_id(value) -> str:
    text = str(value or "").strip() or "-"
    _conversation_id.set(text)
    return text


def get_conversation_id() -> str:
    return _conversation_id.get()


def get_logger(name: str) -> logging.Logger:
    """Return a pipeline logger, e.g. get_logger("orchestrator")."""
    return logging.getLogger(f"chatbot.{name}")


# --- formatting helpers ------------------------------------------------------

def preview(value, limit: int = 200) -> str:
    """Single-line, length-capped rendering of free text for INFO logs."""
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        return text[:limit] + f"... (+{len(text) - limit} chars)"
    return text


# Documented `agent_mode` values. The legacy property-answer blob emits stale
# labels ("gemini", "llm"); map everything to this small enum for telemetry.
AGENT_MODE_ENUM = ("remote_llm", "local_llm", "retrieval", "grounded", "fallback", "live_data_error")

_AGENT_MODE_ALIASES = {
    "gemini": "remote_llm",
    "llm": "remote_llm",
    "remote": "remote_llm",
    "live_remote_llm": "remote_llm",
    "qwen": "local_llm",
    "local": "local_llm",
    "knowledge_retrieval": "retrieval",
    "knowledge": "retrieval",
    "rag": "retrieval",
    "grounded_answer": "grounded",
}


def normalize_agent_mode(value) -> str:
    text = str(value or "").strip().lower()
    if text in AGENT_MODE_ENUM:
        return text
    return _AGENT_MODE_ALIASES.get(text, "remote_llm" if text else "fallback")


def mask_email(value) -> str:
    text = str(value or "").strip()
    if "@" not in text:
        return text or "-"
    local, _, domain = text.partition("@")
    shown = local[:2] if len(local) > 2 else local[:1]
    return f"{shown}***@{domain}"


def kv(**fields) -> str:
    """Render fields as `key=value` pairs, quoting values with spaces."""
    parts = []
    for key, raw in fields.items():
        if raw is None:
            continue
        text = str(raw)
        if any(ch.isspace() for ch in text):
            text = '"' + text.replace('"', "'") + '"'
        parts.append(f"{key}={text}")
    return " ".join(parts)


class StageTimer:
    """Context manager: logs `<stage> start` / `<stage> ok|error` with duration."""

    def __init__(self, logger: logging.Logger, stage: str, **fields):
        self._logger = logger
        self._stage = stage
        self._fields = fields
        self._started = 0.0

    def __enter__(self):
        self._started = monotonic()
        self._logger.debug("%s start %s", self._stage, kv(**self._fields))
        return self

    def __exit__(self, exc_type, exc, tb):
        ms = round((monotonic() - self._started) * 1000, 1)
        if exc_type is None:
            self._logger.info("%s ok %s", self._stage, kv(duration_ms=ms, **self._fields))
        else:
            self._logger.warning(
                "%s error %s", self._stage, kv(duration_ms=ms, error=exc, **self._fields)
            )
        return False


# --- logging configuration -------------------------------------------------

class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        record.conversation_id = _conversation_id.get()
        return True


_LEVEL_COLOURS = {
    "DEBUG": "\033[36m", "INFO": "\033[32m", "WARNING": "\033[33m",
    "ERROR": "\033[31m", "CRITICAL": "\033[41m",
}
_RESET = "\033[0m"


class _PlainFormatter(logging.Formatter):
    def __init__(self, colour: bool):
        super().__init__(
            "%(asctime)s %(levelname)-5s [%(request_id)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        self._colour = colour

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        if self._colour:
            colour = _LEVEL_COLOURS.get(record.levelname, "")
            if colour:
                line = f"{colour}{line}{_RESET}"
        return line


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "request_id": getattr(record, "request_id", "-"),
            "conversation_id": getattr(record, "conversation_id", "-"),
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


_CONFIGURED = False


def _as_bool(value: str, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def configure_logging() -> None:
    """Idempotent. Safe to call at import time and under uvicorn --reload."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    root_level = os.getenv("LOG_LEVEL", "INFO").upper()
    app_level = os.getenv("CHATBOT_LOG_LEVEL", "INFO").upper()
    use_json = _as_bool(os.getenv("LOG_JSON"), False)
    colour = _as_bool(os.getenv("LOG_COLOR"), sys.stderr.isatty()) and not use_json
    log_file = os.getenv("LOG_FILE", "logs/chatbot.log").strip()

    formatter: logging.Formatter = _JsonFormatter() if use_json else _PlainFormatter(colour)
    id_filter = _RequestIdFilter()

    handlers: list[logging.Handler] = []

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    console.addFilter(id_filter)
    handlers.append(console)

    if log_file:
        try:
            os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
            file_handler = RotatingFileHandler(
                log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
            )
            file_handler.setFormatter(_JsonFormatter() if use_json else _PlainFormatter(False))
            file_handler.addFilter(id_filter)
            handlers.append(file_handler)
        except OSError as error:  # pragma: no cover - disk/permission edge
            # Keep the console handler; just report that the file sink failed.
            logging.getLogger("chatbot").warning("Could not open log file %s: %s", log_file, error)

    root = logging.getLogger()
    root.setLevel(root_level)
    for existing in list(root.handlers):
        root.removeHandler(existing)
    for handler in handlers:
        root.addHandler(handler)

    for name in _APP_LOGGERS:
        logging.getLogger(name).setLevel(app_level)

    # Third-party chatter: keep it out of the way unless something breaks.
    for name in ("httpx", "httpcore", "urllib3", "haystack", "sentence_transformers",
                 "transformers", "torch", "filelock"):
        logging.getLogger(name).setLevel(os.getenv("LIB_LOG_LEVEL", "WARNING").upper())

    # uvicorn installs its own handlers on these; drop them so our formatter
    # (with request_id) is the single source and lines are not duplicated.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv = logging.getLogger(name)
        uv.handlers.clear()
        uv.propagate = True

    logging.getLogger("chatbot").info(
        "logging configured %s",
        kv(root=root_level, chatbot=app_level, json=use_json, file=log_file or "-"),
    )
