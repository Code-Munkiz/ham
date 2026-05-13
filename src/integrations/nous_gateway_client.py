"""
Server-side adapter to the Hermes Agent API server (OpenAI-compatible /v1/chat/completions).

Browser and Ham API responses must remain HAM-native; this module is never imported from frontend code.
See docs/HERMES_GATEWAY_CONTRACT.md.
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Iterator
from typing import Any

import httpx

DEFAULT_TIMEOUT_SEC = 300.0
DEFAULT_MODEL = "hermes-agent"
DEFAULT_STREAM_STALL_SEC = 45.0
DEFAULT_STREAM_MAX_EXTRA_SEC = 120.0

logger = logging.getLogger(__name__)

# Retry primary Hermes request with HAM_CHAT_FALLBACK_MODEL on overload / transport / stall errors.
_HTTP_FALLBACK_STATUSES = frozenset({429, 502, 503, 504})
_FALLBACK_ERROR_CODES = frozenset(
    {
        "UPSTREAM_TIMEOUT",
        "UPSTREAM_UNAVAILABLE",
        "STREAM_STALLED",
        "STREAM_MAX_DURATION",
    },
)


class GatewayCallError(Exception):
    """Upstream failure or unusable response (HAM maps this to HTTP errors)."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _fallback_eligible(exc: GatewayCallError) -> bool:
    if exc.code in _FALLBACK_ERROR_CODES:
        return True
    st = getattr(exc, "http_status", None)
    return st is not None and st in _HTTP_FALLBACK_STATUSES


def format_gateway_error_user_message(exc: GatewayCallError) -> str:
    """Safe, user-visible explanation (no raw upstream text)."""
    if exc.code == "UPSTREAM_TIMEOUT":
        return (
            "The model gateway stopped responding in time. "
            "Try again shortly, or check gateway health if this persists."
        )
    if exc.code == "UPSTREAM_UNAVAILABLE":
        return (
            "Chat could not reach the model gateway (connection error). "
            "Check network and gateway availability, then retry."
        )
    if exc.code == "STREAM_STALLED":
        return (
            "The assistant stream stalled (no new data from the gateway for too long). "
            "Try again or switch models if this keeps happening."
        )
    if exc.code == "STREAM_MAX_DURATION":
        return (
            "This reply took too long overall and was stopped. "
            "Try a shorter question or retry."
        )
    if exc.code == "UPSTREAM_REJECTED":
        st = getattr(exc, "http_status", None)
        if st in {401, 403}:
            return (
                f"The model gateway refused authorization (HTTP {st}). "
                "An operator should verify Hermes gateway credentials (HERMES_GATEWAY_API_KEY) and that "
                "HERMES_GATEWAY_BASE_URL reaches the intended Hermes instance."
            )
        if st == 413:
            return (
                "Your chat context is too large for the model gateway. "
                "Older thread messages were trimmed for the next attempts; "
                "starting a new chat clears the buildup if this persists."
            )
        if st == 404:
            return (
                "The model gateway endpoint was not found (HTTP 404). "
                "Verify HERMES_GATEWAY_BASE_URL and that Hermes exposes OpenAI-compatible /v1/chat/completions."
            )
        if st == 422:
            return (
                "The model gateway rejected the request or model id (HTTP 422). "
                "Verify HERMES_GATEWAY_MODEL matches a model your Hermes server accepts."
            )
        if st == 429:
            return (
                "The model gateway rate-limited this request (HTTP 429). Try again in a moment."
            )
        if st is not None and st >= 500:
            return (
                "The model gateway returned a server error. Try again shortly or contact support if it continues."
            )
        return "The model gateway rejected the request. Try again or contact support if it continues."
    if exc.code == "OPENROUTER_MODEL_REJECTED":
        return (
            "OpenRouter rejected the selected model. Switch back to Hermes Agent / Default "
            "or choose a recommended model."
        )
    if exc.code == "INVALID_REQUEST":
        return exc.message
    if exc.code == "CONFIG_ERROR":
        return "Chat is misconfigured on the server. An administrator needs to fix gateway settings."
    return f"The assistant could not complete this turn ({exc.code})."


def _stream_stall_sec() -> float:
    raw = (os.environ.get("HAM_CHAT_HTTP_STALL_SEC") or "").strip()
    if raw:
        try:
            return max(0.001, float(raw))
        except ValueError:
            pass
    return DEFAULT_STREAM_STALL_SEC


def _stream_max_wall_sec(timeout_sec: float) -> float:
    raw = (os.environ.get("HAM_CHAT_HTTP_STREAM_MAX_SEC") or "").strip()
    if raw:
        try:
            return max(30.0, float(raw))
        except ValueError:
            pass
    return max(timeout_sec + DEFAULT_STREAM_MAX_EXTRA_SEC, 300.0)


def _iter_http_chat_completions(
    *,
    base: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    timeout_sec: float,
) -> Iterator[str]:
    """Single POST to Hermes /v1/chat/completions (streaming SSE)."""
    url = f"{base}/v1/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
    }

    stall_sec = _stream_stall_sec()
    max_wall_sec = _stream_max_wall_sec(timeout_sec)
    # Per-chunk read timeout catches TCP silence; stall_sec also enforced on empty SSE deltas below.
    connect_pool = min(30.0, max(5.0, stall_sec))
    httpx_timeout = httpx.Timeout(
        connect=connect_pool,
        read=stall_sec,
        write=min(60.0, max(10.0, stall_sec)),
        pool=connect_pool,
    )

    try:
        with httpx.Client(timeout=httpx_timeout) as client:
            with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code >= 400:
                    raise GatewayCallError(
                        "UPSTREAM_REJECTED",
                        f"Gateway HTTP {resp.status_code}",
                        http_status=resp.status_code,
                    )
                stream_started = time.monotonic()
                # Any received SSE line advances progress; gaps without new lines rely on httpx read timeout.
                last_stream_progress = stream_started
                for line in resp.iter_lines():
                    now = time.monotonic()
                    if now - stream_started > max_wall_sec:
                        raise GatewayCallError(
                            "STREAM_MAX_DURATION",
                            f"No completion within {max_wall_sec:.0f}s wall clock",
                        )
                    if line:
                        last_stream_progress = now
                    if now - last_stream_progress > stall_sec:
                        raise GatewayCallError(
                            "STREAM_STALLED",
                            f"No SSE progress for {stall_sec:.0f}s",
                        )
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


def _text_for_mock_user_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if not isinstance(p, dict):
                continue
            if p.get("type") == "text" and isinstance(p.get("text"), str):
                parts.append(p["text"])
            if p.get("type") == "image_url":
                parts.append("[image]")
        return "\n".join(parts).strip()
    return str(content or "").strip()


def _mock_assistant_text(messages: list[dict[str, Any]]) -> str:
    last_user = ""
    for t in reversed(messages):
        if t.get("role") == "user":
            last_user = _text_for_mock_user_content(t.get("content"))
            break
    if not last_user:
        last_user = "(no user message in history)"
    snippet = last_user[:400] + ("…" if len(last_user) > 400 else "")
    return f"Mock assistant reply. Last message: {snippet}"


def stream_chat_turn(
    messages: list[dict[str, Any]],
    *,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    openrouter_model_override: str | None = None,
    openrouter_litellm_api_key: str | None = None,
    force_openrouter_litellm_route: bool = False,
    gateway_context_budget_diag: dict[str, Any] | None = None,
) -> Iterator[str]:
    """
    Stream one completion as content deltas (OpenAI-style ``delta.content`` chunks).

    Raises:
        GatewayCallError: mock-safe errors and upstream failures (on first chunk setup).
    """
    if not messages:
        raise GatewayCallError("INVALID_REQUEST", "messages must not be empty")

    mode = _resolve_mode()

    def _yield_openrouter_litellm(*, bypass_http: bool) -> Iterator[str]:
        from src.llm_client import normalized_openrouter_api_key, openrouter_api_key_is_plausible
        from src.llm_client import stream_chat_messages_openrouter

        hinted = (openrouter_litellm_api_key or "").strip()
        if bypass_http:
            if not hinted or not openrouter_api_key_is_plausible(hinted):
                raise GatewayCallError(
                    "CONFIG_ERROR",
                    "Connected OpenRouter key required for BYOK dashboard chat.",
                )
            resolved = hinted
        elif hinted and openrouter_api_key_is_plausible(hinted):
            resolved = hinted
        else:
            resolved = normalized_openrouter_api_key()
        if not resolved or not openrouter_api_key_is_plausible(resolved):
            raise GatewayCallError(
                "CONFIG_ERROR",
                "OPENROUTER_API_KEY is not set or is not plausible for dashboard chat.",
            )
        try:
            yield from stream_chat_messages_openrouter(
                messages,
                model_override=openrouter_model_override,
                api_key_override=resolved,
            )
        except RuntimeError as exc:
            raise GatewayCallError("CONFIG_ERROR", str(exc)) from exc
        except Exception as exc:
            msg = str(exc).strip() or type(exc).__name__
            lower = msg.lower()
            if "timeout" in lower or "timed out" in lower:
                raise GatewayCallError("UPSTREAM_TIMEOUT", msg) from exc
            if bypass_http:
                raise GatewayCallError(
                    "OPENROUTER_MODEL_REJECTED",
                    "OpenRouter rejected the selected model for BYOK chat.",
                ) from exc
            raise GatewayCallError("UPSTREAM_REJECTED", msg) from exc

    # User BYOK bypass: authenticated OpenRouter completions while global gateway stays http (Hermes).
    if force_openrouter_litellm_route:
        yield from _yield_openrouter_litellm(bypass_http=True)
        return

    if mode == "mock":
        text = _mock_assistant_text(messages)
        step = max(1, min(16, len(text) // 8 or 1))
        for i in range(0, len(text), step):
            yield text[i : i + step]
        return

    if mode == "openrouter":
        yield from _yield_openrouter_litellm(bypass_http=False)
        return

    base = (os.environ.get("HERMES_GATEWAY_BASE_URL") or "").strip().rstrip("/")
    if not base:
        raise GatewayCallError(
            "CONFIG_ERROR",
            "HERMES_GATEWAY_BASE_URL is required when HERMES_GATEWAY_MODE=http",
        )

    api_key = (os.environ.get("HERMES_GATEWAY_API_KEY") or "").strip()
    primary = (os.environ.get("HERMES_GATEWAY_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    fallback = (os.environ.get("HAM_CHAT_FALLBACK_MODEL") or "").strip()

    from src.ham.hermes_http_context_budget import apply_hermes_http_context_budget

    msgs_for_http, budget_result = apply_hermes_http_context_budget(messages)
    if not msgs_for_http:
        raise GatewayCallError(
            "INVALID_REQUEST",
            "Hermes gateway context budget removed every message.",
        )
    if gateway_context_budget_diag is not None:
        gateway_context_budget_diag.clear()
        gateway_context_budget_diag.update(budget_result.as_dict())
    if budget_result.dropped_error_message_count > 0 or budget_result.truncated_for_gateway_budget:
        logger.info("hermes_http_context_budget=%s", json.dumps(budget_result.as_dict()))

    primary_emitted_chunk = False
    try:
        for chunk in _iter_http_chat_completions(
            base=base,
            api_key=api_key,
            model=primary,
            messages=msgs_for_http,
            timeout_sec=timeout_sec,
        ):
            primary_emitted_chunk = True
            yield chunk
    except GatewayCallError as exc:
        # Only retry before any user-visible tokens: mixing models mid-reply is worse than surfacing an error.
        if (
            not primary_emitted_chunk
            and fallback
            and fallback != primary
            and _fallback_eligible(exc)
        ):
            logger.warning(
                "ham_http_chat: primary model failed (code=%s http_status=%s); retrying once with fallback",
                exc.code,
                exc.http_status,
            )
            yield from _iter_http_chat_completions(
                base=base,
                api_key=api_key,
                model=fallback,
                messages=msgs_for_http,
                timeout_sec=timeout_sec,
            )
        else:
            raise


def complete_chat_turn(
    messages: list[dict[str, Any]],
    *,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    openrouter_model_override: str | None = None,
    openrouter_litellm_api_key: str | None = None,
    force_openrouter_litellm_route: bool = False,
    gateway_context_budget_diag: dict[str, Any] | None = None,
) -> str:
    """
    Run one non-streaming completion. `messages` are OpenAI-style dicts with role + content.

    Raises:
        GatewayCallError: mock-safe errors and upstream failures.
    """
    return "".join(
        stream_chat_turn(
            messages,
            timeout_sec=timeout_sec,
            openrouter_model_override=openrouter_model_override,
            openrouter_litellm_api_key=openrouter_litellm_api_key,
            force_openrouter_litellm_route=force_openrouter_litellm_route,
            gateway_context_budget_diag=gateway_context_budget_diag,
        ),
    ).strip()