"""HAM builder materialization boundary — harness-neutral snapshot outcomes.

External harnesses (workspace tree, managed snapshot, repo diff) converge here
before Workbench preview. No harness is required to emit a single JSON file bundle.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from src.ham.builder_artifact_verifier import verify_builder_scaffold_artifact
from src.ham.builder_chat_cloud_runtime import maybe_enqueue_chat_scaffold_cloud_runtime_job
from src.ham.builder_preview_bootstrap import ensure_preview_bootstrap_files
from src.ham.builder_preview_typecheck import (
    user_safe_typecheck_failure_message,
    validate_preview_app_files,
)
from src.persistence.builder_source_store import (
    ProjectSource,
    SourceSnapshot,
    get_builder_source_store,
)

_LOG = logging.getLogger(__name__)

_MANIFEST_KIND_INLINE = "inline_text_bundle"
MaterializationStatus = Literal["succeeded", "failed", "unavailable", "not_configured"]


@dataclass(frozen=True)
class BuildMaterializationResult:
    """Harness-neutral outcome after files are known (from any collection method)."""

    status: MaterializationStatus
    summary: str
    import_job_id: str | None = None
    source_snapshot_id: str | None = None
    project_source_id: str | None = None
    validation_report: dict[str, Any] | None = None
    preview_meta: dict[str, Any] = field(default_factory=dict)
    failure_reason: str | None = None
    user_message: str | None = None
    error_code: str | None = None
    scaffolded: bool = False
    artifact_verification: dict[str, Any] | None = None

    def to_native_build_dict(self) -> dict[str, Any]:
        """Shape consumed by chat hooks and legacy native builder callers."""
        ham_native: dict[str, Any] = {"status": self.status}
        if self.failure_reason:
            ham_native["failure_reason"] = self.failure_reason
        out: dict[str, Any] = {
            "builder_intent": "build_or_create",
            "builder_operation": "build_or_create",
            "scaffolded": self.scaffolded,
            "ham_native_builder": ham_native,
        }
        if self.import_job_id:
            out["import_job_id"] = self.import_job_id
        if self.source_snapshot_id:
            out["source_snapshot_id"] = self.source_snapshot_id
        if self.project_source_id:
            out["project_source_id"] = self.project_source_id
        if self.artifact_verification:
            out["artifact_verification"] = self.artifact_verification
        out.update(self.preview_meta)
        return out


def _artifact_root() -> Path:
    raw = (__import__("os").environ.get("HAM_BUILDER_SOURCE_ARTIFACT_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".ham" / "builder-source-artifacts").resolve()


def _materialize_inline_files_as_zip_artifact(
    *,
    workspace_id: str,
    project_id: str,
    files: dict[str, str],
) -> tuple[str, int]:
    artifact_id = f"bzip_{uuid.uuid4().hex}"
    target_dir = _artifact_root() / workspace_id / project_id
    target_dir.mkdir(parents=True, exist_ok=True)
    zip_path = target_dir / f"{artifact_id}.zip"
    buf = BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel, text in sorted(files.items()):
            zf.writestr(rel, text.encode("utf-8"))
    payload = buf.getvalue()
    if len(payload) > 50 * 1024 * 1024:
        raise ValueError("artifact_zip_too_large")
    zip_path.write_bytes(payload)
    return f"builder-artifact://{artifact_id}", len(payload)


def materialize_files_to_snapshot(
    *,
    import_job_id: str,
    workspace_id: str,
    project_id: str,
    session_id: str,
    user_prompt: str,
    created_by: str,
    files: dict[str, str],
    store: Any | None = None,
    template_label: str = "hermes_workspace",
) -> BuildMaterializationResult:
    """Validate, bootstrap, typecheck, verify, and persist a Workbench source snapshot."""
    source_store = store or get_builder_source_store()
    candidate_files = ensure_preview_bootstrap_files(files, project_name=user_prompt)
    typecheck = validate_preview_app_files(candidate_files)
    candidate_files = typecheck.files
    if not typecheck.ok:
        return BuildMaterializationResult(
            status="failed",
            summary="Typecheck failed.",
            import_job_id=import_job_id,
            failure_reason="bundle",
            user_message=typecheck.user_message or user_safe_typecheck_failure_message(),
            error_code="HAM_NATIVE_BUILDER_TYPECHECK_FAILED",
            scaffolded=False,
            validation_report={"typecheck": "failed"},
        )

    verification = verify_builder_scaffold_artifact(
        user_prompt, {"template": template_label}, candidate_files, "build_or_create"
    )
    if not verification.get("verified"):
        return BuildMaterializationResult(
            status="failed",
            summary="Verification failed.",
            import_job_id=import_job_id,
            failure_reason="verification",
            error_code="HAM_NATIVE_BUILDER_VERIFY_FAILED",
            scaffolded=False,
            artifact_verification=verification,
            validation_report={"verification": verification},
        )

    digest = hashlib.sha256(json.dumps(candidate_files, sort_keys=True).encode("utf-8")).hexdigest()
    artifact_uri, zip_size = _materialize_inline_files_as_zip_artifact(
        workspace_id=workspace_id,
        project_id=project_id,
        files=candidate_files,
    )
    entries_manifest: list[dict[str, Any]] = []
    total_bytes = 0
    for path, text in sorted(candidate_files.items()):
        size = len(text.encode("utf-8"))
        total_bytes += size
        entries_manifest.append({"path": path, "size_bytes": size})

    source = ProjectSource(
        workspace_id=workspace_id,
        project_id=project_id,
        kind="ham_native_builder",
        status="ready",
        display_name="HAM Native Builder",
        origin_ref="ham_native_workspace",
        created_by=created_by,
        metadata={"native_builder": "hermes_workspace"},
    )
    source = source_store.upsert_project_source(source)
    snapshot = SourceSnapshot(
        workspace_id=workspace_id,
        project_id=project_id,
        project_source_id=source.id,
        digest_sha256=digest,
        size_bytes=zip_size,
        artifact_uri=artifact_uri,
        manifest={
            "kind": _MANIFEST_KIND_INLINE,
            "file_count": len(entries_manifest),
            "entries": entries_manifest,
            "inline_files": candidate_files,
        },
        created_by=created_by,
        metadata={
            "native_builder": "hermes_workspace",
            "import_job_id": import_job_id,
            "chat_scaffold_operation": "build_or_create",
        },
    )
    snapshot = source_store.upsert_source_snapshot(snapshot)
    source.active_snapshot_id = snapshot.id
    source_store.upsert_project_source(source)

    preview_meta: dict[str, Any] = {}
    try:
        preview_meta = maybe_enqueue_chat_scaffold_cloud_runtime_job(
            workspace_id=workspace_id,
            project_id=project_id,
            source_snapshot_id=snapshot.id,
            session_id=session_id,
            requested_by=created_by,
        )
    except Exception:  # noqa: BLE001
        _LOG.warning("ham_native_workspace_preview_enqueue_failed import_job_id=%s", import_job_id)

    return BuildMaterializationResult(
        status="succeeded",
        summary="Materialized workspace build.",
        import_job_id=import_job_id,
        source_snapshot_id=snapshot.id,
        project_source_id=source.id,
        scaffolded=True,
        artifact_verification=verification,
        validation_report={"typecheck": "passed", "verification": verification},
        preview_meta=preview_meta,
    )


__all__ = [
    "BuildMaterializationResult",
    "MaterializationStatus",
    "materialize_files_to_snapshot",
]
