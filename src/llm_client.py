"""
LiteLLM / OpenRouter wiring for CrewAI.

`DEFAULT_MODEL` may be listed as `anthropic/...` (OpenRouter model id); CrewAI expects
`openrouter/<provider/model>` so we normalize before constructing `LLM`.
"""
import os
from typing import Any

from crewai import LLM
from dotenv import load_dotenv

load_dotenv()


def get_openrouter_base_url() -> str:
    """OpenRouter-compatible API base; override via env if needed."""
    return os.getenv("OPENROUTER_API_URL", "https://openrouter.ai/api/v1")


def get_default_model() -> str:
    """Raw model id from env (e.g. anthropic/claude-3.5-sonnet)."""
    return os.getenv("DEFAULT_MODEL", "anthropic/claude-3.5-sonnet")


def resolve_crew_model_name() -> str:
    """Prefix with openrouter/ so Crew routes to OpenAI-compatible OpenRouter, not native Anthropic."""
    raw = get_default_model().strip()
    if raw.startswith("openrouter/"):
        return raw
    return f"openrouter/{raw}"


def get_crew_llm() -> LLM:
    """Configured CrewAI LLM for OpenRouter (BYOK via OPENROUTER_API_KEY)."""
    configure_litellm_env()
    model = resolve_crew_model_name()
    api_key = os.getenv("OPENROUTER_API_KEY")
    kwargs: dict[str, Any] = {}
    if api_key:
        kwargs["api_key"] = api_key
    return LLM(model=model, **kwargs)


def configure_litellm_env() -> None:
    """Set env vars consumed by LiteLLM for OpenRouter routing (placeholder)."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if api_key:
        os.environ.setdefault("OPENROUTER_API_KEY", api_key)
