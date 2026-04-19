"""
Server-side adapter to the Hermes Agent API server (OpenAI-compatible /v1/chat/completions).

Browser and Ham API responses must remain HAM-native; this module is never imported from frontend code.
See docs/HERMES_GATEWAY_CONTRACT.md.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_TIMEOUT_SEC = 120.0
DEFAULT_MODEL = "hermes-agent"


class GatewayCallError(Exception):
    """Upstream failure or unusable response (HAM maps this to HTTP errors)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _resolve_mode() -> str:
    raw = (os.environ.get("HERMES_GATEWAY_MODE") or "").strip().lower()
    if raw == "mock":
        return "mock"
    if raw == "http":
        return "http"
    base = (os.environ.get("HERMES_GATEWAY_BASE_URL") or "").strip()
    return "http" if base else "mock"


def _mock_assistant_text(messages: list[dict[str, str]]) -> str:
    last_user = ""
    for t in reversed(messages):
        if t.get("role") == "user":
            last_user = (t.get("content") or "").strip()
            break
    if not last_user:
        last_user = "(no user message in history)"
    snippet = last_user[:400] + ("…" if len(last_user) > 400 else "")
    return f"Mock assistant reply. Last message: {snippet}"


def complete_chat_turn(
    messages: list[dict[str, str]],
    *,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> str:
    """
    Run one non-streaming completion. `messages` are OpenAI-style dicts with role + content.

    Raises:
        GatewayCallError: mock-safe errors and upstream failures.
    """
    if not messages:
        raise GatewayCallError("INVALID_REQUEST", "messages must not be empty")

    mode = _resolve_mode()
    if mode == "mock":
        return _mock_assistant_text(messages)

    base = (os.environ.get("HERMES_GATEWAY_BASE_URL") or "").strip().rstrip("/")
    if not base:
        raise GatewayCallError(
            "CONFIG_ERROR",
            "HERMES_GATEWAY_BASE_URL is required when HERMES_GATEWAY_MODE=http",
        )

    api_key = (os.environ.get("HERMES_GATEWAY_API_KEY") or "").strip()
    model = (os.environ.get("HERMES_GATEWAY_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL

    url = f"{base}/v1/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }

    try:
        with httpx.Client(timeout=timeout_sec) as client:
            resp = client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise GatewayCallError(
            "UPSTREAM_TIMEOUT",
            f"Gateway request timed out: {exc}",
        ) from exc
    except httpx.RequestError as exc:
        raise GatewayCallError(
            "UPSTREAM_UNAVAILABLE",
            f"Gateway connection failed: {exc}",
        ) from exc

    if resp.status_code >= 400:
        raise GatewayCallError(
            "UPSTREAM_REJECTED",
            f"Gateway HTTP {resp.status_code}",
        )

    try:
        data = resp.json()
    except ValueError as exc:
        raise GatewayCallError(
            "UPSTREAM_INVALID",
            "Gateway returned non-JSON body",
        ) from exc

    try:
        choices = data.get("choices")
        if not choices:
            raise KeyError("choices")
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if content is None:
            return ""
        return str(content).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise GatewayCallError(
            "UPSTREAM_INVALID",
            f"Unexpected gateway response shape: {exc}",
        ) from exc
