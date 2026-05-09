"""
LiteLLM / OpenRouter wiring for Ham (model-agnostic chat completions).

`DEFAULT_MODEL` may be listed as `anthropic/...` (OpenRouter model id); we
normalize to `openrouter/<provider/model>` so LiteLLM routes via OpenRouter's
OpenAI-compatible API.
"""
from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()


def get_openrouter_base_url() -> str:
    """OpenRouter-compatible API base; override via env if needed."""
    return os.getenv("OPENROUTER_API_URL", "https://openrouter.ai/api/v1")


def get_default_model() -> str:
    """Raw model id from env (OpenRouter slug, e.g. minimax/minimax-m2.5:free)."""
    # Default must be a model that stays routable on OpenRouter; older Claude
    # slugs often 404 when renamed/retired.
    return os.getenv("DEFAULT_MODEL", "minimax/minimax-m2.5:free")


def resolve_openrouter_model_name() -> str:
    """Prefix with openrouter/ so LiteLLM uses OpenRouter, not native provider APIs."""
    raw = get_default_model().strip()
    if raw.startswith("openrouter/"):
        return raw
    return f"openrouter/{raw}"


def normalized_openrouter_api_key() -> str:
    """Effective OpenRouter key: workspace-stored credential wins, else env (may be empty)."""
    try:
        from src.persistence.workspace_tool_credentials import (
            get_effective_openrouter_api_key,
        )

        return get_effective_openrouter_api_key()
    except ImportError:
        return (os.getenv("OPENROUTER_API_KEY") or "").strip()


def openrouter_api_key_is_plausible(raw: str | None = None) -> bool:
    """
    Heuristic: value should be a single-line token for OpenRouter/LiteLLM (not shell paste noise).

    Rejects common Secret Manager accidents: newlines, a leading ``Bearer `` prefix, or embedded
    command snippets. Real OpenRouter keys normally start with ``sk-or-`` and are long; generic
    high-entropy tokens are accepted when length and charset look reasonable.
    """
    k = normalized_openrouter_api_key() if raw is None else (raw or "").strip()
    if not k:
        return False
    if any(c in k for c in "\n\r\t"):
        return False
    kl = k.lower()
    if kl.startswith("bearer "):
        return False
    for needle in ("echo ", "export ", "gcloud ", "curl ", "printf ", "$(", "${"):
        if needle in kl:
            return False
    if k.startswith("sk-or-"):
        return len(k) >= 24
    if all(c.isalnum() or c in "_-" for c in k) and 32 <= len(k) <= 256:
        return True
    return False


def resolve_openrouter_model_name_for_chat() -> str:
    """
    Model for dashboard/API chat when using OpenRouter.

    Uses `HERMES_GATEWAY_MODEL` if set (OpenRouter slug, e.g. minimax/minimax-m2.5:free),
    otherwise `DEFAULT_MODEL` via `resolve_openrouter_model_name()`.
    """
    override = (os.environ.get("HERMES_GATEWAY_MODEL") or "").strip()
    if not override:
        return resolve_openrouter_model_name()
    if override.startswith("openrouter/"):
        return override
    return f"openrouter/{override}"


def complete_chat_messages_openrouter(
    messages: list[dict[str, Any]],
    *,
    model_override: str | None = None,
    api_key_override: str | None = None,
) -> str:
    """
    Multi-turn chat completion via OpenRouter (LiteLLM).

    Requires ``OPENROUTER_API_KEY``. Uses ``OPENROUTER_API_URL`` (default OpenRouter v1),
    optional ``OPENROUTER_HTTP_REFERER`` / ``OPENROUTER_APP_TITLE`` headers.

    ``model_override`` must be a LiteLLM-ready id (e.g. ``openrouter/minimax/minimax-m2.5:free``).
    """
    return "".join(
        stream_chat_messages_openrouter(
            messages,
            model_override=model_override,
            api_key_override=api_key_override,
        ),
    ).strip()


def stream_chat_messages_openrouter(
    messages: list[dict[str, Any]],
    *,
    model_override: str | None = None,
    api_key_override: str | None = None,
):
    """Streaming chat completion via OpenRouter (LiteLLM). Yields content deltas (str)."""
    import litellm

    if not messages:
        raise ValueError("messages must not be empty")

    configure_litellm_env()
    raw_override = (api_key_override or "").strip()
    api_key = raw_override if raw_override else normalized_openrouter_api_key()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    if not openrouter_api_key_is_plausible(api_key):
        raise RuntimeError(
            "OPENROUTER_API_KEY is set but is not a plausible raw API token "
            "(expected one line only: no shell commands, no 'Bearer ' prefix, no newlines). "
            "Fix the Secret Manager value and redeploy Cloud Run."
        )

    model = (model_override or "").strip() or resolve_openrouter_model_name_for_chat()
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "api_base": get_openrouter_base_url(),
        "api_key": api_key,
        "stream": True,
    }
    extra_headers: dict[str, str] = {}
    ref = os.getenv("OPENROUTER_HTTP_REFERER")
    ttl = os.getenv("OPENROUTER_APP_TITLE")
    if ref:
        extra_headers["HTTP-Referer"] = ref
    if ttl:
        extra_headers["X-Title"] = ttl
    if extra_headers:
        kwargs["extra_headers"] = extra_headers

    stream = litellm.completion(**kwargs)
    for chunk in stream:
        try:
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue
            ch0 = choices[0]
            delta = getattr(ch0, "delta", None)
            if delta is None:
                continue
            content = getattr(delta, "content", None)
            if content:
                yield str(content)
        except (IndexError, AttributeError, TypeError):
            continue


class _OpenRouterChatClient:
    """Thin adapter: .call(prompt) / invoke / callable — matches hermes reviewer usage."""

    def __init__(self, *, model: str, api_key: str | None) -> None:
        self._model = model
        self._api_key = api_key

    def call(self, prompt: str) -> str:
        import litellm

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "api_base": get_openrouter_base_url(),
        }
        if self._api_key:
            kwargs["api_key"] = self._api_key
        extra_headers: dict[str, str] = {}
        ref = os.getenv("OPENROUTER_HTTP_REFERER")
        ttl = os.getenv("OPENROUTER_APP_TITLE")
        if ref:
            extra_headers["HTTP-Referer"] = ref
        if ttl:
            extra_headers["X-Title"] = ttl
        if extra_headers:
            kwargs["extra_headers"] = extra_headers
        resp = litellm.completion(**kwargs)
        msg = resp.choices[0].message
        content = getattr(msg, "content", None)
        return content if isinstance(content, str) else str(content or "")

    def invoke(self, prompt: str) -> str:
        return self.call(prompt)

    def __call__(self, prompt: str) -> str:
        return self.call(prompt)


def get_llm_client() -> _OpenRouterChatClient:
    """Return a LiteLLM-backed client for OpenRouter (BYOK via OPENROUTER_API_KEY)."""
    configure_litellm_env()
    model = resolve_openrouter_model_name()
    api_key = normalized_openrouter_api_key() or None
    if api_key and not openrouter_api_key_is_plausible(api_key):
        raise RuntimeError(
            "OPENROUTER_API_KEY is set but is not a plausible raw API token "
            "(one line only; no shell/Bearer noise). Fix Secret Manager and redeploy."
        )
    return _OpenRouterChatClient(model=model, api_key=api_key)


def configure_litellm_env() -> None:
    """Set env vars consumed by LiteLLM for OpenRouter routing."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if api_key:
        os.environ.setdefault("OPENROUTER_API_KEY", api_key)
    # LiteLLM OpenRouter paths also read OR_SITE_URL / OR_APP_NAME for headers.
    referer = os.getenv("OPENROUTER_HTTP_REFERER")
    title = os.getenv("OPENROUTER_APP_TITLE")
    if referer:
        os.environ.setdefault("OR_SITE_URL", referer)
    if title:
        os.environ.setdefault("OR_APP_NAME", title)
