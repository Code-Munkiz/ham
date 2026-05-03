"""Claude Agent SDK worker adapter — readiness + optional controlled smoke.

Detects whether the optional ``claude-agent-sdk`` package is importable and
whether one of its supported auth modes appears configured (presence-only;
values are never read or returned).

Controlled smoke (``run_claude_agent_sdk_smoke``) and the bounded mission
runner (``run_claude_agent_sdk_mission``) call ``query()`` with **no tools**,
``permission_mode='plan'``, ``max_turns=1`` — only from feature-gated HTTP routes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from typing import Any, Literal

CLAUDE_AGENT_SMOKE_PROMPT = "Reply with exactly: HAM_CLAUDE_SMOKE_OK"
SMOKE_QUERY_TIMEOUT_SEC = 60.0
MISSION_QUERY_TIMEOUT_SEC = 90.0
_RESPONSE_TEXT_CAP = 500
_MISSION_RESPONSE_CAP = 4000
_DIAG_STDERR_LINE_CAP = 48
_DIAG_STDERR_JOIN_CAP = 900

_LOG = logging.getLogger(__name__)

CLAUDE_AGENT_MISSION_PROMPT = """Review this HAM mission brief and return a JSON object with:
- mission_status: ok
- worker: claude_agent_sdk
- job_type: non_mutating_review
- summary: one sentence
- acceptance_criteria: exactly three short bullets
Do not request tools. Do not edit files."""

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
    if _anthropic_direct_key_present():
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


def _workspace_stored_anthropic_key_present() -> bool:
    """True if the Connected Tools file store holds an Anthropic key (server-side MVP)."""
    try:
        from src.persistence.workspace_tool_credentials import (
            get_stored_anthropic_api_key,
        )

        return bool(get_stored_anthropic_api_key())
    except Exception:
        return False


def _anthropic_direct_key_present() -> bool:
    """Anthropic direct auth: env key or workspace-stored user key."""
    return _has_anthropic_api_key() or _workspace_stored_anthropic_key_present()


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
            _anthropic_direct_key_present() or _has_bedrock_signal() or _has_vertex_signal()
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


_SECRETISH = re.compile(
    r"(sk-ant-|sk-or-v1-|sk_live_|sk_test_|ghp_|HAM_CLAUDE_AGENT_SMOKE_TOKEN|ANTHROPIC_API_KEY)",
    re.I,
)


def _redact_diagnostic_text(raw: str, cap: int = _DIAG_STDERR_JOIN_CAP) -> str:
    """Redact likely secrets and cap length for logs/API blocker text."""
    redacted = _SECRETISH.sub("[REDACTED]", raw)
    redacted = " ".join(redacted.split())
    if len(redacted) > cap:
        return redacted[:cap].rstrip() + "…"
    return redacted


def _format_sdk_query_failure(exc: BaseException, stderr_lines: list[str]) -> str:
    """Human-readable failure detail; stderr only appears when options.stderr is wired."""
    msg = _redact_diagnostic_text(str(exc).strip(), cap=700)
    if not stderr_lines:
        return msg
    tail = stderr_lines[-_DIAG_STDERR_LINE_CAP :]
    stderr_blob = _redact_diagnostic_text("\n".join(tail), cap=_DIAG_STDERR_JOIN_CAP)
    return f"{msg} | stderr: {stderr_blob}"


def _sanitize_capped_response_text(raw: str, cap: int) -> str:
    s = " ".join(raw.split())
    if len(s) > cap:
        return s[:cap].rstrip() + "…"
    return s


def _sanitize_smoke_response_text(raw: str) -> str:
    return _sanitize_capped_response_text(raw, _RESPONSE_TEXT_CAP)


def _ham_preferred_cli_path() -> str | None:
    """Prefer npm/system ``claude`` when installed (bundled wheel binary can fail on slim Linux)."""
    return shutil.which("claude")


def _plan_mode_query_options(stderr_lines: list[str]) -> Any:
    from claude_agent_sdk import ClaudeAgentOptions  # type: ignore[import-not-found]

    def _stderr_cb(line: str) -> None:
        stderr_lines.append(line)
        while len(stderr_lines) > _DIAG_STDERR_LINE_CAP:
            stderr_lines.pop(0)

    kwargs: dict[str, Any] = {
        "tools": [],
        "allowed_tools": [],
        "permission_mode": "plan",
        "max_turns": 1,
        "stderr": _stderr_cb,
    }
    cli = _ham_preferred_cli_path()
    if cli:
        kwargs["cli_path"] = cli
    return ClaudeAgentOptions(**kwargs)


async def _run_claude_agent_sdk_plan_query(
    prompt: str,
    timeout_sec: float,
    response_cap: int,
) -> tuple[str | None, str | None, ClaudeAgentWorkerReadiness]:
    """Execute one bounded plan-mode SDK query.

    Returns ``(sanitized_text, blocker, readiness_snapshot)``.
    """
    readiness = check_claude_agent_readiness()
    if readiness.status != "ready":
        return (
            None,
            readiness.reason or "Claude Agent SDK is not ready on this server.",
            readiness,
        )
    try:
        from claude_agent_sdk import query  # type: ignore[import-not-found]
    except ImportError:
        return (
            None,
            "claude-agent-sdk import failed or package not installed.",
            readiness,
        )

    stderr_lines: list[str] = []
    opts = _plan_mode_query_options(stderr_lines)

    async def _collect() -> str:
        parts: list[str] = []
        async for msg in query(prompt=prompt, options=opts):
            parts.append(_text_from_sdk_message(msg))
        return "".join(parts).strip()

    try:
        combined = await asyncio.wait_for(_collect(), timeout=timeout_sec)
    except TimeoutError:
        return None, "Claude Agent SDK query timed out.", readiness
    except Exception as exc:
        detail = _format_sdk_query_failure(exc, stderr_lines)
        _LOG.warning("claude_agent_sdk query failed: %s", detail)
        return None, f"Claude Agent SDK query failed: {detail}", readiness

    return _sanitize_capped_response_text(combined, response_cap), None, readiness


def _strip_json_fence(raw: str) -> str:
    t = raw.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


def _primitive_is_safe(val: Any) -> bool:
    if isinstance(val, bool):
        return True
    if isinstance(val, int | float) and not isinstance(val, bool):
        return True
    if isinstance(val, str):
        return _SECRETISH.search(val) is None
    if isinstance(val, list):
        return all(isinstance(x, str) and _SECRETISH.search(x) is None for x in val)
    return False


def _safe_mission_parsed_subset(obj: dict[str, Any]) -> dict[str, Any] | None:
    allowed_keys = (
        "mission_status",
        "worker",
        "job_type",
        "summary",
        "acceptance_criteria",
    )
    out: dict[str, Any] = {}
    for k in allowed_keys:
        if k not in obj:
            continue
        v = obj[k]
        if not _primitive_is_safe(v):
            continue
        out[k] = v
    return out or None


def _parse_mission_json(text: str) -> tuple[dict[str, Any] | None, bool]:
    """Returns ``(parsed_subset_or_none, mission_ok)``."""
    stripped = _strip_json_fence(text)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return None, False
    if not isinstance(data, dict):
        return None, False
    summary = data.get("summary")
    ac = data.get("acceptance_criteria")
    ac_ok = (
        isinstance(ac, list)
        and len(ac) == 3
        and all(isinstance(x, str) and x.strip() for x in ac)
    )
    mission_ok = (
        data.get("mission_status") == "ok"
        and data.get("worker") == "claude_agent_sdk"
        and data.get("job_type") == "non_mutating_review"
        and isinstance(summary, str)
        and bool(summary.strip())
        and ac_ok
    )
    safe = _safe_mission_parsed_subset(data)
    return safe, bool(mission_ok and safe)


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


@dataclass(frozen=True)
class ClaudeAgentMissionResult:
    """Bounded mission outcome — no secrets."""

    ok: bool
    mission_ok: bool
    worker: str
    mission_type: str
    result_text: str
    parsed_result: dict[str, Any] | None
    duration_ms: int
    safety_mode: str
    blocker: str | None = None


async def run_claude_agent_sdk_smoke() -> ClaudeAgentSmokeResult:
    """One harmless SDK ``query`` with tools disabled and plan-only permissions.

    Uses server-side auth already present in the environment. Does not pass
    project files, user prompts, or tool allowlists beyond empty/disabled tools.
    """
    readiness = check_claude_agent_readiness()
    provider = claude_agent_coarse_provider()
    combined, blocker, rd = await _run_claude_agent_sdk_plan_query(
        CLAUDE_AGENT_SMOKE_PROMPT,
        SMOKE_QUERY_TIMEOUT_SEC,
        _RESPONSE_TEXT_CAP,
    )
    if blocker or combined is None:
        return ClaudeAgentSmokeResult(
            status="error",
            provider=provider,
            sdk_available=rd.sdk_available,
            authenticated=rd.authenticated,
            smoke_ok=False,
            response_text="",
            blocker=blocker or "Claude Agent SDK query produced no text.",
        )

    smoke_ok = "HAM_CLAUDE_SMOKE_OK" in combined
    return ClaudeAgentSmokeResult(
        status="ok" if smoke_ok else "error",
        provider=provider,
        sdk_available=rd.sdk_available,
        authenticated=rd.authenticated,
        smoke_ok=smoke_ok,
        response_text=combined,
        blocker=None if smoke_ok else "Model reply did not contain the expected smoke token.",
    )


async def run_claude_agent_sdk_mission() -> ClaudeAgentMissionResult:
    """Fixed HAM mission brief — plan mode, no tools, bounded turns/time."""
    t0 = time.monotonic()
    worker = "claude_agent_sdk"
    mission_type = "non_mutating_review"
    safety_mode = "plan"

    combined, blocker, rd = await _run_claude_agent_sdk_plan_query(
        CLAUDE_AGENT_MISSION_PROMPT,
        MISSION_QUERY_TIMEOUT_SEC,
        _MISSION_RESPONSE_CAP,
    )
    duration_ms = max(0, int((time.monotonic() - t0) * 1000))

    if blocker or combined is None:
        return ClaudeAgentMissionResult(
            ok=False,
            mission_ok=False,
            worker=worker,
            mission_type=mission_type,
            result_text="",
            parsed_result=None,
            duration_ms=duration_ms,
            safety_mode=safety_mode,
            blocker=blocker or "Claude Agent SDK query produced no text.",
        )

    parsed, mission_ok = _parse_mission_json(combined)
    return ClaudeAgentMissionResult(
        ok=True,
        mission_ok=mission_ok,
        worker=worker,
        mission_type=mission_type,
        result_text=combined,
        parsed_result=parsed,
        duration_ms=duration_ms,
        safety_mode=safety_mode,
        blocker=None if mission_ok else "Mission JSON did not match acceptance shape.",
    )
