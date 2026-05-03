"""Claude Agent SDK worker adapter — readiness shell only (MVP).

Detects whether the optional ``claude-agent-sdk`` package is importable and
whether one of its supported auth modes appears configured (presence-only;
values are never read or returned). Does NOT launch a real agent and does
NOT call ``claude_agent_sdk.query()``.

Mirrors the surface and conventions of ``cursor_adapter`` in this package.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

# Module-level cache for the SDK import probe. The /api/workspace/tools
# endpoint rebuilds the registry on every request; importing the SDK each
# time would be wasteful. Reset via ``reset_claude_agent_readiness_cache``.
_SDK_DETECTION: tuple[bool, str | None] | None = None


@dataclass(frozen=True)
class ClaudeAgentWorkerCapabilities:
    """Capabilities the Claude Agent worker can provide when ready."""

    can_plan: bool = True
    can_edit_code: bool = True
    can_run_tests: bool = True
    can_open_pr: bool = False
    requires_project_root: bool = True
    requires_auth: bool = True
    launch_mode: Literal["sdk_local"] = "sdk_local"


@dataclass
class ClaudeAgentWorkerReadiness:
    """Current readiness state of the Claude Agent worker."""

    authenticated: bool = False
    sdk_available: bool = False
    sdk_version: str | None = None
    status: Literal["ready", "needs_sign_in", "unavailable"] = "unavailable"
    capabilities: ClaudeAgentWorkerCapabilities = field(
        default_factory=ClaudeAgentWorkerCapabilities
    )
    reason: str | None = None


def _do_import() -> tuple[bool, str | None]:
    """Attempt the SDK import. Isolated so tests can patch it cheaply.

    Returns ``(available, version)``. Any failure is swallowed.
    """
    try:
        import claude_agent_sdk  # type: ignore[import-not-found]

        version = getattr(claude_agent_sdk, "__version__", None)
        return (True, version)
    except ImportError:
        return (False, None)
    except Exception:
        # Defensive: never let an exotic import-time error break readiness.
        return (False, None)


def _detect_sdk() -> tuple[bool, str | None]:
    """Cached SDK detection. Subsequent calls reuse the first result."""
    global _SDK_DETECTION
    if _SDK_DETECTION is not None:
        return _SDK_DETECTION
    _SDK_DETECTION = _do_import()
    return _SDK_DETECTION


def reset_claude_agent_readiness_cache() -> None:
    """Clear the cached SDK detection so the next call re-imports.

    Wired to the workspace tools scan endpoint so a user who installs the
    SDK and clicks "Scan again" sees the change without a server restart.
    """
    global _SDK_DETECTION
    _SDK_DETECTION = None


def _has_anthropic_api_key() -> bool:
    return bool((os.environ.get("ANTHROPIC_API_KEY") or "").strip())


def _has_bedrock_signal() -> bool:
    """Bedrock auth requires the flag AND a region (per official docs)."""
    flag = (os.environ.get("CLAUDE_CODE_USE_BEDROCK") or "").strip()
    if flag != "1":
        return False
    region = (
        os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or ""
    ).strip()
    return bool(region)


def _has_vertex_signal() -> bool:
    """Vertex auth requires the flag AND a project id (per official docs).

    GCLOUD_PROJECT and GOOGLE_CLOUD_PROJECT are accepted as fallbacks per
    Google's standard ADC chain that the SDK piggybacks on.
    """
    flag = (os.environ.get("CLAUDE_CODE_USE_VERTEX") or "").strip()
    if flag != "1":
        return False
    project = (
        os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID")
        or os.environ.get("GCLOUD_PROJECT")
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or ""
    ).strip()
    return bool(project)


def _has_any_auth_signal() -> bool:
    """Presence-only auth check across the three supported SDK modes.

    Never reads or returns the underlying values. Returns only a boolean,
    and never reveals which mode succeeded.
    """
    try:
        return (
            _has_anthropic_api_key() or _has_bedrock_signal() or _has_vertex_signal()
        )
    except Exception:
        return False


def check_claude_agent_readiness() -> ClaudeAgentWorkerReadiness:
    """Check whether the Claude Agent worker is ready (SDK + auth signal).

    Performs only local checks: an optional import probe and presence-only
    env-var inspection. Does NOT launch an agent or make external calls.
    """
    caps = ClaudeAgentWorkerCapabilities()

    try:
        sdk_available, sdk_version = _detect_sdk()
    except Exception:
        return ClaudeAgentWorkerReadiness(
            authenticated=False,
            sdk_available=False,
            sdk_version=None,
            status="unavailable",
            capabilities=caps,
            reason="Claude Agent SDK detection raised unexpectedly.",
        )

    if not sdk_available:
        return ClaudeAgentWorkerReadiness(
            authenticated=False,
            sdk_available=False,
            sdk_version=None,
            status="unavailable",
            capabilities=caps,
            reason="claude-agent-sdk is not installed on this server.",
        )

    if not _has_any_auth_signal():
        return ClaudeAgentWorkerReadiness(
            authenticated=False,
            sdk_available=True,
            sdk_version=sdk_version,
            status="needs_sign_in",
            capabilities=caps,
            reason="No Claude auth signal detected (ANTHROPIC_API_KEY, Bedrock, or Vertex).",
        )

    return ClaudeAgentWorkerReadiness(
        authenticated=True,
        sdk_available=True,
        sdk_version=sdk_version,
        status="ready",
        capabilities=caps,
        reason=None,
    )


def is_claude_agent_launchable(
    readiness: ClaudeAgentWorkerReadiness | None = None,
) -> bool:
    """Whether the Claude Agent worker would be launchable.

    In this MVP, even a 'ready' worker does NOT actually launch.
    This is a policy gate for future use.
    """
    if readiness is None:
        readiness = check_claude_agent_readiness()
    return readiness.authenticated and readiness.status == "ready"
