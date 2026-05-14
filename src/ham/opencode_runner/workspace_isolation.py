"""Per-run XDG isolation for ``opencode serve``.

The :func:`build_isolated_env` helper assembles the env mapping passed to
the spawned server. Every secret stays in the returned mapping; we never
log, echo, or otherwise emit env values from this module.

Auth credential resolution lives here too: HAM resolves provider creds at
launch time and writes them into the returned mapping under the standard
``OPENROUTER_API_KEY`` / ``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY`` /
``GROQ_API_KEY`` names so the inline OpenCode config can pick them up via
``{env:VAR}`` substitution. Callers may additionally inject creds at
runtime via ``PUT /auth/:id`` once the server is healthy.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import socket
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_LOG = logging.getLogger(__name__)

_AUTH_ENV_NAMES: tuple[str, ...] = (
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GROQ_API_KEY",
)


@dataclass(frozen=True)
class IsolatedServeEnv:
    """The fully-assembled per-run environment for ``opencode serve``."""

    env: Mapping[str, str]
    host: str
    port: int
    password: str
    xdg_data_home: Path
    xdg_config_home: Path

    def auth_present(self) -> bool:
        for name in _AUTH_ENV_NAMES:
            if (self.env.get(name) or "").strip():
                return True
        return False

    def basic_auth(self) -> tuple[str, str]:
        return ("opencode", self.password)


def _choose_ephemeral_port(host: str = "127.0.0.1") -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, 0))
        return int(s.getsockname()[1])
    finally:
        s.close()


def _default_permission_policy() -> dict[str, Any]:
    """The deny-by-default OpenCode permission tree for HAM-side missions."""
    return {
        "bash": "deny",
        "edit": "ask",
        "read": "allow",
        "glob": "allow",
        "grep": "allow",
        "list": "allow",
        "lsp": "allow",
        "todowrite": "allow",
        "task": "deny",
        "external_directory": "deny",
        "skill": "ask",
        "webfetch": "deny",
        "websearch": "deny",
    }


def _default_provider_config() -> dict[str, Any]:
    """A minimal config that lets OpenCode pick up an env-resolved key.

    OpenCode supports ``{env:VAR}`` substitution inside the inline JSON
    config; we point each provider at its standard env-var name so HAM
    never has to embed the actual secret in the config blob.
    """
    return {
        "provider": {
            "openrouter": {"options": {"apiKey": "{env:OPENROUTER_API_KEY}"}},
            "anthropic": {"options": {"apiKey": "{env:ANTHROPIC_API_KEY}"}},
            "openai": {"options": {"apiKey": "{env:OPENAI_API_KEY}"}},
            "groq": {"options": {"apiKey": "{env:GROQ_API_KEY}"}},
        }
    }


def _resolve_auth_env(
    base_env: Mapping[str, str] | None,
    actor_creds: Mapping[str, str] | None,
) -> dict[str, str]:
    """Return only the auth env names that have a non-empty value.

    Per-actor BYOK credentials (from Connected Tools) take precedence
    over backend env fallbacks. Values flow through the returned dict
    only — they are never logged or returned via any other path.
    """
    source: Mapping[str, str] = base_env if base_env is not None else os.environ
    resolved: dict[str, str] = {}
    for name in _AUTH_ENV_NAMES:
        if actor_creds and (actor_creds.get(name) or "").strip():
            resolved[name] = str(actor_creds[name]).strip()
            continue
        val = (source.get(name) or "").strip()
        if val:
            resolved[name] = val
    return resolved


def build_isolated_env(
    *,
    project_root: Path,
    base_env: Mapping[str, str] | None = None,
    actor_creds: Mapping[str, str] | None = None,
    host: str = "127.0.0.1",
    port: int | None = None,
    extra_config: Mapping[str, Any] | None = None,
    extra_permissions: Mapping[str, Any] | None = None,
) -> IsolatedServeEnv:
    """Assemble the per-run env for ``opencode serve``.

    The returned :class:`IsolatedServeEnv` includes XDG temp dirs we own
    and a freshly-minted Basic-Auth password. Callers are responsible
    for tearing down ``xdg_data_home`` / ``xdg_config_home`` once the
    subprocess has exited.
    """
    del project_root

    chosen_port = port if port is not None else _choose_ephemeral_port(host)
    password = secrets.token_urlsafe(32)

    xdg_data_home = Path(tempfile.mkdtemp(prefix="ham-opencode-data-"))
    xdg_config_home = Path(tempfile.mkdtemp(prefix="ham-opencode-config-"))

    config_body = _default_provider_config()
    if extra_config:
        config_body.update(dict(extra_config))

    permissions_body = _default_permission_policy()
    if extra_permissions:
        permissions_body.update(dict(extra_permissions))

    env: dict[str, str] = {}
    parent = dict(base_env) if base_env is not None else dict(os.environ)
    for key in ("PATH", "HOME", "USER", "LANG", "LC_ALL", "TERM"):
        if key in parent:
            env[key] = parent[key]

    env["XDG_DATA_HOME"] = str(xdg_data_home)
    env["XDG_CONFIG_HOME"] = str(xdg_config_home)
    env["OPENCODE_SERVER_PASSWORD"] = password
    env["OPENCODE_CONFIG_CONTENT"] = json.dumps(config_body, separators=(",", ":"))
    env["OPENCODE_PERMISSION"] = json.dumps(permissions_body, separators=(",", ":"))
    env["OPENCODE_DISABLE_AUTOUPDATE"] = "1"

    env.update(_resolve_auth_env(base_env, actor_creds))

    _LOG.info(
        "opencode_runner.build_isolated_env host=%s port=%s auth_present=%s",
        host,
        chosen_port,
        any(env.get(n) for n in _AUTH_ENV_NAMES),
    )

    return IsolatedServeEnv(
        env=env,
        host=host,
        port=chosen_port,
        password=password,
        xdg_data_home=xdg_data_home,
        xdg_config_home=xdg_config_home,
    )


__all__ = [
    "IsolatedServeEnv",
    "build_isolated_env",
]
