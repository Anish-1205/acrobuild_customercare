"""Bounded requests and durable, privacy-preserving request telemetry."""
import hashlib
import json
import logging
import time
from contextlib import closing
from uuid import uuid4

from starlette.responses import JSONResponse
from services.database_service import open_database_connection

logger = logging.getLogger(__name__)


def audit_event(event, actor="", subject="", metadata=None, request_id=""):
    with closing(open_database_connection()) as conn, conn:
        conn.execute(
            "INSERT INTO audit_events(request_id,event,actor,subject,metadata,created_at) VALUES(?,?,?,?,?,?)",
            (request_id, event, str(actor), str(subject), json.dumps(metadata or {}), time.time()),
        )


def consume_limit(identity, route, limit, seconds=60):
    bucket = hashlib.sha256(f"{identity}:{route}".encode()).hexdigest()
    window = int(time.time()) // seconds * seconds
    with closing(open_database_connection()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM request_limits WHERE window_start < ?", (window - 3600,))
        conn.execute(
            "INSERT INTO request_limits VALUES(?,?,1) ON CONFLICT(bucket) DO UPDATE SET "
            "count=CASE WHEN window_start=excluded.window_start THEN count+1 ELSE 1 END, window_start=excluded.window_start",
            (bucket, window),
        )
        count = conn.execute("SELECT count FROM request_limits WHERE bucket=?", (bucket,)).fetchone()[0]
    return count <= limit


class RequestSecurityMiddleware:
    """ASGI middleware counts actual bytes, including chunked request bodies."""

    def __init__(self, app, max_bytes=16 * 1024 * 1024):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from starlette.concurrency import run_in_threadpool
        path = scope["path"]
        headers = dict(scope.get("headers", []))
        request_id = uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        budgets = {"/auth/login": 10, "/api/support/assist": 30,
                   "/api/support/assist/stream": 30, "/api/support/voice/synthesize": 10,
                   "/create_ticket": 10, "/api/site-visits": 10}
        limit = budgets.get(path, 10 if "upload" in path or "import-url" in path else None)
        if limit and scope["method"] != "OPTIONS":
            identity = str(scope.get("client", ("unknown",))[0])
            allowed = await run_in_threadpool(consume_limit, identity, path, limit)
            if not allowed:
                return await JSONResponse({"detail": "Too many requests. Try again shortly."}, 429, headers={"Retry-After": "60"})(scope, receive, send)
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse({"detail": "Invalid Content-Length."}, 400)(scope, receive, send)
        if declared > self.max_bytes:
            return await JSONResponse({"detail": "Request exceeds 16 MB."}, 413)(scope, receive, send)
        # Buffer only bounded mutation bodies, rejecting before downstream effects.
        messages, size = [], 0
        if scope["method"] in {"POST", "PUT", "PATCH", "DELETE"}:
            while True:
                message = await receive()
                size += len(message.get("body", b""))
                if size > self.max_bytes:
                    return await JSONResponse({"detail": "Request exceeds 16 MB."}, 413)(scope, receive, send)
                messages.append(message)
                if not message.get("more_body", False):
                    break
        async def bounded_receive():
            return messages.pop(0) if messages else await receive()
        started, status = time.monotonic(), 500
        async def observed_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-request-id", request_id.encode()), (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"), (b"cache-control", b"no-store"),
                ]
            await send(message)
        try:
            await self.app(scope, bounded_receive, observed_send)
        finally:
            route = getattr(scope.get("route"), "path", "unmatched")
            try:
                await run_in_threadpool(audit_event, "http_request", "", "", {
                    "route": route, "method": scope["method"], "status": status,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                }, request_id)
            except Exception:
                logger.exception("Could not persist request telemetry")
