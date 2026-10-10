"""HAM Native Builder — workspace execution entry (not JSON artifact mode).

Normal builds route through :mod:`src.ham.hermes_workspace_builder` and
:mod:`src.ham.build_materialization`. The retired JSON artifact transport lives in
``builder_native_hermes_json_artifact_deprecated`` and must not be imported by
product paths.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Callable

from src.ham.build_materialization import BuildMaterializationResult
from src.ham.builder_artifact_verifier import verify_builder_scaffold_artifact
from src.ham.builder_chat_cloud_runtime import maybe_enqueue_chat_scaffold_cloud_runtime_job
from src.ham.builder_preview_typecheck import validate_preview_app_files
from src.ham.hermes_workspace_builder import (
    execute_hermes_native_workspace_build,
    hermes_native_workspace_configured,
)
from src.persistence.builder_source_store import get_builder_source_store
from src.persistence.native_build_context_store import (
    NativeBuildContext,
    get_native_build_context_store,
)

logger = logging.getLogger(__name__)

_NATIVE_UNAVAILABLE_MESSAGE = "HAM Native Builder is not ready yet.\n\n"
_NATIVE_WORKSPACE_NOT_CONFIGURED_MESSAGE = (
    "Native Hermes workspace execution is not configured yet.\n\n"
)
_NATIVE_WORKSPACE_FAILED_MESSAGE = (
    "HAM Native Builder could not complete the workspace build.\n\n"
)
_NATIVE_GATEWAY_MESSAGE = "HAM Native Builder could not reach the Hermes runtime.\n\n"
_NATIVE_BUNDLE_MESSAGE = "HAM Native Builder could not prepare the project files.\n\n"
_NATIVE_STARTED_MESSAGE = (
    "HAM started the native build. I'll prepare the Workbench preview on the right as it runs.\n\n"
)


def hermes_native_builder_ready() -> bool:
    """Return True when the native workspace build lane is enabled on this host."""
    return hermes_native_workspace_configured()


def ham_native_builder_user_message(ham_native: dict[str, Any] | None) -> str:
    """User-facing chat copy for a native build outcome (no build-kit internals)."""
    block = ham_native if isinstance(ham_native, dict) else {}
    status = str(block.get("status") or "").strip().lower()
    reason = str(block.get("failure_reason") or "").strip().lower()
    if status == "started":
        return _NATIVE_STARTED_MESSAGE
    if status in {"unavailable", "not_configured"}:
        if reason in {"unconfigured", "workspace_not_configured"}:
            return _NATIVE_WORKSPACE_NOT_CONFIGURED_MESSAGE
        return _NATIVE_UNAVAILABLE_MESSAGE
    if status == "failed":
        if reason == "gateway":
            return _NATIVE_GATEWAY_MESSAGE
        if reason in {"bundle", "verification"}:
            return _NATIVE_BUNDLE_MESSAGE
        if reason in {"visual_quality", "template_packs_unavailable"}:
            return "HAM couldn't finish this preview.\n\n"
        if reason in {
            "workspace_not_implemented",
            "workspace_not_configured",
            "hermes_cli_unavailable",
            "hermes_cli_timeout",
            "hermes_cli_empty",
            "hermes_cli_failed",
        }:
            return _NATIVE_WORKSPACE_NOT_CONFIGURED_MESSAGE
        return _NATIVE_WORKSPACE_FAILED_MESSAGE
    return _NATIVE_UNAVAILABLE_MESSAGE


def _native_result(
    *,
    status: str,
    failure_reason: str | None = None,
    scaffolded: bool = False,
    import_job_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ham_native: dict[str, Any] = {"status": status}
    if failure_reason:
        ham_native["failure_reason"] = failure_reason
    out: dict[str, Any] = {
        "builder_intent": "build_or_create",
        "builder_operation": "build_or_create",
        "scaffolded": scaffolded,
        "ham_native_builder": ham_native,
    }
    if import_job_id:
        out["import_job_id"] = import_job_id
    if extra:
        out.update(extra)
    return out


def _materialization_to_native_dict(result: BuildMaterializationResult) -> dict[str, Any]:
    if result.status == "not_configured":
        return _native_result(
            status="unavailable",
            failure_reason="workspace_not_configured",
            import_job_id=result.import_job_id,
        )
    if result.status == "failed":
        reason = result.failure_reason or "workspace"
        return _native_result(
            status="failed",
            failure_reason=reason,
            scaffolded=False,
            import_job_id=result.import_job_id,
            extra={
                k: v
                for k, v in {
                    "artifact_verification": result.artifact_verification,
                    "source_snapshot_id": result.source_snapshot_id,
                    "project_source_id": result.project_source_id,
                }.items()
                if v is not None
            },
        )
    return result.to_native_build_dict()


def _fail_native_build(
    store: Any,
    *,
    import_job_id: str,
    phase: str,
    error_code: str,
    error_message: str,
    failure_reason: str,
    extra: dict[str, Any] | None = None,
    stats: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    store.mark_import_job_failed(
        import_job_id=import_job_id,
        phase=phase,
        error_code=error_code,
        error_message=error_message,
        stats=stats,
        metadata=metadata,
    )
    return _native_result(
        status="failed",
        failure_reason=failure_reason,
        import_job_id=import_job_id,
        extra=extra,
    )


def _native_build_preflight() -> dict[str, Any] | None:
    if hermes_native_workspace_configured():
        return None
    logger.info("ham_native_builder_unavailable reason=workspace_not_configured")
    return _native_result(status="unavailable", failure_reason="workspace_not_configured")


def run_hermes_native_build(
    *,
    workspace_id: str,
    project_id: str,
    session_id: str,
    user_prompt: str,
    created_by: str,
    complete_turn: Callable[..., str] | None = None,  # noqa: ARG001 — retired seam
    workspace_files_provider: Callable[..., dict[str, str] | None] | None = None,
) -> dict[str, Any]:
    """Synchronous native build (tests / inline dispatch). Uses workspace lane only."""
    del complete_turn
    early = _native_build_preflight()
    if early is not None:
        return early

    store = get_builder_source_store()
    job = store.create_import_job(
        workspace_id=workspace_id,
        project_id=project_id,
        created_by=created_by,
        phase="received",
        status="queued",
        metadata={
            "origin": "ham_native_builder",
            "activity_title": "HAM Native Builder started",
            "activity_message": "HAM is building natively through Hermes workspace execution.",
        },
    )
    return _execute_native_build_core(
        import_job_id=job.id,
        workspace_id=workspace_id,
        project_id=project_id,
        session_id=session_id,
        user_prompt=user_prompt,
        created_by=created_by,
        workspace_files_provider=workspace_files_provider,
        running_phase="hermes_native_build",
        success_phase="materialized",
        failure_phase="hermes_native_build",
    )


def _execute_native_build_core(
    *,
    import_job_id: str,
    workspace_id: str,
    project_id: str,
    session_id: str,
    user_prompt: str,
    created_by: str,
    workspace_files_provider: Callable[..., dict[str, str] | None] | None = None,
    running_phase: str,
    success_phase: str,
    failure_phase: str,
    generating_phase: str | None = None,
    validating_phase: str | None = None,
    materializing_phase: str | None = None,
    preview_phase: str | None = None,
    repairing_phase: str | None = None,  # noqa: ARG001 — reserved for future iterative workspace
) -> dict[str, Any]:
    """Drive workspace execution + materialization; never calls JSON artifact mode."""
    store = get_builder_source_store()
    store.mark_import_job_running(import_job_id=import_job_id, phase=running_phase)
    current_phase = running_phase

    def _advance(phase: str | None) -> None:
        nonlocal current_phase
        if phase and phase != current_phase:
            store.mark_import_job_running(import_job_id=import_job_id, phase=phase)
            current_phase = phase

    _advance(generating_phase)
    result = execute_hermes_native_workspace_build(
        import_job_id=import_job_id,
        workspace_id=workspace_id,
        project_id=project_id,
        session_id=session_id,
        user_prompt=user_prompt,
        created_by=created_by,
        files_provider=workspace_files_provider,
    )

    if result.status == "not_configured":
        return _fail_native_build(
            store,
            import_job_id=import_job_id,
            phase=failure_phase,
            error_code=result.error_code or "HAM_NATIVE_WORKSPACE_NOT_CONFIGURED",
            error_message=result.user_message or _NATIVE_WORKSPACE_NOT_CONFIGURED_MESSAGE,
            failure_reason="workspace_not_configured",
        )

    if result.status != "succeeded":
        _advance(validating_phase)
        user_message = result.user_message or result.summary
        return _fail_native_build(
            store,
            import_job_id=import_job_id,
            phase=failure_phase,
            error_code=result.error_code or "HAM_NATIVE_WORKSPACE_FAILED",
            error_message=user_message,
            failure_reason=result.failure_reason or "workspace",
            extra={
                k: v
                for k, v in {"artifact_verification": result.artifact_verification}.items()
                if v is not None
            },
            stats=result.operator_stats,
            metadata=result.operator_metadata,
        )

    _advance(materializing_phase)
    _advance(preview_phase)
    store.mark_import_job_succeeded(
        import_job_id=import_job_id,
        phase=success_phase,
        source_snapshot_id=result.source_snapshot_id,
        stats={
            "file_count": (result.validation_report or {}).get("file_count"),
            "native_builder": "hermes_workspace",
        },
    )
    logger.info(
        "ham_native_workspace_succeeded import_job_id=%s snapshot_id=%s",
        import_job_id,
        result.source_snapshot_id,
    )
    return _materialization_to_native_dict(result)


# ---------------------------------------------------------------------------
# HAM Native Builder v2 — async job boundary (Cloud Tasks + worker)
# ---------------------------------------------------------------------------

NATIVE_BUILD_PHASE_QUEUED = "native_build_queued"
NATIVE_BUILD_PHASE_RUNNING = "native_build_running"
NATIVE_BUILD_PHASE_GENERATING = "native_build_generating"
NATIVE_BUILD_PHASE_VALIDATING = "native_build_validating"
NATIVE_BUILD_PHASE_REPAIRING = "native_build_repairing"
NATIVE_BUILD_PHASE_MATERIALIZING = "native_build_materializing"
NATIVE_BUILD_PHASE_PREVIEW_STARTING = "native_build_preview_starting"
NATIVE_BUILD_PHASE_SUCCEEDED = "native_build_succeeded"
NATIVE_BUILD_PHASE_FAILED = "native_build_failed"

NATIVE_BUILD_JOB_ORIGIN = "ham_native_builder_v2"

_EXECUTOR_ERROR_CODE = "HAM_NATIVE_BUILDER_V2_EXECUTOR_ERROR"
_EXECUTOR_ERROR_MESSAGE = "HAM Native Builder could not complete the native build."

_DISPATCH_ENV = "HAM_NATIVE_BUILD_DISPATCH"


def _native_build_dispatch_mode() -> str:
    raw = (os.environ.get(_DISPATCH_ENV) or "").strip().lower()
    return raw if raw in {"inline", "thread"} else "durable"


def start_native_build_job(
    *,
    workspace_id: str,
    project_id: str,
    session_id: str,
    user_prompt: str,
    created_by: str,
    complete_turn: Callable[..., str] | None = None,  # noqa: ARG001 — retired seam
    workspace_files_provider: Callable[..., dict[str, str] | None] | None = None,
) -> dict[str, Any]:
    """Create a native build job and return immediately (workspace lane only)."""
    del complete_turn
    early = _native_build_preflight()
    if early is not None:
        return early

    store = get_builder_source_store()
    job = store.create_import_job(
        workspace_id=workspace_id,
        project_id=project_id,
        created_by=created_by,
        phase=NATIVE_BUILD_PHASE_QUEUED,
        status="queued",
        metadata={"origin": NATIVE_BUILD_JOB_ORIGIN},
    )
    get_native_build_context_store().put_native_build_context(
        NativeBuildContext(
            import_job_id=job.id,
            workspace_id=workspace_id,
            project_id=project_id,
            session_id=session_id,
            user_prompt=user_prompt,
            created_by=created_by,
        )
    )
    logger.info(
        "ham_native_builder_v2_started import_job_id=%s dispatch=%s workspace_configured=%s",
        job.id,
        _native_build_dispatch_mode(),
        str(hermes_native_workspace_configured()).lower(),
    )
    _dispatch_native_build_job(
        import_job_id=job.id,
        workspace_id=workspace_id,
        project_id=project_id,
        session_id=session_id,
        user_prompt=user_prompt,
        created_by=created_by,
        workspace_files_provider=workspace_files_provider,
    )
    return _native_result(
        status="started",
        scaffolded=False,
        import_job_id=job.id,
        extra={"native_build_job_id": job.id},
    )


def _dispatch_native_build_job(**kwargs: Any) -> None:
    mode = _native_build_dispatch_mode()
    if mode == "inline":
        _run_native_build_executor_guarded(**kwargs)
        return
    if mode == "thread":
        threading.Thread(
            target=_run_native_build_executor_guarded,
            kwargs=kwargs,
            name=f"ham-native-build-{kwargs.get('import_job_id')}",
            daemon=True,
        ).start()
        return
    _enqueue_native_build_job_guarded(
        import_job_id=str(kwargs.get("import_job_id") or ""),
        workspace_id=str(kwargs.get("workspace_id") or ""),
        project_id=str(kwargs.get("project_id") or ""),
    )


def _enqueue_native_build_job_guarded(
    *, import_job_id: str, workspace_id: str, project_id: str
) -> None:
    from src.ham.native_build_worker_enqueue import (  # noqa: PLC0415
        NativeBuildExecuteEnvelope,
        get_native_build_enqueue,
    )

    try:
        get_native_build_enqueue().enqueue(
            NativeBuildExecuteEnvelope(
                import_job_id=import_job_id,
                workspace_id=workspace_id,
                project_id=project_id,
            )
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "ham_native_builder_v2_enqueue_failed import_job_id=%s", import_job_id
        )


def _run_native_build_executor_guarded(**kwargs: Any) -> None:
    import_job_id = str(kwargs.get("import_job_id") or "")
    try:
        execute_native_build_job(**kwargs)
    except Exception:  # noqa: BLE001
        logger.exception(
            "ham_native_builder_v2_executor_crashed import_job_id=%s", import_job_id
        )
        try:
            get_builder_source_store().mark_import_job_failed(
                import_job_id=import_job_id,
                phase=NATIVE_BUILD_PHASE_FAILED,
                error_code=_EXECUTOR_ERROR_CODE,
                error_message=_EXECUTOR_ERROR_MESSAGE,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "ham_native_builder_v2_mark_failed_failed import_job_id=%s", import_job_id
            )


def execute_native_build_job(
    *,
    import_job_id: str,
    workspace_id: str,
    project_id: str,
    session_id: str,
    user_prompt: str,
    created_by: str,
    complete_turn: Callable[..., str] | None = None,  # noqa: ARG001 — retired seam
    workspace_files_provider: Callable[..., dict[str, str] | None] | None = None,
) -> dict[str, Any]:
    """Functional native build executor — workspace lane only."""
    del complete_turn
    logger.info(
        "ham_native_builder_v2_executor_start import_job_id=%s workspace_configured=%s",
        import_job_id,
        str(hermes_native_workspace_configured()).lower(),
    )
    return _execute_native_build_core(
        import_job_id=import_job_id,
        workspace_id=workspace_id,
        project_id=project_id,
        session_id=session_id,
        user_prompt=user_prompt,
        created_by=created_by,
        workspace_files_provider=workspace_files_provider,
        running_phase=NATIVE_BUILD_PHASE_RUNNING,
        success_phase=NATIVE_BUILD_PHASE_SUCCEEDED,
        failure_phase=NATIVE_BUILD_PHASE_FAILED,
        generating_phase=NATIVE_BUILD_PHASE_GENERATING,
        validating_phase=NATIVE_BUILD_PHASE_VALIDATING,
        repairing_phase=NATIVE_BUILD_PHASE_REPAIRING,
        materializing_phase=NATIVE_BUILD_PHASE_MATERIALIZING,
        preview_phase=NATIVE_BUILD_PHASE_PREVIEW_STARTING,
    )


__all__ = [
    "execute_native_build_job",
    "ham_native_builder_user_message",
    "hermes_native_builder_ready",
    "run_hermes_native_build",
    "start_native_build_job",
]
