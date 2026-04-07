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
    """Raw model id from env (e.g. anthropic/claude-3.5-sonnet)."""
    return os.getenv("DEFAULT_MODEL", "anthropic/claude-3.5-sonnet")


def resolve_openrouter_model_name() -> str:
    """Prefix with openrouter/ so LiteLLM uses OpenRouter, not native provider APIs."""
    raw = get_default_model().strip()
    if raw.startswith("openrouter/"):
        return raw
    return f"openrouter/{raw}"


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
    api_key = os.getenv("OPENROUTER_API_KEY")
    return _OpenRouterChatClient(model=model, api_key=api_key)


def configure_litellm_env() -> None:
    """Set env vars consumed by LiteLLM for OpenRouter routing."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if api_key:
        os.environ.setdefault("OPENROUTER_API_KEY", api_key)
