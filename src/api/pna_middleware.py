"""
Local Network Access (Chrome / "Private Network Access") for cross-origin
``https://…`` → ``http://127.0.0.1`` fetches.

Public pages that call a loopback API send an OPTIONS preflight with
``Access-Control-Request-Private-Network: true``. The response must include
``Access-Control-Allow-Private-Network: true`` or the browser never sends the
real request and ``fetch`` throws ``TypeError: Failed to fetch`` — the same
symptom as a bad CORS allowlist.

Starlette 0.50 ``CORSMiddleware`` does not set this header. We append it to
**every** ``http.response.start`` (not only the preflight that carries
``Access-Control-Request-Private-Network: true``): Chrome is strict about
public HTTPS → ``http://127.0.0.1``; some builds expect the follow-up response
as well, and a bare ``send`` for non-preflight requests would otherwise never
get the flag.

CORS (allowed origins) is still enforced only by ``CORSMiddleware`` and
``HAM_CORS_ORIGINS`` / ``HAM_CORS_ORIGIN_REGEX``.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


def private_network_access_middleware(app: ASGIApp) -> ASGIApp:
    async def middleware(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await app(scope, receive, send)
            return

        async def send_add_pna(message: Message) -> None:
            if message.get("type") == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Access-Control-Allow-Private-Network"] = "true"
            await send(message)

        await app(scope, receive, send_add_pna)

    return middleware
