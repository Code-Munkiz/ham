"""HTTP validation for workspace tool API keys (no logging of secrets)."""

from __future__ import annotations

import httpx

from src.llm_client import get_openrouter_base_url, openrouter_api_key_is_plausible


def validate_openrouter_api_key(api_key: str) -> bool:
    k = (api_key or "").strip()
    if not openrouter_api_key_is_plausible(k):
        return False
    base = get_openrouter_base_url().rstrip("/")
    try:
        r = httpx.get(
            f"{base}/models",
            headers={"Authorization": f"Bearer {k}"},
            timeout=20.0,
        )
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def validate_github_token(token: str) -> bool:
    t = (token or "").strip()
    if not t or any(c in t for c in "\n\r\t"):
        return False
    try:
        r = httpx.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {t}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=20.0,
        )
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def validate_anthropic_api_key(api_key: str) -> bool:
    k = (api_key or "").strip()
    if not k.startswith("sk-ant-") or len(k) < 24:
        return False
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": k,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-3-5-haiku-20241022",
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "ok"}],
            },
            timeout=25.0,
        )
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def validate_cursor_api_key_plausible(api_key: str) -> bool:
    k = (api_key or "").strip()
    if len(k) < 12 or any(c in k for c in "\n\r\t"):
        return False
    return True


def validate_cursor_api_key(api_key: str) -> bool:
    k = (api_key or "").strip()
    if not validate_cursor_api_key_plausible(k):
        return False
    try:
        r = httpx.get(
            "https://api.cursor.com/v0/me",
            auth=(k, ""),
            timeout=25.0,
        )
        return r.status_code == 200
    except httpx.HTTPError:
        return False
