"""Claude Agent SDK worker adapter — readiness + optional controlled smoke.

Detects whether the optional ``claude-agent-sdk`` package is importable and
whether one of its supported auth modes appears configured (presence-only;
values are never read or returned).

Controlled smoke (``run_claude_agent_sdk_smoke``) calls ``query()`` with
**no tools**, ``permission_mode='plan'``, ``max_turns=1`` — only when invoked
from an explicitly feature-gated HTTP route. Not used by readiness checks.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Literal

CLAUDE_AGENT_SMOKE_PROMPT = "Reply with exactly: HAM_CLAUDE_SMOKE_OK"
SMOKE_QUERY_TIMEOUT_SEC = 60.0
_RESPONSE_TEXT_CAP = 500

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


def _truthy_env(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def claude_agent_smoke_feature_enabled() -> bool:
    """``HAM_CLAUDE_AGENT_SMOKE_ENABLED`` gate for the HTTP smoke route."""
    return _truthy_env("HAM_CLAUDE_AGENT_SMOKE_ENABLED")


def claude_agent_smoke_route_armed() -> bool:
    """Feature on AND (Clerk session mode OR a non-empty ``HAM_CLAUDE_AGENT_SMOKE_TOKEN``)."""
    if not claude_agent_smoke_feature_enabled():
        return False
    try:
        from src.ham.clerk_auth import clerk_authorization_is_clerk_session
    except Exception:
        return False
    if clerk_authorization_is_clerk_session():
        return True
    return bool((os.environ.get("HAM_CLAUDE_AGENT_SMOKE_TOKEN") or "").strip())


def claude_agent_coarse_provider() -> str:
    """Coarse auth channel label for logs/responses — never values."""
    if _has_anthropic_api_key():
        return "anthropic_direct"
    if _has_bedrock_signal():
        return "bedrock"
    if _has_vertex_signal():
        return "vertex"
    return "unknown"


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


def _text_from_sdk_message(msg: object) -> str:
    """Best-effort text extraction without importing SDK message types."""
    chunks: list[str] = []
    content = getattr(msg, "content", None)
    if not content:
        return ""
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            chunks.append(text)
    return "".join(chunks)


def _sanitize_smoke_response_text(raw: str) -> str:
    s = " ".join(raw.split())
    if len(s) > _RESPONSE_TEXT_CAP:
        return s[:_RESPONSE_TEXT_CAP].rstrip() + "…"
    return s


@dataclass(frozen=True)
class ClaudeAgentSmokeResult:
    """Structured smoke outcome — never includes secrets or env dumps."""

    status: Literal["ok", "error"]
    provider: str
    sdk_available: bool
    authenticated: bool
    smoke_ok: bool
    response_text: str
    blocker: str | None = None


async def run_claude_agent_sdk_smoke() -> ClaudeAgentSmokeResult:
    """One harmless SDK ``query`` with tools disabled and plan-only permissions.

    Uses server-side auth already present in the environment. Does not pass
    project files, user prompts, or tool allowlists beyond empty/disabled tools.
    """
    readiness = check_claude_agent_readiness()
    provider = claude_agent_coarse_provider()
    if readiness.status != "ready":
        return ClaudeAgentSmokeResult(
            status="error",
            provider=provider,
            sdk_available=readiness.sdk_available,
            authenticated=readiness.authenticated,
            smoke_ok=False,
            response_text="",
            blocker=readiness.reason or "Claude Agent SDK is not ready on this server.",
        )

    try:
        from claude_agent_sdk import ClaudeAgentOptions, query  # type: ignore[import-not-found]
    except ImportError:
        return ClaudeAgentSmokeResult(
            status="error",
            provider=provider,
            sdk_available=readiness.sdk_available,
            authenticated=readiness.authenticated,
            smoke_ok=False,
            response_text="",
            blocker="claude-agent-sdk import failed or package not installed.",
        )

    opts = ClaudeAgentOptions(
        tools=[],
        allowed_tools=[],
        permission_mode="plan",
        max_turns=1,
    )

    async def _collect() -> str:
        parts: list[str] = []
        async for msg in query(prompt=CLAUDE_AGENT_SMOKE_PROMPT, options=opts):
            parts.append(_text_from_sdk_message(msg))
        return "".join(parts).strip()

    try:
        combined = await asyncio.wait_for(_collect(), timeout=SMOKE_QUERY_TIMEOUT_SEC)
    except TimeoutError:
        return ClaudeAgentSmokeResult(
            status="error",
            provider=provider,
            sdk_available=readiness.sdk_available,
            authenticated=readiness.authenticated,
            smoke_ok=False,
            response_text="",
            blocker="Smoke query timed out.",
        )
    except Exception as exc:
        return ClaudeAgentSmokeResult(
            status="error",
            provider=provider,
            sdk_available=readiness.sdk_available,
            authenticated=readiness.authenticated,
            smoke_ok=False,
            response_text="",
            blocker=f"Smoke query failed: {type(exc).__name__}",
        )

    safe_text = _sanitize_smoke_response_text(combined)
    smoke_ok = "HAM_CLAUDE_SMOKE_OK" in safe_text
    return ClaudeAgentSmokeResult(
        status="ok" if smoke_ok else "error",
        provider=provider,
        sdk_available=readiness.sdk_available,
        authenticated=readiness.authenticated,
        smoke_ok=smoke_ok,
        response_text=safe_text,
        blocker=None if smoke_ok else "Model reply did not contain the expected smoke token.",
    )
