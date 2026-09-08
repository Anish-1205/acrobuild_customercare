from collections import deque
from contextvars import ContextVar
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

_MAX_LOGS = 500
_LOGS = deque(maxlen=_MAX_LOGS)
_LOG_LOCK = Lock()
_TRACE_CONTEXT = ContextVar("data_api_trace", default={})


def begin_data_api_trace(conversation_id="", question=""):
    return _TRACE_CONTEXT.set({
        "trace_id": uuid4().hex,
        "conversation_id": str(conversation_id or "").strip(),
        "question": str(question or "").strip(),
    })


def end_data_api_trace(token):
    try:
        _TRACE_CONTEXT.reset(token)
    except ValueError:
        # StreamingResponse can resume a synchronous generator in a different
        # worker context. Clear that context instead of crashing the stream.
        _TRACE_CONTEXT.set({})


def log_data_api_call(
    *,
    provider,
    endpoint,
    method="GET",
    params=None,
    status="completed",
    duration_ms=0,
    cache_hit=False,
    response_summary=None,
    error="",
):
    context = dict(_TRACE_CONTEXT.get() or {})
    record = {
        "id": uuid4().hex,
        "trace_id": context.get("trace_id", ""),
        "conversation_id": context.get("conversation_id", ""),
        "question": context.get("question", ""),
        "provider": str(provider or "Data API"),
        "endpoint": str(endpoint or ""),
        "method": str(method or "GET").upper(),
        "params": dict(params or {}),
        "status": str(status or "completed"),
        "duration_ms": max(int(duration_ms or 0), 0),
        "cache_hit": bool(cache_hit),
        "response_summary": response_summary or {},
        "error": str(error or ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with _LOG_LOCK:
        _LOGS.appendleft(record)
    return record



def get_current_data_api_logs():
    trace_id = str((_TRACE_CONTEXT.get() or {}).get("trace_id", ""))
    if not trace_id:
        return []
    with _LOG_LOCK:
        records = [record for record in _LOGS if record.get("trace_id") == trace_id]
    return [
        {
            "id": record.get("id", ""),
            "provider": record.get("provider", ""),
            "endpoint": record.get("endpoint", ""),
            "method": record.get("method", "GET"),
            "params": record.get("params", {}),
            "status": record.get("status", ""),
            "duration_ms": record.get("duration_ms", 0),
            "cache_hit": record.get("cache_hit", False),
            "response_summary": record.get("response_summary", {}),
            "error": record.get("error", ""),
            "created_at": record.get("created_at", ""),
        }
        for record in reversed(records)
    ]
def get_data_api_logs(conversation_id="", limit=200):
    normalized_id = str(conversation_id or "").strip()
    safe_limit = min(max(int(limit or 200), 1), _MAX_LOGS)
    with _LOG_LOCK:
        records = list(_LOGS)
    if normalized_id:
        records = [record for record in records if record.get("conversation_id") == normalized_id]
    return records[:safe_limit]


def clear_data_api_logs():
    with _LOG_LOCK:
        _LOGS.clear()