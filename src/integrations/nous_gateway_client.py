"""
Server-side adapter to the Hermes Agent API server (OpenAI-compatible /v1/chat/completions).

Browser and Ham API responses must remain HAM-native; this module is never imported from frontend code.
See docs/HERMES_GATEWAY_CONTRACT.md.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterator
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
    if raw == "openrouter":
        return "openrouter"
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


def stream_chat_turn(
    messages: list[dict[str, str]],
    *,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> Iterator[str]:
    """
    Stream one completion as content deltas (OpenAI-style ``delta.content`` chunks).

    Raises:
        GatewayCallError: mock-safe errors and upstream failures (on first chunk setup).
    """
    if not messages:
        raise GatewayCallError("INVALID_REQUEST", "messages must not be empty")

    mode = _resolve_mode()
    if mode == "mock":
        text = _mock_assistant_text(messages)
        step = max(1, min(16, len(text) // 8 or 1))
        for i in range(0, len(text), step):
            yield text[i : i + step]
        return

    if mode == "openrouter":
        from src.llm_client import stream_chat_messages_openrouter

        try:
            yield from stream_chat_messages_openrouter(messages)
        except RuntimeError as exc:
            raise GatewayCallError("CONFIG_ERROR", str(exc)) from exc
        except Exception as exc:
            msg = str(exc).strip() or type(exc).__name__
            lower = msg.lower()
            if "timeout" in lower or "timed out" in lower:
                raise GatewayCallError("UPSTREAM_TIMEOUT", msg) from exc
            raise GatewayCallError("UPSTREAM_REJECTED", msg) from exc
        return

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
        "stream": True,
    }

    try:
        with httpx.Client(timeout=timeout_sec) as client:
            with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code >= 400:
                    raise GatewayCallError(
                        "UPSTREAM_REJECTED",
                        f"Gateway HTTP {resp.status_code}",
                    )
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    choices = data.get("choices")
                    if not choices:
                        continue
                    delta = (choices[0].get("delta") or {}) if isinstance(choices[0], dict) else {}
                    content = delta.get("content")
                    if content:
                        yield str(content)
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
    return "".join(stream_chat_turn(messages, timeout_sec=timeout_sec)).strip()
