"""Auth-aware HTTP client for ``opencode serve``.

Wraps :mod:`httpx` with Basic auth and a tiny set of explicit endpoint
methods. Tests inject a custom ``client_factory`` so no live HTTP
traffic is required.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

_LOG = logging.getLogger(__name__)


class HttpClientFactory(Protocol):
    """Factory protocol for constructing the underlying HTTP client.

    Production uses :func:`default_client_factory`. Tests inject a mock
    that returns an ``httpx.Client`` wired to an ``httpx.MockTransport``.
    """

    def __call__(self, *, base_url: str, auth: tuple[str, str]) -> httpx.Client: ...


def default_client_factory(*, base_url: str, auth: tuple[str, str]) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        auth=auth,
        timeout=httpx.Timeout(30.0, connect=5.0),
    )


@dataclass
class OpenCodeServeClient:
    """Thin auth-aware client wrapping a small set of explicit endpoints."""

    base_url: str
    auth: tuple[str, str]
    client: httpx.Client

    @classmethod
    def open(
        cls,
        *,
        base_url: str,
        auth: tuple[str, str],
        client_factory: HttpClientFactory | None = None,
    ) -> OpenCodeServeClient:
        factory = client_factory or default_client_factory
        return cls(base_url=base_url, auth=auth, client=factory(base_url=base_url, auth=auth))

    def close(self) -> None:
        try:
            self.client.close()
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("opencode_runner.http_close_raised %s", type(exc).__name__)

    def __enter__(self) -> OpenCodeServeClient:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # OpenCode HTTP endpoints
    # ------------------------------------------------------------------

    def health(self) -> httpx.Response:
        return self.client.get("/global/health")

    def put_auth(self, provider_id: str, payload: Mapping[str, Any]) -> httpx.Response:
        return self.client.put(f"/auth/{provider_id}", json=dict(payload))

    def create_session(self, *, title: str | None = None) -> httpx.Response:
        body: dict[str, Any] = {}
        if title:
            body["title"] = title
        return self.client.post("/session", json=body)

    def prompt_async(
        self,
        session_id: str,
        *,
        agent: str,
        model: str | None,
        prompt: str,
    ) -> httpx.Response:
        parts = [{"type": "text", "text": prompt}]
        payload: dict[str, Any] = {"agent": agent, "parts": parts}
        if model:
            payload["model"] = model
        return self.client.post(f"/session/{session_id}/prompt_async", json=payload)

    def respond_permission(
        self,
        session_id: str,
        permission_id: str,
        *,
        response: str,
        remember: bool = False,
    ) -> httpx.Response:
        return self.client.post(
            f"/session/{session_id}/permissions/{permission_id}",
            json={"response": response, "remember": remember},
        )

    def abort_session(self, session_id: str) -> httpx.Response:
        return self.client.post(f"/session/{session_id}/abort", json={})

    def dispose_instance(self) -> httpx.Response:
        return self.client.post("/instance/dispose", json={})


__all__ = [
    "HttpClientFactory",
    "OpenCodeServeClient",
    "default_client_factory",
]
