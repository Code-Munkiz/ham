"""Helpers for VAL-OPERATOR-014/015 visible-string leak scans.

These utilities walk a nested payload (REST response body, stream event dict,
PDF-rendered text fragment, etc.) and yield every user-visible string so a
caller can assert that no forbidden internal/protocol/runtime token leaks
into normal product copy.

Strings that live under known machine-metadata keys (``provider``, ``proposal_digest``,
``base_revision``, ``persist_path``, identifier-shaped fields, etc.) are treated
as allowed because they are not rendered as product copy and the contract
explicitly preserves them in API transport / operator diagnostics.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

FORBIDDEN_VISIBLE_TOKENS: tuple[str, ...] = (
    "HERMES_GATEWAY",
    "HERMES_GATEWAY_MODE",
    "HERMES_GATEWAY_BASE_URL",
    "HERMES_GATEWAY_MODEL",
    "HERMES_GATEWAY_API_KEY",
    "OPENROUTER_API_KEY",
    "HAM_RUN_LAUNCH_TOKEN",
    "HAM_DROID_EXEC_TOKEN",
    "HAM_CURSOR_AGENT_LAUNCH_TOKEN",
    "HAM_SETTINGS_WRITE_TOKEN",
    "HAM_SKILLS_WRITE_TOKEN",
    "HAM_CLAUDE_AGENT_SMOKE_TOKEN",
    "proposal_digest",
    "base_revision",
    "operator.phase",
    ".ham/runs",
    "ControlPlaneRun",
    "Cloud Run",
    "GCP",
    "Firestore",
    "cursor_cloud_agent",
    "cursor_cloud",
    "claude_code",
    "opencode_cli",
    "factory_droid_audit",
    "factory_droid_build",
    "Cloud Agent",
    "Cursor Cloud Agent",
)

MACHINE_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "session_id",
        "request_id",
        "run_id",
        "audit_id",
        "runner_id",
        "agent_id",
        "external_id",
        "cursor_agent_id",
        "mission_registry_id",
        "workflow_id",
        "project_id",
        "profile_id",
        "owner_key",
        "proposal_digest",
        "base_revision",
        "new_revision",
        "backup_id",
        "provider",
        "preferred_provider",
        "model",
        "model_id",
        "default_model",
        "persist_path",
        "cwd",
        "path",
        "root",
        "repository",
        "ref",
        "reason_code",
        "code",
        "phase",
        "kind",
        "mime",
        "harness_id",
    }
)


def iter_visible_strings(
    obj: Any,
    *,
    extra_metadata_keys: frozenset[str] = frozenset(),
    path: tuple[str | int, ...] = (),
) -> Iterator[tuple[tuple[str | int, ...], str]]:
    """Yield ``(path, value)`` for every string outside known machine-metadata keys."""
    metadata_keys = MACHINE_METADATA_KEYS | extra_metadata_keys
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k in metadata_keys:
                continue
            yield from iter_visible_strings(
                v,
                extra_metadata_keys=extra_metadata_keys,
                path=path + (str(k),),
            )
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from iter_visible_strings(
                v,
                extra_metadata_keys=extra_metadata_keys,
                path=path + (i,),
            )
    elif isinstance(obj, str):
        yield path, obj


def assert_no_visible_leaks(
    obj: Any,
    *,
    tokens: tuple[str, ...] = FORBIDDEN_VISIBLE_TOKENS,
    extra_metadata_keys: frozenset[str] = frozenset(),
    label: str = "payload",
) -> None:
    """Assert no forbidden token appears in any user-visible string under ``obj``.

    Strings whose immediate parent key is in ``MACHINE_METADATA_KEYS`` (or
    ``extra_metadata_keys``) are skipped — those are machine fields preserved
    for routing/diagnostics and are not rendered as product copy.
    """
    leaks: list[str] = []
    for path, value in iter_visible_strings(obj, extra_metadata_keys=extra_metadata_keys):
        for tok in tokens:
            if tok in value:
                where = ".".join(str(p) for p in path) or "<root>"
                leaks.append(f"{label}[{where}] leaked {tok!r}: {value[:160]!r}")
                break
    if leaks:
        raise AssertionError(
            "visible payload leaked forbidden tokens:\n" + "\n".join(leaks)
        )
