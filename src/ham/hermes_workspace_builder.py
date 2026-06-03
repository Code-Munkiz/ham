"""Hermes Native Builder — harness-native workspace execution (not JSON artifact mode).

Iterative Hermes CLI/workspace edits land here. Normal product builds must never call
:func:`complete_artifact_turn` or parse a one-shot JSON file bundle for project generation.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.ham.build_materialization import (
    BuildMaterializationResult,
    materialize_files_to_snapshot,
)

_LOG = logging.getLogger(__name__)

_WORKSPACE_ENABLED_ENV = "HAM_HERMES_NATIVE_WORKSPACE_ENABLED"
_WORKSPACE_ROOT_ENV = "HAM_HERMES_NATIVE_WORKSPACE_ROOT"

# Test-only seam: when set, returns file map instead of driving Hermes CLI (never used in prod).
_workspace_files_provider: Callable[..., dict[str, str] | None] | None = None

_USER_MESSAGE_NOT_CONFIGURED = "Native Hermes workspace execution is not configured yet.\n\n"
_USER_MESSAGE_NOT_IMPLEMENTED = (
    "Native Hermes workspace execution is enabled but not available on this host yet.\n\n"
)
_ERROR_CODE_NOT_CONFIGURED = "HAM_NATIVE_WORKSPACE_NOT_CONFIGURED"
_ERROR_CODE_NOT_IMPLEMENTED = "HAM_NATIVE_WORKSPACE_NOT_IMPLEMENTED"
_ERROR_CODE_EMPTY_WORKSPACE = "HAM_NATIVE_WORKSPACE_EMPTY"


def _truthy_env(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def hermes_native_workspace_configured() -> bool:
    """Return True when the workspace execution lane is enabled on this host."""
    return _truthy_env(_WORKSPACE_ENABLED_ENV)


def append_build_registry_context(user_prompt: str, *, originated_from: str) -> str:
    """Append Build Registry v2 / v1 playbook context (internal only)."""
    prompt = str(user_prompt or "")
    try:
        from src.ham.build_registry.intent import enrich_plan_metadata_with_registry_v2
        from src.ham.build_registry.scaffold_context import resolve_scaffold_context
        from src.ham.builder_kit_router import select_kit_for_prompt

        template_kind = select_kit_for_prompt(prompt)
        metadata = enrich_plan_metadata_with_registry_v2(
            {"template_kind": template_kind, "originated_from": originated_from},
            prompt,
        )
        resolved = resolve_scaffold_context(metadata=metadata, template_kind=template_kind)
        if resolved.source == "none" or not resolved.context.strip():
            return prompt
        return f"{prompt}\n\n{resolved.header}\n{resolved.context}"
    except Exception:  # noqa: BLE001
        return prompt


def _isolated_workspace_dir(*, workspace_id: str, project_id: str, import_job_id: str) -> Path:
    root_raw = (os.environ.get(_WORKSPACE_ROOT_ENV) or "").strip()
    base = Path(root_raw).expanduser().resolve() if root_raw else Path.home() / ".ham" / "native-workspaces"
    path = base / workspace_id / project_id / import_job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _collect_files_from_workspace_tree(workspace_dir: Path) -> dict[str, str]:
    """Read text files from an isolated workspace tree (posix-relative paths)."""
    if not workspace_dir.is_dir():
        return {}
    out: dict[str, str] = {}
    for file_path in sorted(workspace_dir.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(workspace_dir).as_posix()
        if ".." in rel.split("/"):
            continue
        try:
            text = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        out[rel] = text
    return out


def _resolve_workspace_files(
    *,
    workspace_id: str,
    project_id: str,
    import_job_id: str,
    user_prompt: str,
    workspace_dir: Path,
    files_provider: Callable[..., dict[str, str] | None] | None,
) -> dict[str, str] | None:
    """Collect generated files from the workspace harness (provider seam or on-disk tree)."""
    provider = files_provider or _workspace_files_provider
    if provider is not None:
        collected = provider(
            workspace_id=workspace_id,
            project_id=project_id,
            import_job_id=import_job_id,
            user_prompt=user_prompt,
            workspace_dir=workspace_dir,
        )
        if isinstance(collected, dict) and collected:
            return collected
        return None

    # Skeleton: Hermes CLI iterative execution is not wired yet on this host.
    return None


def execute_hermes_native_workspace_build(
    *,
    import_job_id: str,
    workspace_id: str,
    project_id: str,
    session_id: str,
    user_prompt: str,
    created_by: str,
    files_provider: Callable[..., dict[str, str] | None] | None = None,
) -> BuildMaterializationResult:
    """Run the native Hermes workspace build lane (never JSON artifact mode).

    When ``HAM_HERMES_NATIVE_WORKSPACE_ENABLED`` is unset, returns ``not_configured``
    with safe user copy. When enabled but no files are produced, fails clearly without
    falling back to :func:`complete_artifact_turn` or legacy scaffold.
    """
    if not hermes_native_workspace_configured():
        return BuildMaterializationResult(
            status="not_configured",
            summary=_USER_MESSAGE_NOT_CONFIGURED,
            import_job_id=import_job_id,
            failure_reason="workspace_not_configured",
            user_message=_USER_MESSAGE_NOT_CONFIGURED,
            error_code=_ERROR_CODE_NOT_CONFIGURED,
        )

    enriched_prompt = append_build_registry_context(
        user_prompt, originated_from="ham_native_workspace_builder"
    )
    workspace_dir = _isolated_workspace_dir(
        workspace_id=workspace_id,
        project_id=project_id,
        import_job_id=import_job_id,
    )
    _LOG.info(
        "ham_native_workspace_build_start import_job_id=%s workspace_dir=%s prompt_chars=%d",
        import_job_id,
        workspace_dir,
        len(enriched_prompt),
    )

    files = _resolve_workspace_files(
        workspace_id=workspace_id,
        project_id=project_id,
        import_job_id=import_job_id,
        user_prompt=enriched_prompt,
        workspace_dir=workspace_dir,
        files_provider=files_provider,
    )
    if files is None:
        on_disk = _collect_files_from_workspace_tree(workspace_dir)
        files = on_disk if on_disk else None

    if not files:
        return BuildMaterializationResult(
            status="failed",
            summary="Workspace build produced no files.",
            import_job_id=import_job_id,
            failure_reason="workspace_not_implemented",
            user_message=_USER_MESSAGE_NOT_IMPLEMENTED,
            error_code=_ERROR_CODE_NOT_IMPLEMENTED,
        )

    return materialize_files_to_snapshot(
        import_job_id=import_job_id,
        workspace_id=workspace_id,
        project_id=project_id,
        session_id=session_id,
        user_prompt=user_prompt,
        created_by=created_by,
        files=files,
        template_label="hermes_workspace",
    )


__all__ = [
    "append_build_registry_context",
    "execute_hermes_native_workspace_build",
    "hermes_native_workspace_configured",
]
