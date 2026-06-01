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
import threading
import uuid
import zipfile
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from src.ham.builder_artifact_verifier import verify_builder_scaffold_artifact
from src.ham.builder_chat_cloud_runtime import maybe_enqueue_chat_scaffold_cloud_runtime_job
from src.ham.builder_preview_bootstrap import ensure_preview_bootstrap_files
from src.integrations.nous_gateway_client import (
    GatewayCallError,
    builder_artifact_model_override,
    complete_artifact_turn,
)
from src.persistence.builder_source_store import (
    NativeBuildContext,
    ProjectSource,
    SourceSnapshot,
    get_builder_source_store,
)

_MANIFEST_KIND_INLINE = "inline_text_bundle"
# Keep the first native bundle minimal so a conversational gateway can finish well
# within the request budget; richer files are added by later iterative edits, not
# the initial build. (See artifact-timeout mitigation: smaller bundle => faster turn.)
_MAX_FILES = 16
_MAX_FILE_BYTES = 80_000
_MAX_TOTAL_TEXT = 150_000
# Hermes is a conversational agent driven as a CLI-like multi-step builder: one
# initial generate turn plus up to two bounded repair turns that re-ask for a
# JSON-only artifact, fed a focused (safe) summary of why the prior reply failed
# validation / verification. Kept small so the whole loop stays within budget.
_NATIVE_BUILD_MAX_ATTEMPTS = 3
_REPAIR_MAX_PREVIOUS_CHARS = 8_000
_FAILURE_STATUS_VALUES = frozenset({"error", "failed", "failed_validation", "unsupported"})
_ALLOWED_PATH_RE = re.compile(
    r"^(?:package\.json|index\.html|vite\.config\.(?:ts|js)|"
    r"postcss\.config\.(?:js|cjs|mjs)|eslint\.config\.(?:js|cjs|mjs)|"
    r"tsconfig(?:\.\w+)?\.json|"
    r"src/[\w./-]+\.(?:tsx|ts|d\.ts|jsx|js|css|json|svg)|public/[\w./-]+)$"
)

logger = logging.getLogger(__name__)

_NATIVE_UNAVAILABLE_MESSAGE = "HAM Native Builder is not ready yet.\n\n"
_NATIVE_UNCONFIGURED_MESSAGE = "HAM Native Builder is still being configured.\n\n"
_NATIVE_GATEWAY_MESSAGE = "HAM Native Builder could not reach the Hermes runtime.\n\n"
_NATIVE_BUNDLE_MESSAGE = "HAM Native Builder could not prepare the project files.\n\n"
_NATIVE_STARTED_MESSAGE = (
    "HAM started the native build. I'll prepare the Workbench preview on the right as it runs.\n\n"
)


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
    if status == "started":
        return _NATIVE_STARTED_MESSAGE
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


def _iter_balanced_json_objects(text: str) -> Iterator[str]:
    """Yield top-level brace-balanced ``{...}`` spans, ignoring braces in strings.

    Conversational replies often wrap the bundle in prose; a greedy regex would
    span from the first ``{`` to the last ``}`` and fail to parse. Scanning for
    balanced objects lets us recover the real JSON artifact from chatter.
    """
    depth = 0
    start = -1
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start >= 0:
                yield text[start : i + 1]
                start = -1


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
    if fence:
        try:
            parsed = json.loads(fence.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    # Prefer a prose-embedded object that actually carries a files map; fall back
    # to the first parseable object otherwise.
    fallback: dict[str, Any] | None = None
    for candidate in _iter_balanced_json_objects(text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        if isinstance(parsed.get("files"), dict):
            return parsed
        if fallback is None:
            fallback = parsed
    return fallback


def _coerce_file_path(raw_path: Any) -> str | None:
    if isinstance(raw_path, str):
        path = raw_path.strip()
        return path or None
    if raw_path is None:
        return None
    path = str(raw_path).strip()
    return path or None


def _coerce_file_content(raw_content: Any) -> str | None:
    """Normalize Hermes file payloads that should be UTF-8 text but often arrive as objects."""
    if isinstance(raw_content, str):
        return raw_content
    if isinstance(raw_content, (bytes, bytearray)):
        return bytes(raw_content).decode("utf-8", errors="replace")
    if isinstance(raw_content, dict):
        for key in ("content", "text", "body", "source"):
            val = raw_content.get(key)
            if isinstance(val, str):
                return val
        try:
            return json.dumps(raw_content, indent=2, ensure_ascii=False) + "\n"
        except (TypeError, ValueError):
            return None
    if isinstance(raw_content, list):
        if raw_content and all(isinstance(item, str) for item in raw_content):
            return "\n".join(raw_content) + "\n"
        try:
            return json.dumps(raw_content, indent=2, ensure_ascii=False) + "\n"
        except (TypeError, ValueError):
            return None
    if isinstance(raw_content, (int, float, bool)):
        return str(raw_content)
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


def _validate_file_bundle(
    payload: dict[str, Any],
) -> tuple[dict[str, str], str | None, int]:
    """Return validated files, error kind (if any), and count of skipped disallowed paths."""
    files_raw = payload.get("files")
    if not isinstance(files_raw, dict):
        return {}, "files_not_object", 0
    out: dict[str, str] = {}
    total = 0
    skipped_paths = 0
    skipped_invalid = 0
    for raw_path, raw_content in files_raw.items():
        path_text = _coerce_file_path(raw_path)
        body = _coerce_file_content(raw_content)
        if path_text is None or body is None:
            skipped_invalid += 1
            continue
        norm = path_text.replace("\\", "/").lstrip("/")
        if not norm or ".." in norm.split("/"):
            return {}, "path_not_allowed", skipped_paths
        if not _ALLOWED_PATH_RE.fullmatch(norm):
            skipped_paths += 1
            continue
        if not body.strip():
            return {}, "empty_file_content", skipped_paths
        size = len(body.encode("utf-8"))
        if size > _MAX_FILE_BYTES:
            return {}, "file_too_large", skipped_paths
        total += size
        if total > _MAX_TOTAL_TEXT:
            return {}, "bundle_too_large", skipped_paths
        if _forbidden_generated_content(body):
            return {}, "forbidden_content", skipped_paths
        out[norm] = body
        if len(out) > _MAX_FILES:
            return {}, "too_many_files", skipped_paths
    if not out:
        if skipped_invalid:
            return {}, "file_entry_invalid", skipped_paths
        return {}, ("path_not_allowed" if skipped_paths else "empty_files"), skipped_paths
    return out, None, skipped_paths


def _response_shape_flags(raw: str) -> tuple[bool, bool]:
    payload = _extract_json_object(raw)
    json_found = isinstance(payload, dict)
    files_found = json_found and isinstance(payload.get("files"), dict)
    return json_found, files_found


def _coerce_files_from_response(raw: str) -> tuple[dict[str, str], str | None]:
    """Recover a validated file bundle from a (possibly conversational) reply.

    Hermes stays conversational to the user elsewhere; here the project-file
    artifact is private backend output, so we tolerate prose-wrapped JSON and a
    missing/loose ``status`` field as long as a valid ``files`` map is present.
    An explicit failure status is still rejected.
    """
    payload = _extract_json_object(raw)
    if not isinstance(payload, dict):
        return {}, "invalid_response"
    status = str(payload.get("status") or "").strip().lower()
    if status in _FAILURE_STATUS_VALUES:
        return {}, "invalid_response"
    files, err, _skipped = _validate_file_bundle(payload)
    return files, err


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
        "Create the SMALLEST runnable Vite + React + TypeScript project that satisfies the "
        "request: aim for about 6-10 files total and keep source compact so it builds "
        "quickly; this is a first preview that can be enhanced by later edits. Include "
        "complete source files, not placeholders. Required files include package.json, "
        "index.html, vite.config.ts, src/main.tsx, and at least one app/component file. "
        "Prefer a single App component over many components for this first version. Use paths only "
        "under package.json, index.html, vite.config.ts, tsconfig*.json, src/**, or public/** "
        "(no README, .env, or repo-root components/ paths). Do not include secrets, local URLs, "
        "internal ids, provider names, registry metadata, proposal digests, base revisions, or "
        "workflow identifiers."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": enriched},
    ]


# Safe, generic guidance per validation failure class (no internals / secrets /
# provider or registry references) fed back to Hermes on the next repair turn.
_REPAIR_SUMMARY_BY_KIND: dict[str, str] = {
    "invalid_response": "Your previous reply was not a single valid JSON object.",
    "files_not_object": "The 'files' field must be a JSON object mapping each path to its full file text.",
    "path_not_allowed": "Some file paths were not allowed.",
    "empty_file_content": "Some files were empty; include complete file contents.",
    "empty_files": "No usable files were produced; include complete runnable source files.",
    "file_entry_invalid": "Each file entry must map a string path to string file contents.",
    "file_too_large": "A file was too large; keep each file compact.",
    "bundle_too_large": "The project was too large; produce a small app of about 6-10 compact files.",
    "too_many_files": "Too many files; produce about 6-10 files total.",
    "forbidden_content": "Remove secrets, local URLs, internal ids, provider names, or metadata from the files.",
}


def _repair_summary_for_bundle(detail: str) -> str:
    return _REPAIR_SUMMARY_BY_KIND.get(
        detail, "Your previous reply could not be parsed into a valid file bundle."
    )


def _repair_summary_for_verification(verification: dict[str, Any]) -> str:
    # Deliberately generic: the raw verifier reason can reference config/provider
    # concepts, so never echo it back to the model or the user.
    return (
        "The generated project did not pass verification; ensure it is a complete, "
        "runnable Vite + React + TypeScript app."
    )


def _build_repair_messages(
    base_messages: list[dict[str, Any]],
    *,
    previous_raw: str,
    error_summary: str | None = None,
) -> list[dict[str, Any]]:
    """Re-ask Hermes for a JSON-only artifact, feeding back its prior (bounded) reply.

    This is a real next model turn (no faked execution); the prior reply is capped
    so the repair prompt stays bounded, ``error_summary`` is a safe, focused note on
    why the previous attempt failed (validation / verification class only, never
    internals), and the artifact never reaches the user.
    """
    prev = str(previous_raw or "")
    if len(prev) > _REPAIR_MAX_PREVIOUS_CHARS:
        prev = prev[:_REPAIR_MAX_PREVIOUS_CHARS]
    focus = (error_summary or "").strip()
    if not focus:
        focus = "Your previous reply could not be used as a runnable project."
    repair = (
        f"{focus} Reply again with EXACTLY one JSON object and nothing else: no prose, no "
        'markdown, no code fences. Schema: {"status":"success","summary":"...",'
        '"files":{"path":"full UTF-8 file text"},"checks":["..."]}. Include complete runnable '
        "files: package.json, index.html, vite.config.ts, src/main.tsx, and at least one "
        "app/component file. Use paths only under package.json, index.html, vite.config.ts, "
        "tsconfig*.json, src/**, or public/**. Do not include secrets, local URLs, internal ids, "
        "provider names, registry metadata, proposal digests, base revisions, or workflow identifiers."
    )
    return [
        *base_messages,
        {"role": "assistant", "content": prev},
        {"role": "user", "content": repair},
    ]


def _bundle_failure_error_code(bundle_detail: str) -> str:
    if bundle_detail == "invalid_response":
        return "HAM_NATIVE_BUILDER_INVALID_RESPONSE"
    return "HAM_NATIVE_BUILDER_INVALID_FILES"


def _validate_bootstrap_verify(
    raw: str, *, user_prompt: str
) -> tuple[dict[str, str] | None, str, str | None, dict[str, Any]]:
    """Validate -> preview-bootstrap -> verify one generated reply.

    Returns ``(files, failure_kind, repair_summary, verification)``. On success
    ``files`` is the normalized bundle and ``failure_kind`` is empty; otherwise
    ``files`` is ``None``, ``failure_kind`` is ``"bundle:<detail>"`` or
    ``"verification"``, and ``repair_summary`` is the safe note to feed the next
    repair turn.
    """
    candidate_files, bundle_detail = _coerce_files_from_response(raw)
    if bundle_detail is not None:
        return None, f"bundle:{bundle_detail}", _repair_summary_for_bundle(bundle_detail), {}
    candidate_files = ensure_preview_bootstrap_files(candidate_files, project_name=user_prompt)
    verification = verify_builder_scaffold_artifact(
        user_prompt, {"template": "hermes_native"}, candidate_files, "build_or_create"
    )
    if not verification.get("verified"):
        return None, "verification", _repair_summary_for_verification(verification), verification
    return candidate_files, "", None, verification


def _fail_native_build(
    store: Any,
    *,
    import_job_id: str,
    phase: str,
    error_code: str,
    error_message: str,
    failure_reason: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mark the job failed and return the safe, non-internal failure result."""
    store.mark_import_job_failed(
        import_job_id=import_job_id,
        phase=phase,
        error_code=error_code,
        error_message=error_message,
    )
    return _native_result(
        status="failed",
        failure_reason=failure_reason,
        import_job_id=import_job_id,
        extra=extra,
    )


def _native_build_preflight(
    complete_turn: Callable[..., str] | None,
) -> tuple[bool, dict[str, Any] | None]:
    """Return ``(builder_model_configured, early_result)`` for native build gating.

    Combines two fail-fast checks so the caller keeps a single early-return branch:
    (1) the gateway must be configured (``hermes_native_builder_ready``); (2) a dedicated
    fast artifact model/profile (``HERMES_BUILDER_MODEL``) must be set on the real gateway
    path — the conversational chat model is too slow to emit a full file bundle inside the
    request budget and would time out (``UPSTREAM_TIMEOUT``). When either is missing, return
    the safe "still being configured" result and fail fast instead of burning the budget.
    Tests/programmatic callers that inject their own turn bypass the model gate.
    """
    builder_model_configured = builder_artifact_model_override() is not None
    if not hermes_native_builder_ready():
        logger.info("ham_native_builder_unavailable reason=unconfigured")
        return builder_model_configured, _native_result(
            status="unavailable", failure_reason="unconfigured"
        )
    if complete_turn is None and not builder_model_configured:
        logger.warning(
            "ham_native_builder_unavailable reason=builder_model_unconfigured "
            "builder_model_configured=false",
        )
        return builder_model_configured, _native_result(
            status="unavailable", failure_reason="unconfigured"
        )
    return builder_model_configured, None


def run_hermes_native_build(
    *,
    workspace_id: str,
    project_id: str,
    session_id: str,
    user_prompt: str,
    created_by: str,
    complete_turn: Callable[..., str] | None = None,
) -> dict[str, Any]:
    builder_model_configured, early_result = _native_build_preflight(complete_turn)
    if early_result is not None:
        return early_result

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
    return _execute_native_build_core(
        import_job_id=job.id,
        workspace_id=workspace_id,
        project_id=project_id,
        session_id=session_id,
        user_prompt=user_prompt,
        created_by=created_by,
        complete_turn=complete_turn,
        builder_model_configured=builder_model_configured,
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
    complete_turn: Callable[..., str] | None,
    builder_model_configured: bool,
    running_phase: str,
    success_phase: str,
    failure_phase: str,
    generating_phase: str | None = None,
    validating_phase: str | None = None,
    repairing_phase: str | None = None,
    materializing_phase: str | None = None,
    preview_phase: str | None = None,
) -> dict[str, Any]:
    """Run the bounded multi-step Hermes native build loop against an existing job.

    Shared by the synchronous one-shot path (`run_hermes_native_build`) and the
    async v2 executor (`execute_native_build_job`); only the lifecycle phase labels
    differ. Marks the job running, then loops up to `_NATIVE_BUILD_MAX_ATTEMPTS`
    times: generate via the private artifact channel -> validate/normalize ->
    preview-bootstrap -> verify; on a validation/verification failure it runs a real
    repair turn fed a focused, safe error summary, and only after exhausting attempts
    does it fail. On success it materializes the source snapshot the Workbench
    understands, starts the preview runtime, and marks the job succeeded. The
    granular phases (`generating`/`validating`/`repairing`/`materializing`/
    `preview`) are persisted only when supplied (v2); the synchronous path leaves
    them `None` and stays on its coarse `running_phase`. Build Registry v2 / kit
    context is applied invisibly via `_build_native_messages`; logs carry only safe
    diagnostics (no raw model output or file contents); no internals reach callers.
    """
    store = get_builder_source_store()
    store.mark_import_job_running(import_job_id=import_job_id, phase=running_phase)
    current_phase = running_phase

    def _advance(phase: str | None) -> None:
        """Persist a granular phase transition (v2); a no-op when phase is unset/unchanged."""
        nonlocal current_phase
        if phase and phase != current_phase:
            store.mark_import_job_running(import_job_id=import_job_id, phase=phase)
            current_phase = phase

    # Private artifact channel: a JSON-mode build request, distinct from the
    # user-facing conversational chat. Tests may inject a plain text producer.
    gateway_diag: dict[str, Any] = {}
    injected = complete_turn is not None
    if injected:
        turn = complete_turn
    else:

        def turn(msgs: list[dict[str, Any]]) -> str:
            return complete_artifact_turn(msgs, diag=gateway_diag)

    base_messages = _build_native_messages(user_prompt)

    files: dict[str, str] = {}
    verification: dict[str, Any] = {}
    failure_kind = ""
    repair_summary: str | None = None
    raw = ""
    repair_attempted = False
    first_json_found = False
    first_files_found = False
    repair_json_found = False
    repair_files_found = False
    validation_error_kind = ""
    for attempt in range(_NATIVE_BUILD_MAX_ATTEMPTS):
        if attempt == 0:
            _advance(generating_phase)
            messages = base_messages
        else:
            repair_attempted = True
            _advance(repairing_phase)
            messages = _build_repair_messages(
                base_messages, previous_raw=raw, error_summary=repair_summary
            )

        try:
            raw = turn(messages)
        except GatewayCallError as exc:
            logger.warning(
                "ham_native_builder_failed reason=gateway import_job_id=%s gateway_code=%s "
                "artifact_mode=%s artifact_transport=%s model_channel=%s "
                "builder_model_configured=%s elapsed_ms=%s attempt=%d repair_attempted=%s",
                import_job_id,
                exc.code,
                gateway_diag.get("artifact_mode") or "json_mode",
                gateway_diag.get("artifact_transport") or "unknown",
                gateway_diag.get("model_channel") or ("injected" if injected else "default"),
                str(builder_model_configured).lower(),
                gateway_diag.get("elapsed_ms") if gateway_diag.get("elapsed_ms") is not None else "n/a",
                attempt + 1,
                repair_attempted,
            )
            return _fail_native_build(
                store,
                import_job_id=import_job_id,
                phase=failure_phase,
                error_code="HAM_NATIVE_BUILDER_GATEWAY_ERROR",
                error_message="HAM Native Builder could not reach Hermes.",
                failure_reason="gateway",
            )

        if _looks_like_mock_assistant_text(raw):
            logger.warning(
                "ham_native_builder_failed reason=gateway import_job_id=%s gateway_code=mock attempt=%d",
                import_job_id,
                attempt + 1,
            )
            return _fail_native_build(
                store,
                import_job_id=import_job_id,
                phase=failure_phase,
                error_code="HAM_NATIVE_BUILDER_GATEWAY_MOCK",
                error_message="Mock gateway cannot produce structured native builds.",
                failure_reason="gateway",
            )

        json_found, files_found = _response_shape_flags(raw)
        if attempt == 0:
            first_json_found = json_found
            first_files_found = files_found
        else:
            repair_json_found = json_found
            repair_files_found = files_found

        _advance(validating_phase)
        candidate_files, failure_kind, repair_summary, verification = _validate_bootstrap_verify(
            raw, user_prompt=user_prompt
        )
        if not failure_kind:
            files = candidate_files or {}
            break
        validation_error_kind = (
            failure_kind.split(":", 1)[1] if failure_kind.startswith("bundle:") else failure_kind
        )
        logger.info(
            "ham_native_builder_repair_attempt import_job_id=%s attempt=%d failure_class=%s "
            "validation_error_kind=%s artifact_mode=%s artifact_transport=%s",
            import_job_id,
            attempt + 1,
            failure_kind.split(":", 1)[0],
            validation_error_kind,
            gateway_diag.get("artifact_mode") or ("injected" if injected else "unavailable"),
            gateway_diag.get("artifact_transport") or "unknown",
        )

    if not files:
        if failure_kind == "verification":
            logger.warning(
                "ham_native_builder_failed reason=verification import_job_id=%s attempts=%d",
                import_job_id,
                _NATIVE_BUILD_MAX_ATTEMPTS,
            )
            return _fail_native_build(
                store,
                import_job_id=import_job_id,
                phase=failure_phase,
                error_code="HAM_NATIVE_BUILDER_VERIFY_FAILED",
                error_message="HAM Native Builder output did not pass verification.",
                failure_reason="verification",
                extra={"artifact_verification": verification},
            )
        detail = validation_error_kind or "invalid_response"
        logger.warning(
            "ham_native_builder_failed reason=bundle import_job_id=%s detail=%s "
            "first_attempt_json_found=%s first_attempt_files_found=%s repair_attempted=%s "
            "repair_json_found=%s repair_files_found=%s validation_error_kind=%s "
            "artifact_mode=%s artifact_transport=%s gateway_capability_detected=%s model_channel=%s "
            "builder_model_configured=%s attempts=%d",
            import_job_id,
            detail,
            first_json_found,
            first_files_found,
            repair_attempted,
            repair_json_found,
            repair_files_found,
            validation_error_kind or detail,
            gateway_diag.get("artifact_mode") or ("injected" if injected else "unavailable"),
            gateway_diag.get("artifact_transport") or "unknown",
            gateway_diag.get("gateway_capability_detected") or "unknown",
            gateway_diag.get("model_channel") or "default",
            str(builder_model_configured).lower(),
            _NATIVE_BUILD_MAX_ATTEMPTS,
        )
        return _fail_native_build(
            store,
            import_job_id=import_job_id,
            phase=failure_phase,
            error_code=_bundle_failure_error_code(detail),
            error_message=f"HAM Native Builder did not return a valid file bundle: {detail}.",
            failure_reason="bundle",
        )

    artifact_verification = verification
    _advance(materializing_phase)
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
            "import_job_id": import_job_id,
            "chat_scaffold_operation": "build_or_create",
        },
    )
    snapshot = store.upsert_source_snapshot(snapshot)
    source.active_snapshot_id = snapshot.id
    source = store.upsert_project_source(source)

    # Preview is best-effort and must never undo a real, materialized build, so it
    # runs (guarded) before the terminal success transition.
    _advance(preview_phase)
    try:
        preview_meta = maybe_enqueue_chat_scaffold_cloud_runtime_job(
            workspace_id=workspace_id,
            project_id=project_id,
            source_snapshot_id=snapshot.id,
            session_id=session_id,
            requested_by=created_by,
        )
    except Exception:  # noqa: BLE001 - never fail a finished build on preview enqueue.
        logger.warning("ham_native_builder_preview_enqueue_failed import_job_id=%s", import_job_id)
        preview_meta = {}

    store.mark_import_job_succeeded(
        import_job_id=import_job_id,
        phase=success_phase,
        source_snapshot_id=snapshot.id,
        stats={"file_count": len(files), "inline_bytes": total_bytes, "artifact_zip_bytes": zip_size},
    )
    logger.info(
        "ham_native_builder_succeeded import_job_id=%s file_count=%d "
        "artifact_mode=%s artifact_transport=%s elapsed_ms=%s "
        "gateway_capability_detected=%s model_channel=%s builder_model_configured=%s "
        "first_attempt_json_found=%s first_attempt_files_found=%s repair_attempted=%s",
        import_job_id,
        len(files),
        gateway_diag.get("artifact_mode") or ("injected" if injected else "unavailable"),
        gateway_diag.get("artifact_transport") or "unknown",
        gateway_diag.get("elapsed_ms") if gateway_diag.get("elapsed_ms") is not None else "n/a",
        gateway_diag.get("gateway_capability_detected") or "unknown",
        gateway_diag.get("model_channel") or "default",
        str(builder_model_configured).lower(),
        first_json_found,
        first_files_found,
        repair_attempted,
    )
    return {
        "builder_intent": "build_or_create",
        "builder_operation": "build_or_create",
        "scaffolded": True,
        "project_source_id": source.id,
        "source_snapshot_id": snapshot.id,
        "import_job_id": import_job_id,
        "artifact_verification": artifact_verification,
        "ham_native_builder": {"status": "succeeded"},
        **preview_meta,
    }


# ---------------------------------------------------------------------------
# HAM Native Builder v2 — async job boundary + functional executor
#
# The synchronous path (`run_hermes_native_build`) generates a full file bundle
# in one Hermes turn inside the `/api/chat/stream` request, which exceeds the
# request budget with a conversational gateway and times out. v2 splits the work:
# `start_native_build_job` persists a job and returns immediately; the executor
# (`execute_native_build_job`) runs off the request path via the dispatcher and is
# independently invocable so a future out-of-process worker (Cloud Tasks -> worker
# endpoint, or a Cloud Run Job) can run it by job id.
#
# The executor drives a bounded multi-step generate/validate/repair loop on the
# existing job by delegating to `_execute_native_build_core` (shared with the
# synchronous path), persisting granular phases as it progresses.
#
# The job is the existing ImportJob record tagged with a native-builder origin,
# so status is already pollable via the import-jobs status endpoint. No build-kit
# internals, raw JSON, env names, provider ids, digests, or secrets are exposed.
# ---------------------------------------------------------------------------

# Native-build lifecycle phases stored on the reused `ImportJob.phase` (free-form
# strings; no change to the shared store schema or its status enum).
NATIVE_BUILD_PHASE_QUEUED = "native_build_queued"
NATIVE_BUILD_PHASE_RUNNING = "native_build_running"
NATIVE_BUILD_PHASE_GENERATING = "native_build_generating"
NATIVE_BUILD_PHASE_VALIDATING = "native_build_validating"
NATIVE_BUILD_PHASE_REPAIRING = "native_build_repairing"
NATIVE_BUILD_PHASE_MATERIALIZING = "native_build_materializing"
NATIVE_BUILD_PHASE_PREVIEW_STARTING = "native_build_preview_starting"
NATIVE_BUILD_PHASE_SUCCEEDED = "native_build_succeeded"
NATIVE_BUILD_PHASE_FAILED = "native_build_failed"

# Product-level origin tag (never a build-kit internal / provider id) marking the
# reused import job as a native-builder v2 record. Surfaced via the status API.
NATIVE_BUILD_JOB_ORIGIN = "ham_native_builder_v2"

# Safe outcome when the executor crashes unexpectedly (defense-in-depth; known
# gateway/bundle/verification failures are already marked inside the core).
_EXECUTOR_ERROR_CODE = "HAM_NATIVE_BUILDER_V2_EXECUTOR_ERROR"
_EXECUTOR_ERROR_MESSAGE = "HAM Native Builder could not complete the native build."

_DISPATCH_ENV = "HAM_NATIVE_BUILD_DISPATCH"


def _native_build_dispatch_mode() -> str:
    """Return the dispatch mode: ``durable`` (default), ``inline``, or ``thread``.

    ``durable`` hands the persisted job id to the out-of-process enqueue seam
    (:mod:`src.ham.native_build_worker_enqueue`) instead of running the build in
    the request: with ``HAM_NATIVE_BUILD_DISPATCH=cloud_tasks`` it pushes a task to
    the authenticated worker endpoint; otherwise the no-op backend leaves the job
    queued (pollable) for a worker to drive. This is the default because a
    request-scoped Cloud Run container throttles CPU after the response, so a
    daemon thread is not durable for a multi-second Hermes build.

    ``inline`` runs the executor synchronously and ``thread`` on a daemon thread —
    both in-process and intended only for tests / local dev, never as the hosted
    default.
    """
    raw = (os.environ.get(_DISPATCH_ENV) or "").strip().lower()
    return raw if raw in {"inline", "thread"} else "durable"


def start_native_build_job(
    *,
    workspace_id: str,
    project_id: str,
    session_id: str,
    user_prompt: str,
    created_by: str,
    complete_turn: Callable[..., str] | None = None,
) -> dict[str, Any]:
    """Create a native build job and return immediately.

    Never generates the artifact bundle inline (that is the executor's job, run
    off the request path). On a misconfigured gateway / missing builder model the
    cheap preflight returns the same safe "unavailable" result the synchronous
    path used and no job is created; otherwise a queued job is persisted,
    dispatched to the executor, and a "started" result is returned.
    """
    builder_model_configured, early_result = _native_build_preflight(complete_turn)
    if early_result is not None:
        return early_result

    store = get_builder_source_store()
    job = store.create_import_job(
        workspace_id=workspace_id,
        project_id=project_id,
        created_by=created_by,
        phase=NATIVE_BUILD_PHASE_QUEUED,
        status="queued",
        metadata={"origin": NATIVE_BUILD_JOB_ORIGIN},
    )
    # Persist enough context (keyed by job id) for an out-of-process worker to run
    # the build without any in-memory thread state. Stored server-side only; never
    # surfaced through the import-jobs status API.
    store.put_native_build_context(
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
        "ham_native_builder_v2_started import_job_id=%s dispatch=%s builder_model_configured=%s",
        job.id,
        _native_build_dispatch_mode(),
        str(builder_model_configured).lower(),
    )
    _dispatch_native_build_job(
        import_job_id=job.id,
        workspace_id=workspace_id,
        project_id=project_id,
        session_id=session_id,
        user_prompt=user_prompt,
        created_by=created_by,
        complete_turn=complete_turn,
    )
    return _native_result(
        status="started",
        scaffolded=False,
        import_job_id=job.id,
        extra={"native_build_job_id": job.id},
    )


def _dispatch_native_build_job(**kwargs: Any) -> None:
    """Async boundary: hand the persisted job off to the executor / worker.

    Dispatch failures never escape into the chat turn — the job and its durable
    context are already persisted, so a crash here is logged and (for in-process
    modes) the job is marked failed; the durable path leaves the job queued for a
    worker / retry.
    """
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
    """Durable dispatch: enqueue the job for out-of-process execution.

    A misconfigured / unavailable backend never breaks the chat turn — the job and
    its context are persisted, so the job simply stays queued (pollable) for a
    worker or a retry to pick up. We deliberately do not mark it failed here: an
    enqueue/config error is recoverable, unlike a build failure.
    """
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
    complete_turn: Callable[..., str] | None = None,
) -> dict[str, Any]:
    """Functional native build executor — the independently invocable entry point.

    Runs off the chat request (via the dispatcher) and drives the bounded multi-step
    Hermes loop against the already-created job: marks it running, then generates ->
    validates/normalizes -> preview-bootstraps -> verifies, running a real repair turn
    (fed a focused, safe error summary) on failure for up to `_NATIVE_BUILD_MAX_ATTEMPTS`
    attempts before failing. Build Registry v2 / kit context is applied invisibly. On
    success it materializes the source snapshot, starts the preview runtime, and marks
    the job succeeded; otherwise it marks a safe failure. It persists the granular
    native-build phases as it progresses, never re-enables the old scaffold, and never
    fakes success.

    A durable out-of-process worker (Cloud Tasks -> worker endpoint, or a Cloud Run
    Job) calls this by job id.
    """
    builder_model_configured = builder_artifact_model_override() is not None
    logger.info(
        "ham_native_builder_v2_executor_start import_job_id=%s builder_model_configured=%s",
        import_job_id,
        str(builder_model_configured).lower(),
    )
    return _execute_native_build_core(
        import_job_id=import_job_id,
        workspace_id=workspace_id,
        project_id=project_id,
        session_id=session_id,
        user_prompt=user_prompt,
        created_by=created_by,
        complete_turn=complete_turn,
        builder_model_configured=builder_model_configured,
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
