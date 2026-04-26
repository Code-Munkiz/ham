"""
Local Network Access (Chrome / "Private Network Access") for cross-origin
``https://…`` → ``http://127.0.0.1`` fetches.

Public pages that call a loopback API send an OPTIONS preflight with
``Access-Control-Request-Private-Network: true``. The response must include
``Access-Control-Allow-Private-Network: true`` or the browser never sends the
real request and ``fetch`` throws ``TypeError: Failed to fetch`` — the same
symptom as a bad CORS allowlist.

Starlette 0.50 ``CORSMiddleware`` does not set this header; this ASGI layer
adds it when the preflight request asks for PNA. Still require the origin in
``HAM_CORS_ORIGINS`` (or ``HAM_CORS_ORIGIN_REGEX``) so the inner CORS layer
can allow the Vercel origin.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


def private_network_access_middleware(app: ASGIApp) -> ASGIApp:
    async def middleware(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await app(scope, receive, send)
            return
        needs_pna = any(
            k == b"access-control-request-private-network" and v.decode("latin-1").lower() == "true"
            for k, v in scope.get("headers", [])
        )
        if not needs_pna:
            await app(scope, receive, send)
            return

        async def send_with_pna(message: Message) -> None:
            if message.get("type") == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Access-Control-Allow-Private-Network"] = "true"
            await send(message)

        await app(scope, receive, send_with_pna)

    return middleware
