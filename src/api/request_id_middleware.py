"""Request-ID ASGI middleware — Phase 1 #9 (ADR-0008).

Generates a UUID4 per HTTP request, attaches it to the Sentry scope
(when Sentry is active), and surfaces it as ``X-Request-ID`` in the
response. Frontend Sentry events read this header to correlate browser
errors with backend traces.

Usage in server.py (mirrors pna_middleware pattern):
    from src.api.request_id_middleware import request_id_middleware
    app = request_id_middleware(private_network_access_middleware(fastapi_app))
"""

from __future__ import annotations

import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


def request_id_middleware(app: ASGIApp) -> ASGIApp:
    async def middleware(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())

        # Starlette stores request state in scope["state"]; FastAPI exposes it
        # as request.state.request_id for downstream route handlers.
        state = scope.setdefault("state", {})
        state["request_id"] = request_id

        # Bind to Sentry scope when the SDK is active.
        try:
            import sentry_sdk

            sentry_sdk.set_tag("request_id", request_id)
        except Exception:  # SDK not initialised or sentry_sdk not installed
            pass

        async def send_with_request_id(message: Message) -> None:
            if message.get("type") == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
            await send(message)

        await app(scope, receive, send_with_request_id)

    return middleware
