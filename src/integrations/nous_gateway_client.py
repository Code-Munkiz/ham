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

# Private builder artifact channel (NOT user-facing chat). Optional dedicated
# model/profile for artifact generation; falls back to the configured chat model
# when unset. JSON mode is requested via response_format so the backend receives a
# parseable file artifact rather than conversational prose.
BUILDER_MODEL_ENV = "HERMES_BUILDER_MODEL"
_ARTIFACT_RESPONSE_FORMAT: dict[str, Any] = {"type": "json_object"}

# Artifact transport budget — deliberately independent of the user-chat SSE
# stall/wall guards (HAM_CHAT_HTTP_*) that keep conversational replies snappy.
# A native build returns one large file bundle, so artifact mode prefers a single
# non-streaming completion with a generous blocking budget; this avoids
# STREAM_MAX_DURATION when the bundle takes longer than the chat stream cap.
ARTIFACT_TIMEOUT_ENV = "HERMES_ARTIFACT_TIMEOUT_SEC"
ARTIFACT_STREAM_ENV = "HERMES_ARTIFACT_STREAM"
DEFAULT_ARTIFACT_TIMEOUT_SEC = 300.0

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
    """Safe, user-visible explanation (no raw upstream text; HAM-natural voice, no env names)."""
    if exc.code == "UPSTREAM_TIMEOUT":
        return (
            "The model is taking too long to respond. "
            "Try again in a moment, or switch models in Settings."
        )
    if exc.code == "UPSTREAM_UNAVAILABLE":
        return (
            "I'm having trouble reaching the model right now. "
            "Try again in a moment, or switch models in Settings."
        )
    if exc.code == "STREAM_STALLED":
        return (
            "The reply stalled mid-stream. "
            "Try again, or switch models in Settings if it keeps happening."
        )
    if exc.code == "STREAM_MAX_DURATION":
        return (
            "This reply took too long and was stopped. "
            "Try a shorter question, or try again."
        )
    if exc.code == "UPSTREAM_REJECTED":
        st = getattr(exc, "http_status", None)
        if st in {401, 403}:
            return (
                "I can't reach the model right now (authorization issue). "
                "Try again later, or switch models in Settings."
            )
        if st == 413:
            return (
                "This chat thread is too large for the model. "
                "Older messages were trimmed for the next attempts; "
                "starting a new chat clears the buildup if this persists."
            )
        if st == 404:
            return (
                "I can't find the selected model right now. "
                "Try again, or switch models in Settings."
            )
        if st == 422:
            return (
                "The selected model didn't accept this request. "
                "Switch models in Settings and try again."
            )
        if st == 429:
            return (
                "Too many requests for the model right now. "
                "Give it a moment and try again."
            )
        if st is not None and st >= 500:
            return (
                "The model returned an error. "
                "Try again shortly, or switch models in Settings."
            )
        return (
            "I'm having trouble reaching the model right now. "
            "Try again, or switch models in Settings."
        )
    if exc.code == "OPENROUTER_MODEL_REJECTED":
        return (
            "That model isn't available right now. "
            "Switch models in Settings and try again."
        )
    if exc.code == "INVALID_REQUEST":
        return exc.message
    if exc.code == "CONFIG_ERROR":
        return (
            "Chat isn't configured correctly on this server. "
            "An administrator needs to fix it before I can reply."
        )
    return (
        "I'm having trouble completing this reply right now. "
        "Try again, or switch models in Settings."
    )


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


def _http_chat_payload(
    model: str,
    messages: list[dict[str, Any]],
    response_format: dict[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
    if response_format is not None:
        payload["response_format"] = response_format
    return payload


def _iter_http_chat_completions(
    *,
    base: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    timeout_sec: float,
    response_format: dict[str, Any] | None = None,
    stall_sec: float | None = None,
    max_wall_sec: float | None = None,
) -> Iterator[str]:
    """Single POST to Hermes /v1/chat/completions (streaming SSE).

    ``stall_sec`` / ``max_wall_sec`` default to the user-chat guards
    (``HAM_CHAT_HTTP_*``); callers (e.g. the artifact channel) may override them
    with a transport-specific budget without changing conversational behavior.
    """
    url = f"{base}/v1/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = _http_chat_payload(model, messages, response_format)

    stall_sec = _stream_stall_sec() if stall_sec is None else max(0.001, stall_sec)
    max_wall_sec = _stream_max_wall_sec(timeout_sec) if max_wall_sec is None else max(30.0, max_wall_sec)
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


def _normalize_http_model_override(http_model_override: str | None) -> str | None:
    if http_model_override is None:
        return None
    stripped = http_model_override.strip()
    if not stripped:
        return None
    if "\n" in stripped or "\r" in stripped:
        return None
    return stripped


def stream_chat_turn(
    messages: list[dict[str, Any]],
    *,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    openrouter_model_override: str | None = None,
    openrouter_litellm_api_key: str | None = None,
    force_openrouter_litellm_route: bool = False,
    gateway_context_budget_diag: dict[str, Any] | None = None,
    http_model_override: str | None = None,
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
    configured_primary = (os.environ.get("HERMES_GATEWAY_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    primary_override = _normalize_http_model_override(http_model_override)
    primary = primary_override or configured_primary
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
    http_model_override: str | None = None,
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
            http_model_override=http_model_override,
        ),
    ).strip()


def builder_artifact_model_override() -> str | None:
    """Optional dedicated model/profile id for the private builder artifact channel."""
    raw = (os.environ.get(BUILDER_MODEL_ENV) or "").strip()
    return raw or None


def _artifact_timeout_sec() -> float:
    """Artifact transport budget (seconds), independent of chat stream guards."""
    raw = (os.environ.get(ARTIFACT_TIMEOUT_ENV) or "").strip()
    if raw:
        try:
            return max(30.0, min(600.0, float(raw)))
        except ValueError:
            pass
    return DEFAULT_ARTIFACT_TIMEOUT_SEC


def _artifact_prefer_streaming() -> bool:
    """Opt-in to force streaming for artifact mode (default: prefer non-streaming)."""
    raw = (os.environ.get(ARTIFACT_STREAM_ENV) or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _http_chat_completion_blocking(
    *,
    base: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    timeout_sec: float,
    response_format: dict[str, Any] | None = None,
) -> str:
    """Single non-streaming POST to Hermes /v1/chat/completions (``stream: false``).

    Returns the full assistant content in one blocking response, free of the SSE
    stall/wall guards used for user chat. Raises ``NON_STREAMING_UNSUPPORTED`` if
    the gateway does not return a parseable one-shot JSON body (caller may then
    fall back to streaming). Raw bodies are never logged here.
    """
    url = f"{base}/v1/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
    if response_format is not None:
        payload["response_format"] = response_format

    connect = min(30.0, max(5.0, timeout_sec))
    httpx_timeout = httpx.Timeout(
        connect=connect,
        read=timeout_sec,
        write=min(60.0, max(10.0, connect)),
        pool=connect,
    )
    try:
        with httpx.Client(timeout=httpx_timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise GatewayCallError("UPSTREAM_TIMEOUT", f"Gateway request timed out: {exc}") from exc
    except httpx.RequestError as exc:
        raise GatewayCallError("UPSTREAM_UNAVAILABLE", f"Gateway connection failed: {exc}") from exc

    if resp.status_code >= 400:
        raise GatewayCallError(
            "UPSTREAM_REJECTED",
            f"Gateway HTTP {resp.status_code}",
            http_status=resp.status_code,
        )
    try:
        data = resp.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise GatewayCallError(
            "NON_STREAMING_UNSUPPORTED",
            "Gateway did not return a one-shot JSON completion body",
        ) from exc
    choices = data.get("choices") if isinstance(data, dict) else None
    if not choices or not isinstance(choices[0], dict):
        raise GatewayCallError("NON_STREAMING_UNSUPPORTED", "Gateway response had no choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise GatewayCallError("NON_STREAMING_UNSUPPORTED", "Gateway response had no message content")
    return content.strip()


def _artifact_openrouter_turn(
    messages: list[dict[str, Any]],
    *,
    builder_model: str | None,
    timeout_sec: float,
    diag: dict[str, Any],
) -> str:
    from src.llm_client import (
        complete_chat_messages_openrouter,
        normalized_openrouter_api_key,
        openrouter_api_key_is_plausible,
        resolve_openrouter_model_name_for_chat,
    )

    key = normalized_openrouter_api_key()
    if not key or not openrouter_api_key_is_plausible(key):
        raise GatewayCallError(
            "CONFIG_ERROR",
            "OPENROUTER_API_KEY is not set or not plausible for builder artifact mode.",
        )
    if builder_model:
        model_override = (
            builder_model
            if builder_model.startswith("openrouter/")
            else f"openrouter/{builder_model}"
        )
    else:
        model_override = resolve_openrouter_model_name_for_chat()
    # LiteLLM streaming has its own request timeout (no HAM SSE wall guard).
    diag["artifact_transport"] = "streaming"
    start = time.monotonic()
    try:
        text = complete_chat_messages_openrouter(
            messages,
            model_override=model_override,
            timeout_sec=timeout_sec,
            response_format=_ARTIFACT_RESPONSE_FORMAT,
        )
    except RuntimeError as exc:
        raise GatewayCallError("CONFIG_ERROR", str(exc)) from exc
    except Exception:
        # Capability fallback: retry once without the JSON-mode field.
        try:
            text = complete_chat_messages_openrouter(
                messages,
                model_override=model_override,
                timeout_sec=timeout_sec,
            )
        except RuntimeError as exc2:
            raise GatewayCallError("CONFIG_ERROR", str(exc2)) from exc2
        except Exception as exc2:
            raise GatewayCallError("UPSTREAM_REJECTED", str(exc2)) from exc2
        diag["elapsed_ms"] = round((time.monotonic() - start) * 1000.0, 1)
        diag["artifact_mode"] = "plain_adapter"
        diag["gateway_capability_detected"] = "response_format_unsupported"
        return text
    diag["elapsed_ms"] = round((time.monotonic() - start) * 1000.0, 1)
    diag["artifact_mode"] = "json_mode"
    diag["gateway_capability_detected"] = "response_format_supported"
    return text


def _artifact_http_turn(
    messages: list[dict[str, Any]],
    *,
    builder_model: str | None,
    timeout_sec: float,
    diag: dict[str, Any],
) -> str:
    base = (os.environ.get("HERMES_GATEWAY_BASE_URL") or "").strip().rstrip("/")
    if not base:
        raise GatewayCallError(
            "CONFIG_ERROR",
            "HERMES_GATEWAY_BASE_URL is required when HERMES_GATEWAY_MODE=http",
        )
    api_key = (os.environ.get("HERMES_GATEWAY_API_KEY") or "").strip()
    model = builder_model or (os.environ.get("HERMES_GATEWAY_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    budget = timeout_sec
    prefer_streaming = _artifact_prefer_streaming()

    def _collect(response_format: dict[str, Any] | None) -> str:
        # Prefer one non-streaming completion (no SSE wall/stall cap); fall back to
        # streaming with the artifact budget only if the gateway can't do stream=false.
        start = time.monotonic()
        try:
            if not prefer_streaming:
                diag["artifact_transport"] = "non_streaming"
                try:
                    return _http_chat_completion_blocking(
                        base=base,
                        api_key=api_key,
                        model=model,
                        messages=messages,
                        timeout_sec=budget,
                        response_format=response_format,
                    )
                except GatewayCallError as exc:
                    if exc.code != "NON_STREAMING_UNSUPPORTED":
                        raise
            diag["artifact_transport"] = "streaming"
            return "".join(
                _iter_http_chat_completions(
                    base=base,
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    timeout_sec=budget,
                    response_format=response_format,
                    stall_sec=budget,
                    max_wall_sec=budget,
                ),
            ).strip()
        finally:
            diag["elapsed_ms"] = round((time.monotonic() - start) * 1000.0, 1)

    diag["artifact_mode"] = "json_mode"
    try:
        text = _collect(_ARTIFACT_RESPONSE_FORMAT)
    except GatewayCallError as exc:
        # A 400/422 may mean the gateway does not accept the JSON-mode field; retry
        # once without it (capability fallback). Other failures propagate unchanged.
        if exc.http_status in {400, 422}:
            text = _collect(None)
            diag["artifact_mode"] = "plain_adapter"
            diag["gateway_capability_detected"] = "response_format_unsupported"
            return text
        raise
    diag["gateway_capability_detected"] = "response_format_supported"
    return text


def complete_artifact_turn(
    messages: list[dict[str, Any]],
    *,
    timeout_sec: float | None = None,
    diag: dict[str, Any] | None = None,
) -> str:
    """Private builder artifact channel — distinct from user-facing chat.

    Requests a strict JSON object (``response_format``) so the backend receives a
    parseable file artifact instead of conversational prose, optionally routed to a
    dedicated builder model/profile via ``HERMES_BUILDER_MODEL``. If the gateway
    rejects the JSON-mode field (HTTP 400/422), it retries once in plain mode
    (capability fallback). This is never used for conversational replies and the
    caller keeps the artifact private.

    Artifact mode prefers a single non-streaming completion with its own budget
    (``HERMES_ARTIFACT_TIMEOUT_SEC``), independent of the user-chat SSE guards, and
    only falls back to streaming if the gateway can't do ``stream: false`` (or when
    ``HERMES_ARTIFACT_STREAM`` opts in). This avoids ``STREAM_MAX_DURATION`` on large
    bundles while leaving conversational streaming untouched.

    ``diag`` (optional) is populated with non-sensitive routing facts for logging:
    ``artifact_mode`` (``json_mode``|``plain_adapter``|``mock``),
    ``artifact_transport`` (``non_streaming``|``streaming``|``mock``),
    ``gateway_capability_detected``, ``model_channel`` (``builder``|``default``), and
    ``elapsed_ms``. Raw model output and file contents are never written into ``diag``.
    """
    if not messages:
        raise GatewayCallError("INVALID_REQUEST", "messages must not be empty")

    sink = diag if diag is not None else {}
    budget = timeout_sec if timeout_sec is not None else _artifact_timeout_sec()
    builder_model = builder_artifact_model_override()
    sink["model_channel"] = "builder" if builder_model else "default"

    mode = _resolve_mode()
    if mode == "mock":
        sink["artifact_mode"] = "mock"
        sink["gateway_capability_detected"] = "mock"
        sink["artifact_transport"] = "mock"
        return _mock_assistant_text(messages)
    if mode == "openrouter":
        return _artifact_openrouter_turn(
            messages, builder_model=builder_model, timeout_sec=budget, diag=sink
        )
    return _artifact_http_turn(
        messages, builder_model=builder_model, timeout_sec=budget, diag=sink
    )
