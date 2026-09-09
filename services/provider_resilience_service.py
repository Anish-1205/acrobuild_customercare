"""Thread-safe circuit state; retries are restricted to failed generation calls."""
import time
from threading import Lock

_lock = Lock()
_states = {}


def guarded_generation(provider, operation):
    with _lock:
        state = _states.setdefault(provider, {"failures": 0, "opened_at": 0, "last_latency_ms": None})
        if state["failures"] >= 3 and time.monotonic() - state["opened_at"] < 30:
            raise RuntimeError(f"{provider} is temporarily unavailable")
    start = time.monotonic()
    try:
        result = operation()
    except Exception:
        with _lock:
            state["failures"] += 1
            state["opened_at"] = time.monotonic()
        raise
    with _lock:
        state.update(failures=0, opened_at=0, last_latency_ms=round((time.monotonic() - start) * 1000))
    try:
        from services.request_security_service import audit_event
        audit_event("model_call", metadata={"provider": provider, "latency_ms": state["last_latency_ms"],
                                             "output_characters": len(result), "token_count": None})
    except Exception:
        # Telemetry must not replace an otherwise successful model response.
        pass
    return result


def provider_health():
    with _lock:
        return {name: {"circuit_open": state["failures"] >= 3 and time.monotonic() - state["opened_at"] < 30,
                       "failures": state["failures"], "last_latency_ms": state["last_latency_ms"]} for name, state in _states.items()}
