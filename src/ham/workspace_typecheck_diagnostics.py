"""Safe operator diagnostics for Native Hermes workspace typecheck failures."""

from __future__ import annotations

import logging
import uuid
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

from src.ham.builder_preview_typecheck import sanitize_typecheck_output

_LOG = logging.getLogger(__name__)

OPERATOR_METADATA_KEY = "native_workspace_operator"
OPERATOR_STATS_KEY = "native_workspace_typecheck"

_MAX_TSC_EXCERPT_LINES = 24
_MAX_FILE_PATHS = 64
_MAX_FAILED_ARTIFACT_BYTES = 8 * 1024 * 1024
_FAILED_ARTIFACT_URI_PREFIX = "builder-failed-artifact://"

_SKIP_DIR_NAMES = frozenset(
    {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".next",
        ".cache",
    }
)
_SKIP_FILE_NAMES = frozenset({".env", ".env.local", ".env.production"})


def _artifact_root() -> Path:
    raw = (__import__("os").environ.get("HAM_BUILDER_SOURCE_ARTIFACT_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".ham" / "builder-source-artifacts").resolve()


def should_skip_failed_artifact_path(rel: str) -> bool:
    """Return True when a relative path must not be stored in failed-workspace artifacts."""
    parts = rel.split("/")
    if any(part in _SKIP_DIR_NAMES for part in parts):
        return True
    base = parts[-1] if parts else rel
    if base in _SKIP_FILE_NAMES:
        return True
    if base.startswith(".env."):
        return True
    return False


def _has_path(files: dict[str, str], *candidates: str) -> bool:
    keys = set(files)
    for candidate in candidates:
        if candidate in keys:
            return True
    return False


def _has_tsconfig(files: dict[str, str]) -> bool:
    return any(p.startswith("tsconfig") and p.endswith(".json") for p in files)


def _has_tailwind_config(files: dict[str, str]) -> bool:
    return _has_path(files, "tailwind.config.js", "tailwind.config.cjs", "tailwind.config.ts")


def build_typecheck_file_presence(files: dict[str, str]) -> dict[str, bool]:
    return {
        "package_json": _has_path(files, "package.json"),
        "index_html": _has_path(files, "index.html"),
        "src_main_tsx": _has_path(files, "src/main.tsx"),
        "src_app_tsx": _has_path(files, "src/App.tsx"),
        "tsconfig": _has_tsconfig(files),
        "tailwind_config": _has_tailwind_config(files),
    }


def safe_tsc_output_excerpt(compiler_output: str) -> str:
    """Capped, sanitized tsc stderr/stdout for operator diagnostics only."""
    sanitized = sanitize_typecheck_output(compiler_output)
    if not sanitized:
        return ""
    lines = [line for line in sanitized.splitlines() if line.strip()]
    return "\n".join(lines[:_MAX_TSC_EXCERPT_LINES])


def build_typecheck_diagnostic_summary(
    *,
    files: dict[str, str],
    error_code: str,
    compiler_output: str,
    artifact_capture: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build operator stats + metadata for a workspace typecheck failure."""
    paths = sorted(files.keys())[:_MAX_FILE_PATHS]
    presence = build_typecheck_file_presence(files)
    stats: dict[str, Any] = {
        "failure_kind": "typecheck",
        "error_code": error_code,
        "file_count": len(files),
        "file_paths": paths,
        **{f"has_{k}": v for k, v in presence.items()},
        "tsc_output_excerpt": safe_tsc_output_excerpt(compiler_output),
    }
    operator_meta: dict[str, Any] = {
        "failure_kind": "typecheck",
        "error_code": error_code,
        "file_count": len(files),
        "file_paths": paths,
        **{f"has_{k}": v for k, v in presence.items()},
        "tsc_output_excerpt": stats["tsc_output_excerpt"],
    }
    if artifact_capture:
        operator_meta["artifact_capture"] = artifact_capture
        if artifact_capture.get("artifact_uri"):
            stats["failed_artifact_uri"] = artifact_capture["artifact_uri"]
    return {OPERATOR_STATS_KEY: stats}, {OPERATOR_METADATA_KEY: operator_meta}


def capture_failed_workspace_artifact(
    *,
    files: dict[str, str],
    workspace_id: str,
    project_id: str,
    import_job_id: str,
) -> dict[str, Any]:
    """Persist a zip of failed generated files for operator debugging (internal only)."""
    safe_files = {
        rel: text
        for rel, text in files.items()
        if rel and not should_skip_failed_artifact_path(rel)
    }
    if not safe_files:
        _LOG.warning(
            "hermes_native_workspace_artifact_capture_unavailable import_job_id=%s reason=no_safe_files",
            import_job_id,
        )
        return {"capture_status": "unavailable", "reason": "no_safe_files"}

    artifact_id = f"bfail_{uuid.uuid4().hex}"
    target_dir = _artifact_root() / workspace_id / project_id / "failed-workspaces"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _LOG.warning(
            "hermes_native_workspace_artifact_capture_unavailable import_job_id=%s reason=mkdir err=%s",
            import_job_id,
            type(exc).__name__,
        )
        return {"capture_status": "unavailable", "reason": "artifact_dir_unwritable"}

    zip_path = target_dir / f"{import_job_id}_{artifact_id}.zip"
    buf = BytesIO()
    try:
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for rel, text in sorted(safe_files.items()):
                zf.writestr(rel, text.encode("utf-8"))
        payload = buf.getvalue()
        if len(payload) > _MAX_FAILED_ARTIFACT_BYTES:
            _LOG.warning(
                "hermes_native_workspace_artifact_capture_unavailable import_job_id=%s reason=too_large bytes=%d",
                import_job_id,
                len(payload),
            )
            return {
                "capture_status": "unavailable",
                "reason": "artifact_too_large",
                "file_count": len(safe_files),
            }
        zip_path.write_bytes(payload)
    except OSError as exc:
        _LOG.warning(
            "hermes_native_workspace_artifact_capture_unavailable import_job_id=%s reason=write err=%s",
            import_job_id,
            type(exc).__name__,
        )
        return {"capture_status": "unavailable", "reason": "artifact_write_failed"}

    return {
        "capture_status": "stored",
        "artifact_uri": f"{_FAILED_ARTIFACT_URI_PREFIX}{artifact_id}",
        "artifact_bytes": len(payload),
        "file_count": len(safe_files),
    }


def strip_operator_fields_from_import_job_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove operator-only native workspace diagnostics from a public import-job dict."""
    out = dict(payload)
    metadata = dict(out.get("metadata") or {})
    metadata.pop(OPERATOR_METADATA_KEY, None)
    out["metadata"] = metadata
    stats = dict(out.get("stats") or {})
    stats.pop(OPERATOR_STATS_KEY, None)
    out["stats"] = stats
    return out


__all__ = [
    "OPERATOR_METADATA_KEY",
    "OPERATOR_STATS_KEY",
    "build_typecheck_diagnostic_summary",
    "build_typecheck_file_presence",
    "capture_failed_workspace_artifact",
    "safe_tsc_output_excerpt",
    "should_skip_failed_artifact_path",
    "strip_operator_fields_from_import_job_payload",
]
