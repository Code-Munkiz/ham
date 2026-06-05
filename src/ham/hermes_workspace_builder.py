"""Hermes Native Builder — harness-native workspace execution (not JSON artifact mode).

Iterative Hermes CLI/workspace edits land here. Normal product builds must never call
:func:`complete_artifact_turn` or parse a one-shot JSON file bundle for project generation.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.ham.template_packs.schema import TemplatePack

from src.ham.build_materialization import (
    BuildMaterializationResult,
    materialize_files_to_snapshot,
)
from src.ham.hermes_workspace_execution import (
    WorkspaceExecutionOutcome,
    collect_workspace_files,
    run_hermes_cli_workspace_build,
)
from src.ham.template_packs.quality import (
    evaluate_workspace_visual_quality,
    user_message_for_quality_failure,
)
from src.ham.template_packs.renderer import append_template_pack_context
from src.ham.template_packs.repair import attempt_visual_quality_repair
from src.ham.template_packs.restore import restore_missing_pack_sections
from src.ham.template_packs.registry import (
    TEMPLATE_PACK_REGISTRY_EMPTY_INTERNAL,
    TemplatePackRegistryEmptyError,
)
from src.ham.template_packs.selector import select_template_pack

_LOG = logging.getLogger(__name__)

_WORKSPACE_ENABLED_ENV = "HAM_HERMES_NATIVE_WORKSPACE_ENABLED"
_WORKSPACE_ROOT_ENV = "HAM_HERMES_NATIVE_WORKSPACE_ROOT"

# Test-only seam: when set, returns file map instead of driving Hermes CLI (never used in prod).
_workspace_files_provider: Callable[..., dict[str, str] | None] | None = None

_USER_MESSAGE_NOT_CONFIGURED = "Native Hermes workspace execution is not configured yet.\n\n"
_USER_MESSAGE_CLI_UNAVAILABLE = (
    "Native Hermes workspace execution is not available on this host yet.\n\n"
)
_ERROR_CODE_NOT_CONFIGURED = "HAM_NATIVE_WORKSPACE_NOT_CONFIGURED"
_ERROR_CODE_CLI_UNAVAILABLE = "HERMES_CLI_UNAVAILABLE"
_ERROR_CODE_CLI_EMPTY = "HERMES_CLI_EMPTY_WORKSPACE"
_ERROR_CODE_CLI_TIMEOUT = "HERMES_CLI_TIMEOUT"
_ERROR_CODE_CLI_FAILED = "HERMES_CLI_FAILED"
_ERROR_CODE_VISUAL_QUALITY = "HAM_NATIVE_VISUAL_QUALITY_FAILED"
_ERROR_CODE_TEMPLATE_PACKS_EMPTY = "HAM_TEMPLATE_PACK_REGISTRY_EMPTY"
_PREVIEW_QUALITY_USER_MESSAGE = user_message_for_quality_failure()


def _template_pack_registry_unavailable_result(
    *, import_job_id: str
) -> BuildMaterializationResult:
    return BuildMaterializationResult(
        status="failed",
        summary=TEMPLATE_PACK_REGISTRY_EMPTY_INTERNAL,
        import_job_id=import_job_id,
        failure_reason="template_packs_unavailable",
        user_message=_PREVIEW_QUALITY_USER_MESSAGE,
        error_code=_ERROR_CODE_TEMPLATE_PACKS_EMPTY,
    )


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


def _outcome_to_user_message(outcome: WorkspaceExecutionOutcome) -> str:
    code = (outcome.error_code or "").strip()
    if code in {_ERROR_CODE_CLI_UNAVAILABLE, _ERROR_CODE_CLI_TIMEOUT, _ERROR_CODE_CLI_FAILED}:
        return _USER_MESSAGE_CLI_UNAVAILABLE
    if code == _ERROR_CODE_CLI_EMPTY:
        return _USER_MESSAGE_CLI_UNAVAILABLE
    return _USER_MESSAGE_CLI_UNAVAILABLE


def _resolve_workspace_files(
    *,
    workspace_id: str,
    project_id: str,
    import_job_id: str,
    user_prompt: str,
    workspace_dir: Path,
    files_provider: Callable[..., dict[str, str] | None] | None,
    template_pack: TemplatePack | None = None,
    selection_prompt: str | None = None,
) -> tuple[dict[str, str] | None, WorkspaceExecutionOutcome | None]:
    """Collect generated files from the workspace harness (provider seam or Hermes CLI)."""
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
            return collected, None
        return None, WorkspaceExecutionOutcome(
            ok=False,
            error_code=_ERROR_CODE_CLI_EMPTY,
            error_summary="Test workspace provider returned no files.",
        )

    try:
        pack = template_pack or select_template_pack(selection_prompt or user_prompt)
    except TemplatePackRegistryEmptyError:
        _LOG.warning(
            "template_pack_registry_empty import_job_id=%s",
            import_job_id,
        )
        return None, WorkspaceExecutionOutcome(
            ok=False,
            error_code=_ERROR_CODE_TEMPLATE_PACKS_EMPTY,
            error_summary=TEMPLATE_PACK_REGISTRY_EMPTY_INTERNAL,
        )
    outcome = run_hermes_cli_workspace_build(
        workspace_dir=workspace_dir,
        user_prompt=user_prompt,
        import_job_id=import_job_id,
        template_pack=pack,
    )
    if not outcome.ok:
        return None, outcome
    return outcome.files or collect_workspace_files(workspace_dir) or None, outcome


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
    with safe user copy. When enabled but Hermes CLI is unavailable or produces no
    files, fails clearly without falling back to :func:`complete_artifact_turn` or
    legacy scaffold.
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

    try:
        pack = select_template_pack(user_prompt)
    except TemplatePackRegistryEmptyError:
        _LOG.warning(
            "template_pack_registry_empty import_job_id=%s project_id=%s",
            import_job_id,
            project_id,
        )
        return _template_pack_registry_unavailable_result(import_job_id=import_job_id)

    enriched_prompt = append_build_registry_context(
        user_prompt, originated_from="ham_native_workspace_builder"
    )
    enriched_prompt = append_template_pack_context(enriched_prompt, pack)
    workspace_dir = _isolated_workspace_dir(
        workspace_id=workspace_id,
        project_id=project_id,
        import_job_id=import_job_id,
    )
    build_started = time.monotonic()
    _LOG.warning(
        "hermes_native_workspace_start import_job_id=%s project_id=%s prompt_chars=%d",
        import_job_id,
        project_id,
        len(enriched_prompt),
    )

    files, exec_outcome = _resolve_workspace_files(
        workspace_id=workspace_id,
        project_id=project_id,
        import_job_id=import_job_id,
        user_prompt=enriched_prompt,
        workspace_dir=workspace_dir,
        files_provider=files_provider,
        template_pack=pack,
        selection_prompt=user_prompt,
    )

    if files:
        quality = evaluate_workspace_visual_quality(files, pack=pack)
        restored_section_ids: tuple[str, ...] = ()
        if not quality.ok:
            restored = restore_missing_pack_sections(files, pack=pack, issues=quality.issues)
            if restored is not None:
                files, restored_section_ids = restored
                quality = evaluate_workspace_visual_quality(files, pack=pack)
                _LOG.warning(
                    "template_pack_sections_restored import_job_id=%s sections=%s",
                    import_job_id,
                    list(restored_section_ids),
                )
        if not quality.ok:
            repaired = attempt_visual_quality_repair(
                workspace_dir=workspace_dir,
                user_prompt=enriched_prompt,
                import_job_id=import_job_id,
                pack=pack,
                quality_issues=quality.issues,
                files_provider=files_provider,
            )
            if repaired:
                files = repaired
                quality = evaluate_workspace_visual_quality(files, pack=pack)
                restored = restore_missing_pack_sections(files, pack=pack, issues=quality.issues)
                if restored is not None:
                    files, post_repair_ids = restored
                    restored_section_ids = restored_section_ids + post_repair_ids
                    quality = evaluate_workspace_visual_quality(files, pack=pack)
                    _LOG.warning(
                        "template_pack_sections_restored_after_repair import_job_id=%s sections=%s",
                        import_job_id,
                        list(post_repair_ids),
                    )
        if not quality.ok:
            operator_metadata = quality.to_operator_metadata()
            if restored_section_ids:
                operator_metadata = {
                    **operator_metadata,
                    "sections_restored": list(restored_section_ids),
                }
            return BuildMaterializationResult(
                status="failed",
                summary="Visual quality gate failed.",
                import_job_id=import_job_id,
                failure_reason="visual_quality",
                user_message=_PREVIEW_QUALITY_USER_MESSAGE,
                error_code=_ERROR_CODE_VISUAL_QUALITY,
                operator_metadata=operator_metadata,
            )

    if not files:
        outcome = exec_outcome or WorkspaceExecutionOutcome(
            ok=False,
            error_code=_ERROR_CODE_CLI_EMPTY,
            error_summary="Workspace build produced no files.",
        )
        if outcome.error_code == _ERROR_CODE_TEMPLATE_PACKS_EMPTY:
            _LOG.warning(
                "template_pack_registry_empty import_job_id=%s project_id=%s",
                import_job_id,
                project_id,
            )
            return _template_pack_registry_unavailable_result(import_job_id=import_job_id)
        reason = "hermes_cli_unavailable"
        if outcome.error_code == _ERROR_CODE_CLI_TIMEOUT:
            reason = "hermes_cli_timeout"
        elif outcome.error_code == _ERROR_CODE_CLI_EMPTY:
            reason = "hermes_cli_empty"
        return BuildMaterializationResult(
            status="failed",
            summary=outcome.error_summary or "Workspace build failed.",
            import_job_id=import_job_id,
            failure_reason=reason,
            user_message=_outcome_to_user_message(outcome),
            error_code=outcome.error_code or _ERROR_CODE_CLI_FAILED,
        )

    elapsed_ms = int((time.monotonic() - build_started) * 1000)
    _LOG.warning(
        "hermes_native_workspace_files_collected import_job_id=%s project_id=%s file_count=%d elapsed_ms=%d",
        import_job_id,
        project_id,
        len(files),
        elapsed_ms,
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
        materialization_started_at=build_started,
    )


__all__ = [
    "append_build_registry_context",
    "execute_hermes_native_workspace_build",
    "hermes_native_workspace_configured",
]
