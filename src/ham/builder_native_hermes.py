"""HAM Native Builder entry point backed by the Hermes gateway.

This module is intentionally separate from the legacy scaffold generator. It
asks Hermes for a bounded full-file bundle, validates the response, then writes
the same source snapshot shape the Workbench preview already understands.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from src.ham.builder_artifact_verifier import verify_builder_scaffold_artifact
from src.ham.builder_chat_cloud_runtime import maybe_enqueue_chat_scaffold_cloud_runtime_job
from src.ham.builder_preview_bootstrap import ensure_preview_bootstrap_files
from src.integrations.nous_gateway_client import GatewayCallError, complete_chat_turn
from src.persistence.builder_source_store import (
    ProjectSource,
    SourceSnapshot,
    get_builder_source_store,
)

_MANIFEST_KIND_INLINE = "inline_text_bundle"
_MAX_FILES = 40
_MAX_FILE_BYTES = 80_000
_MAX_TOTAL_TEXT = 300_000
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")
_ALLOWED_PATH_RE = re.compile(
    r"^(?:package\.json|index\.html|vite\.config\.(?:ts|js)|tsconfig(?:\.\w+)?\.json|"
    r"src/[\w./-]+\.(?:tsx|ts|jsx|js|css|json)|public/[\w./-]+)$"
)

logger = logging.getLogger(__name__)

_NATIVE_UNAVAILABLE_MESSAGE = "HAM Native Builder is not ready yet.\n\n"
_NATIVE_UNCONFIGURED_MESSAGE = "HAM Native Builder is still being configured.\n\n"
_NATIVE_GATEWAY_MESSAGE = "HAM Native Builder could not reach the Hermes runtime.\n\n"
_NATIVE_BUNDLE_MESSAGE = "HAM Native Builder could not prepare the project files.\n\n"


def _looks_like_mock_assistant_text(text: str) -> bool:
    return "mock assistant reply" in str(text or "").lower()


def hermes_native_builder_ready() -> bool:
    raw = (os.environ.get("HERMES_GATEWAY_MODE") or "").strip().lower()
    if raw == "mock":
        return False
    if raw == "openrouter":
        try:
            from src.llm_client import normalized_openrouter_api_key, openrouter_api_key_is_plausible

            key = normalized_openrouter_api_key()
            return bool(key and openrouter_api_key_is_plausible(key))
        except Exception:  # noqa: BLE001
            return False
    if raw == "http":
        return bool((os.environ.get("HERMES_GATEWAY_BASE_URL") or "").strip())
    return bool((os.environ.get("HERMES_GATEWAY_BASE_URL") or "").strip())


def ham_native_builder_user_message(ham_native: dict[str, Any] | None) -> str:
    """User-facing chat copy for a native build outcome (no build-kit internals)."""
    block = ham_native if isinstance(ham_native, dict) else {}
    status = str(block.get("status") or "").strip().lower()
    reason = str(block.get("failure_reason") or "").strip().lower()
    if status == "unavailable":
        if reason == "unconfigured":
            return _NATIVE_UNCONFIGURED_MESSAGE
        return _NATIVE_UNAVAILABLE_MESSAGE
    if status == "failed":
        if reason == "gateway":
            return _NATIVE_GATEWAY_MESSAGE
        if reason in {"bundle", "verification"}:
            return _NATIVE_BUNDLE_MESSAGE
        return _NATIVE_BUNDLE_MESSAGE
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


def _artifact_root() -> Path:
    raw = (os.environ.get("HAM_BUILDER_SOURCE_ARTIFACT_DIR") or "").strip()
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


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
    if fence:
        try:
            parsed = json.loads(fence.group(1))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass
    match = _JSON_OBJECT_RE.search(text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _forbidden_generated_content(text: str) -> bool:
    low = text.lower()
    if "-----begin" in low and "private key" in low:
        return True
    if re.search(r"\bAKIA[0-9A-Z]{16}\b", text):
        return True
    if re.search(r"\b(sk_live_|sk_test_)[0-9a-zA-Z]{8,}\b", text):
        return True
    if "proposal_digest" in low or "base_revision" in low or "registry_v2" in low:
        return True
    return False


def _validate_file_bundle(payload: dict[str, Any]) -> tuple[dict[str, str], str | None]:
    files_raw = payload.get("files")
    if not isinstance(files_raw, dict):
        return {}, "files_not_object"
    out: dict[str, str] = {}
    total = 0
    for raw_path, raw_content in files_raw.items():
        if not isinstance(raw_path, str) or not isinstance(raw_content, str):
            return {}, "file_entry_invalid"
        norm = raw_path.replace("\\", "/").lstrip("/")
        if not norm or ".." in norm.split("/") or not _ALLOWED_PATH_RE.fullmatch(norm):
            return {}, "path_not_allowed"
        body = raw_content
        if not body.strip():
            return {}, "empty_file_content"
        size = len(body.encode("utf-8"))
        if size > _MAX_FILE_BYTES:
            return {}, "file_too_large"
        total += size
        if total > _MAX_TOTAL_TEXT:
            return {}, "bundle_too_large"
        if _forbidden_generated_content(body):
            return {}, "forbidden_content"
        out[norm] = body
        if len(out) > _MAX_FILES:
            return {}, "too_many_files"
    if not out:
        return {}, "empty_files"
    return out, None


def _append_native_build_context(user_prompt: str) -> str:
    prompt = str(user_prompt or "")
    try:
        from src.ham.build_registry.intent import enrich_plan_metadata_with_registry_v2
        from src.ham.build_registry.scaffold_context import resolve_scaffold_context
        from src.ham.builder_kit_router import select_kit_for_prompt

        template_kind = select_kit_for_prompt(prompt)
        metadata = enrich_plan_metadata_with_registry_v2(
            {
                "template_kind": template_kind,
                "originated_from": "ham_native_builder",
            },
            prompt,
        )
        resolved = resolve_scaffold_context(metadata=metadata, template_kind=template_kind)
        if resolved.source == "none" or not resolved.context.strip():
            return prompt
        return f"{prompt}\n\n{resolved.header}\n{resolved.context}"
    except Exception:  # noqa: BLE001 - context is helpful, never required.
        return prompt


def _build_native_messages(user_prompt: str) -> list[dict[str, Any]]:
    enriched = _append_native_build_context(user_prompt)
    system = (
        "You are HAM Native Builder running through Hermes. Output exactly one JSON object "
        "and nothing else. Schema: {\"status\":\"success\", \"summary\":\"...\", "
        "\"files\":{\"path\":\"full UTF-8 file text\"}, \"checks\":[\"...\"]}. "
        "Create a small, runnable Vite + React + TypeScript project. Include complete "
        "source files, not placeholders. Required files include package.json, index.html, "
        "vite.config.ts, src/main.tsx, and at least one app/component file. Do not include "
        "secrets, local URLs, internal ids, provider names, registry metadata, proposal "
        "digests, base revisions, or workflow identifiers."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": enriched},
    ]


def run_hermes_native_build(
    *,
    workspace_id: str,
    project_id: str,
    session_id: str,
    user_prompt: str,
    created_by: str,
    complete_turn: Callable[..., str] | None = None,
) -> dict[str, Any]:
    if not hermes_native_builder_ready():
        logger.info("ham_native_builder_unavailable reason=unconfigured")
        return _native_result(status="unavailable", failure_reason="unconfigured")

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
            "activity_message": "HAM is building natively through Hermes.",
        },
    )
    job = store.mark_import_job_running(import_job_id=job.id, phase="hermes_native_build")

    turn = complete_turn or complete_chat_turn
    try:
        raw = turn(_build_native_messages(user_prompt))
    except GatewayCallError as exc:
        job = store.mark_import_job_failed(
            import_job_id=job.id,
            phase="hermes_native_build",
            error_code="HAM_NATIVE_BUILDER_GATEWAY_ERROR",
            error_message="HAM Native Builder could not reach Hermes.",
        )
        logger.warning(
            "ham_native_builder_failed reason=gateway import_job_id=%s gateway_code=%s",
            job.id,
            exc.code,
        )
        return _native_result(
            status="failed",
            failure_reason="gateway",
            import_job_id=job.id,
        )

    if _looks_like_mock_assistant_text(raw):
        job = store.mark_import_job_failed(
            import_job_id=job.id,
            phase="hermes_native_build",
            error_code="HAM_NATIVE_BUILDER_GATEWAY_MOCK",
            error_message="Mock gateway cannot produce structured native builds.",
        )
        logger.warning(
            "ham_native_builder_failed reason=gateway import_job_id=%s gateway_code=mock",
            job.id,
        )
        return _native_result(
            status="failed",
            failure_reason="gateway",
            import_job_id=job.id,
        )

    payload = _extract_json_object(raw)
    if not payload or str(payload.get("status") or "").strip().lower() != "success":
        job = store.mark_import_job_failed(
            import_job_id=job.id,
            phase="hermes_native_build",
            error_code="HAM_NATIVE_BUILDER_INVALID_RESPONSE",
            error_message="HAM Native Builder did not return a valid file bundle.",
        )
        logger.warning(
            "ham_native_builder_failed reason=bundle import_job_id=%s detail=invalid_response",
            job.id,
        )
        return _native_result(
            status="failed",
            failure_reason="bundle",
            import_job_id=job.id,
        )

    files, err = _validate_file_bundle(payload)
    if err:
        job = store.mark_import_job_failed(
            import_job_id=job.id,
            phase="hermes_native_build",
            error_code="HAM_NATIVE_BUILDER_INVALID_FILES",
            error_message=f"HAM Native Builder file bundle failed validation: {err}.",
        )
        logger.warning(
            "ham_native_builder_failed reason=bundle import_job_id=%s detail=%s",
            job.id,
            err,
        )
        return _native_result(
            status="failed",
            failure_reason="bundle",
            import_job_id=job.id,
        )

    files = ensure_preview_bootstrap_files(files, project_name=user_prompt)
    artifact_verification = verify_builder_scaffold_artifact(
        user_prompt,
        {"template": "hermes_native"},
        files,
        "build_or_create",
    )
    if not artifact_verification.get("verified"):
        job = store.mark_import_job_failed(
            import_job_id=job.id,
            phase="hermes_native_build",
            error_code="HAM_NATIVE_BUILDER_VERIFY_FAILED",
            error_message="HAM Native Builder output did not pass verification.",
        )
        logger.warning(
            "ham_native_builder_failed reason=verification import_job_id=%s",
            job.id,
        )
        return _native_result(
            status="failed",
            failure_reason="verification",
            import_job_id=job.id,
            extra={"artifact_verification": artifact_verification},
        )

    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode("utf-8")).hexdigest()
    artifact_uri, zip_size = _materialize_inline_files_as_zip_artifact(
        workspace_id=workspace_id,
        project_id=project_id,
        files=files,
    )
    entries_manifest: list[dict[str, Any]] = []
    total_bytes = 0
    for path, text in sorted(files.items()):
        size = len(text.encode("utf-8"))
        total_bytes += size
        entries_manifest.append({"path": path, "size_bytes": size})

    source = ProjectSource(
        workspace_id=workspace_id,
        project_id=project_id,
        kind="ham_native_builder",
        status="ready",
        display_name="HAM Native Builder",
        origin_ref="ham_native",
        created_by=created_by,
        metadata={"native_builder": "hermes"},
    )
    source = store.upsert_project_source(source)
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
            "inline_files": files,
        },
        created_by=created_by,
        metadata={
            "native_builder": "hermes",
            "import_job_id": job.id,
            "chat_scaffold_operation": "build_or_create",
        },
    )
    snapshot = store.upsert_source_snapshot(snapshot)
    source.active_snapshot_id = snapshot.id
    source = store.upsert_project_source(source)
    job = store.mark_import_job_succeeded(
        import_job_id=job.id,
        phase="materialized",
        source_snapshot_id=snapshot.id,
        stats={"file_count": len(files), "inline_bytes": total_bytes, "artifact_zip_bytes": zip_size},
    )

    preview_meta = maybe_enqueue_chat_scaffold_cloud_runtime_job(
        workspace_id=workspace_id,
        project_id=project_id,
        source_snapshot_id=snapshot.id,
        session_id=session_id,
        requested_by=created_by,
    )
    return {
        "builder_intent": "build_or_create",
        "builder_operation": "build_or_create",
        "scaffolded": True,
        "project_source_id": source.id,
        "source_snapshot_id": snapshot.id,
        "import_job_id": job.id,
        "artifact_verification": artifact_verification,
        "ham_native_builder": {"status": "succeeded"},
        **preview_meta,
    }


__all__ = [
    "ham_native_builder_user_message",
    "hermes_native_builder_ready",
    "run_hermes_native_build",
]
