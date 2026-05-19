"""Tests for src/api/request_id_middleware.py — Phase 1 #9 (ADR-0008).

Covers: UUID generation, X-Request-ID response header, request state binding.
"""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from src.api.request_id_middleware import request_id_middleware


def _make_app() -> object:
    async def echo(request: Request) -> JSONResponse:
        return JSONResponse({"request_id": request.state.request_id})

    routes = [Route("/echo", endpoint=echo)]
    starlette_app = Starlette(routes=routes)
    return request_id_middleware(starlette_app)


@pytest.fixture()
def client():
    return TestClient(_make_app(), raise_server_exceptions=True)


class TestRequestIdMiddleware:
    def test_response_has_x_request_id_header(self, client):
        response = client.get("/echo")
        assert "x-request-id" in response.headers

    def test_x_request_id_is_uuid4_format(self, client):
        import uuid

        response = client.get("/echo")
        header_val = response.headers["x-request-id"]
        parsed = uuid.UUID(header_val, version=4)
        assert str(parsed) == header_val

    def test_request_id_propagated_to_request_state(self, client):
        response = client.get("/echo")
        body = response.json()
        header_val = response.headers["x-request-id"]
        assert body["request_id"] == header_val

    def test_unique_id_per_request(self, client):
        r1 = client.get("/echo")
        r2 = client.get("/echo")
        assert r1.headers["x-request-id"] != r2.headers["x-request-id"]

    def test_non_http_scope_passes_through(self):
        """Lifespan/websocket scopes must not crash the middleware."""
        import asyncio

        calls: list[str] = []

        async def dummy_app(scope, receive, send):
            calls.append(scope["type"])

        wrapped = request_id_middleware(dummy_app)

        async def run():
            await wrapped({"type": "lifespan"}, None, None)

        asyncio.run(run())
        assert calls == ["lifespan"]
