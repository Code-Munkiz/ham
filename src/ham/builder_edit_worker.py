"""Builder Edit Worker v1 — Hermes gateway (complete_chat_turn) for long-tail snapshot edits."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable

from src.ham.builder_chat_cloud_runtime import maybe_enqueue_chat_scaffold_cloud_runtime_job
from src.ham.builder_chat_scaffold import materialize_inline_files_as_zip_artifact
from src.ham.builder_mutation_router import (
    BuilderActionDecision,
    builder_edit_worker_eligible,
    classify_builder_project_action,
    resolve_snapshot_project_template,
)
from src.integrations.nous_gateway_client import GatewayCallError, complete_chat_turn
from src.persistence.builder_source_store import (
    ImportJob,
    ProjectSource,
    SourceSnapshot,
    get_builder_source_store,
)

DEFAULT_BUILDER_CODE_WORKER = "hermes_gateway"
BUILDER_CODE_WORKER_META_KEY = "builder_code_worker"
_MANIFEST_KIND_INLINE = "inline_text_bundle"
_EDIT_MAX_FILE_BYTES = 60_000
_EDIT_MAX_TOTAL_TEXT = 200_000
_NEW_WORKER_SRC_PATH = re.compile(r"^src/[\w./-]+\.(?:tsx|ts|jsx|js|css)$")
_CURRENT_FILES_JSON_BUDGET = 95_000
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _gateway_mode_allows_live_edit() -> bool:
    raw = (os.environ.get("HERMES_GATEWAY_MODE") or "").strip().lower()
    if raw == "mock":
        return False
    if raw in {"http", "openrouter"}:
        return True
    base = (os.environ.get("HERMES_GATEWAY_BASE_URL") or "").strip()
    return bool(base)


def is_operator_plus_minus_blue_purple_border_edit(user_plain: str) -> bool:
    """Known long-tail: + and - operator buttons, blue fill, purple border."""
    text = str(user_plain or "").strip()
    if not text:
        return False
    low = " ".join(text.replace("\r", " ").replace("\n", " ").split()).lower()
    if "button" not in low:
        return False
    if not re.search(r"\+", text) and not re.search(r"\bplus\b", low):
        return False
    has_minus = bool(re.search(r"\bminus\b", low) or re.search(r"\+\s+and\s+-\s+", text) or re.search(r"\+\s*-\s+button", low))
    if not has_minus:
        return False
    if not re.search(r"\bblue\b", low):
        return False
    if not re.search(r"\bpurple\b", low):
        return False
    if not re.search(r"\bborder\b", low) and not re.search(r"\bring\b", low):
        return False
    return True


def needs_hermes_gateway_edit_path(user_plain: str, *, active_template: str | None = "calculator") -> bool:
    """True when the Hermes edit worker would run for this prompt (tests + diagnostics)."""
    decision = classify_builder_project_action(
        user_plain,
        has_active_snapshot=True,
        active_template=active_template,
    )
    return builder_edit_worker_eligible(
        user_plain,
        decision=decision,
        active_template=active_template,
    )


def _worker_patch_path_allowed(norm: str, baseline: dict[str, str]) -> bool:
    if norm in baseline:
        return True
    return bool(_NEW_WORKER_SRC_PATH.fullmatch(norm))


def _worker_current_files_payload(baseline: dict[str, str]) -> dict[str, str]:
    """Bounded JSON payload of current snapshot text files for the gateway."""
    budget = _CURRENT_FILES_JSON_BUDGET
    out: dict[str, str] = {}
    used = 0
    for key in ("src/App.tsx", "src/styles.css"):
        if key not in baseline:
            continue
        raw = baseline[key]
        n = len(raw.encode("utf-8"))
        if used + n > budget:
            continue
        out[key] = raw
        used += n
    for key in sorted(baseline.keys()):
        if key in out:
            continue
        raw = baseline[key]
        n = len(raw.encode("utf-8"))
        if used + n > budget:
            continue
        out[key] = raw
        used += n
    return out


def resolve_effective_builder_worker_id(project_source: ProjectSource | None) -> str:
    raw = ""
    if project_source is not None:
        raw = str((project_source.metadata or {}).get(BUILDER_CODE_WORKER_META_KEY) or "").strip()
    return raw if raw else DEFAULT_BUILDER_CODE_WORKER


@dataclass
class WorkerDirectiveResult:
    cleaned_prompt: str
    assistant_note: str | None
    blocked_reason: str | None
    updated_source: ProjectSource | None


def apply_builder_worker_chat_directives(
    *,
    last_user_plain: str,
    project_source: ProjectSource | None,
    store: Any,
) -> WorkerDirectiveResult:
    """
    Strip supported worker directives from the user message; persist preferences on ProjectSource.

    Returns cleaned_prompt for the rest of the builder flow. assistant_note is set when the message
    was only a directive acknowledgement.
    """
    text = str(last_user_plain or "").strip()
    if not text:
        return WorkerDirectiveResult(text, None, None, None)

    lines = text.splitlines()
    kept: list[str] = []
    notes: list[str] = []
    blocked: str | None = None
    src = project_source

    line_re = re.compile(
        r"^\s*(?P<body>use\s+(?P<who>hermes|cursor|opencode|factory|droid)\s+"
        r"(?:for\s+)?(?:this\s+)?(?:app|project|builder|task)\s*\.?\s*)\s*$",
        re.IGNORECASE,
    )
    switch_re = re.compile(
        r"^\s*(switch\s+back\s+to\s+(?:the\s+)?default\s+worker|use\s+default\s+worker)\s*\.?\s*$",
        re.IGNORECASE,
    )

    for line in lines:
        m_sw = switch_re.match(line)
        if m_sw:
            if src is not None:
                meta = dict(src.metadata or {})
                meta[BUILDER_CODE_WORKER_META_KEY] = DEFAULT_BUILDER_CODE_WORKER
                src = src.model_copy(update={"metadata": meta, "updated_at": _utc_now()})
                src = store.upsert_project_source(src)
                notes.append("Restored default builder code worker (Hermes gateway).")
            else:
                notes.append(
                    "Default builder worker is Hermes gateway once a builder source exists for this project."
                )
            continue
        m = line_re.match(line)
        if m:
            who = str(m.group("who") or "").strip().lower()
            if who == "hermes":
                if src is not None:
                    meta = dict(src.metadata or {})
                    meta[BUILDER_CODE_WORKER_META_KEY] = "hermes_gateway"
                    src = src.model_copy(update={"metadata": meta, "updated_at": _utc_now()})
                    src = store.upsert_project_source(src)
                    notes.append("Saved builder code worker: Hermes gateway.")
                else:
                    notes.append(
                        "Create or open a builder project source first; then you can save the Hermes gateway worker."
                    )
            else:
                blocked = who
                notes.append(f"The {who!r} builder worker is not available for chat edits yet.")
            continue
        kept.append(line)

    cleaned = "\n".join(kept).strip()
    assistant_note = None
    if notes and not cleaned:
        assistant_note = "\n\n".join(notes) + "\n\n"
    elif notes and cleaned:
        # Prefix acknowledgement so the user sees preference + edit handled in one turn
        assistant_note = "\n\n".join(notes) + "\n\n"

    return WorkerDirectiveResult(
        cleaned_prompt=cleaned,
        assistant_note=assistant_note,
        blocked_reason=blocked,
        updated_source=src,
    )


def _inline_file_map(snapshot: SourceSnapshot) -> dict[str, str]:
    manifest = snapshot.manifest or {}
    if str(manifest.get("kind") or "") != _MANIFEST_KIND_INLINE:
        return {}
    raw_files = manifest.get("inline_files")
    if not isinstance(raw_files, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw_files.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        norm = key.replace("\\", "/").lstrip("/")
        if not norm or ".." in norm.split("/"):
            continue
        out[norm] = value
    return out


def _append_activity(job: ImportJob, store: Any, step: str, title: str) -> ImportJob:
    meta = dict(job.metadata or {})
    seq = list(meta.get("builder_edit_activity") or [])
    seq.append({"step": step, "title": title, "at": _utc_now()})
    meta["builder_edit_activity"] = seq
    meta["activity_title"] = title
    meta["activity_message"] = title
    updated = job.model_copy(update={"metadata": meta, "updated_at": _utc_now()})
    return store.upsert_import_job(updated)


def _looks_like_mock_assistant_text(text: str) -> bool:
    return "mock assistant reply" in text.lower()


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", s, re.IGNORECASE)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass
    m = _JSON_OBJECT_RE.search(s)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _forbidden_secret_markers(text: str) -> bool:
    low = text.lower()
    if "-----begin" in low and "private key" in low:
        return True
    if "eyj" in low and low.count(".") >= 2 and "bearer" in low:
        return True
    if re.search(r"\bAKIA[0-9A-Z]{16}\b", text):
        return True
    if re.search(r"\b(sk_live_|sk_test_)[0-9a-zA-Z]{8,}\b", text):
        return True
    return False


def _forbidden_internal_urls(text: str) -> bool:
    low = text.lower()
    if "127.0.0.1" in low or "0.0.0.0" in low:
        return True
    if "localhost" in low:
        return True
    if ".internal" in low or ".svc.cluster.local" in low:
        return True
    return False


def _validate_gateway_patch_payload(
    data: dict[str, Any],
    *,
    baseline: dict[str, str],
) -> tuple[dict[str, str], str | None]:
    status = str(data.get("status") or "").strip().lower()
    if status not in {"success", "unsupported", "failed_validation"}:
        return {}, "invalid_status"
    if status != "success":
        return {}, f"worker_status_{status}"
    files_raw = data.get("files")
    if not isinstance(files_raw, dict):
        return {}, "files_not_object"
    out_files: dict[str, str] = {}
    for k, v in files_raw.items():
        if not isinstance(k, str) or not isinstance(v, str):
            return {}, "file_entry_invalid"
        norm = k.replace("\\", "/").lstrip("/")
        if not _worker_patch_path_allowed(norm, baseline):
            return {}, f"path_not_allowed:{norm}"
        if ".." in norm.split("/"):
            return {}, "path_traversal"
        # Reject whitespace-only payloads: non-calculator verify_* only ensures paths exist,
        # so an empty string would otherwise replace real sources and persist a wiped file.
        if not str(v).strip():
            return {}, "empty_file_content"
        if len(v.encode("utf-8")) > _EDIT_MAX_FILE_BYTES:
            return {}, "file_too_large"
        if _forbidden_secret_markers(v) or _forbidden_internal_urls(v):
            return {}, "forbidden_content"
        out_files[norm] = v
    if not out_files:
        return {}, "empty_files"
    total = sum(len(t.encode("utf-8")) for t in out_files.values())
    if total > _EDIT_MAX_TOTAL_TEXT:
        return {}, "bundle_too_large"
    return out_files, None


def verify_plus_minus_blue_purple_preserve_calculator(
    *,
    before: dict[str, str],
    after: dict[str, str],
) -> bool:
    """Post-edit checks: preserve multicolor + yellow digit border; require +/− operator markers."""
    b_app = (before.get("src/App.tsx") or "").lower()
    a_app = (after.get("src/App.tsx") or "").lower()
    b_css = (before.get("src/styles.css") or "").lower()
    a_css = (after.get("src/styles.css") or "").lower()

    if "calc-digit-multicolor-keys" in b_app and "calc-digit-multicolor-keys" not in a_app:
        return False
    if "calc-yellow-digit-border" in b_app and "calc-yellow-digit-border" not in a_app:
        return False
    if ".calc-yellow-digit-border" in b_css:
        if ".calc-yellow-digit-border" not in a_css:
            return False

    if "ham-key-op-pm-plus" not in a_app or "ham-key-op-pm-minus" not in a_app:
        return False
    if "ham-key-op-pm-plus" not in a_css or "ham-key-op-pm-minus" not in a_css:
        return False

    def _chunk_has_blue_purple(blob: str, anchor: str) -> bool:
        idx = 0
        while True:
            pos = blob.find(anchor, idx)
            if pos < 0:
                return False
            win = blob[pos : pos + 400]
            has_blue = "blue" in win or "#3b82f6" in win or "#2563eb" in win or "#60a5fa" in win
            has_purple = "purple" in win or "#a78bfa" in win or "#7c3aed" in win or "#9333ea" in win
            if has_blue and has_purple:
                return True
            idx = pos + 1

    if not _chunk_has_blue_purple(a_css, "ham-key-op-pm-plus"):
        return False
    if not _chunk_has_blue_purple(a_css, "ham-key-op-pm-minus"):
        return False
    return True


def verify_general_calculator_edit_preserves_theme(*, before: dict[str, str], after: dict[str, str]) -> bool:
    """Post-gateway checks for long-tail edits: keep established calculator markers unless explicitly removed."""
    b_app = (before.get("src/App.tsx") or "").lower()
    a_app = (after.get("src/App.tsx") or "").lower()
    b_css = (before.get("src/styles.css") or "").lower()
    a_css = (after.get("src/styles.css") or "").lower()

    if "calc-digit-multicolor-keys" in b_app and "calc-digit-multicolor-keys" not in a_app:
        return False
    if "calc-yellow-digit-border" in b_app and "calc-yellow-digit-border" not in a_app:
        return False
    if ".calc-yellow-digit-border" in b_css:
        if ".calc-yellow-digit-border" not in a_css:
            return False

    for marker in ("ham-key-op-pm-plus", "ham-key-op-pm-minus"):
        if marker in b_app and marker not in a_app:
            return False
        if marker in b_css and marker not in a_css:
            return False

    return True


def verify_calculator_gateway_patch(
    *,
    before: dict[str, str],
    after: dict[str, str],
    user_plain: str,
) -> bool:
    if is_operator_plus_minus_blue_purple_border_edit(user_plain):
        return verify_plus_minus_blue_purple_preserve_calculator(before=before, after=after)
    return verify_general_calculator_edit_preserves_theme(before=before, after=after)


def verify_general_project_edit_preserves_baseline(*, before: dict[str, str], after: dict[str, str]) -> bool:
    """v1: every snapshot file present before the edit must still exist after merge."""
    for key in before:
        if key not in after:
            return False
    return True


def verify_builder_gateway_patch(
    *,
    before: dict[str, str],
    after: dict[str, str],
    user_plain: str,
    template: str | None,
) -> bool:
    tpl = (template or "").strip().lower()
    if tpl == "calculator":
        return verify_calculator_gateway_patch(before=before, after=after, user_plain=user_plain)
    return verify_general_project_edit_preserves_baseline(before=before, after=after)


def _merge_file_maps(baseline: dict[str, str], patch: dict[str, str]) -> dict[str, str]:
    out = dict(baseline)
    out.update(patch)
    return out


def _no_op_merge(baseline: dict[str, str], merged: dict[str, str]) -> bool:
    for k, v in merged.items():
        if baseline.get(k) != v:
            return False
    return True


def run_builder_edit_worker_maybe(
    *,
    workspace_id: str,
    project_id: str,
    session_id: str,
    last_user_plain: str,
    created_by: str,
    operation: str,
    preferred_source: ProjectSource,
    active_snapshot: SourceSnapshot,
    complete_turn: Callable[..., str] | None = None,
    action_decision: BuilderActionDecision | None = None,
) -> dict[str, Any] | None:
    """
    Hermes-gateway edit path for eligible long-tail follow-ups.

    Returns a summary dict compatible with builder hook metadata, or None if this worker
    does not handle the turn (caller continues with scaffold).
    """
    if operation != "update_existing_project":
        return None
    tpl = resolve_snapshot_project_template(active_snapshot)
    decision = action_decision or classify_builder_project_action(
        last_user_plain,
        has_active_snapshot=True,
        active_template=tpl,
    )
    if decision.kind != "mutate":
        return None
    if not builder_edit_worker_eligible(last_user_plain, decision=decision, active_template=tpl):
        return None

    worker_id = resolve_effective_builder_worker_id(preferred_source)
    if worker_id != DEFAULT_BUILDER_CODE_WORKER:
        return {
            "builder_intent": "build_or_create",
            "builder_operation": operation,
            "builder_edit_worker_blocked": True,
            "builder_edit_worker": {"worker": worker_id, "blocked_reason": "unsupported_worker"},
            "source_snapshot_id": str(active_snapshot.id or "").strip() or None,
        }

    if not _gateway_mode_allows_live_edit():
        return {
            "builder_intent": "build_or_create",
            "builder_operation": operation,
            "builder_edit_worker_blocked": True,
            "builder_edit_worker": {"worker": worker_id, "blocked_reason": "gateway_mock_or_unconfigured"},
            "source_snapshot_id": str(active_snapshot.id or "").strip() or None,
        }

    baseline = _inline_file_map(active_snapshot)
    if not baseline or "src/App.tsx" not in baseline:
        return None

    store = get_builder_source_store()
    job = store.create_import_job(
        workspace_id=workspace_id,
        project_id=project_id,
        created_by=created_by,
        phase="received",
        status="queued",
        project_source_id=preferred_source.id,
        metadata={
            "origin": "builder_edit_worker",
            "activity_title": "Planning builder edit",
            "activity_message": "Planning builder edit",
        },
    )
    job = _append_activity(job, store, "plan", "Planning edit via Hermes gateway")
    job = store.mark_import_job_running(import_job_id=job.id, phase="hermes_edit")
    job = _append_activity(
        job,
        store,
        "read_files",
        "Reading inline snapshot source files",
    )
    job = _append_activity(job, store, "worker_selected", "Selected Hermes gateway as code worker")

    tpl_l = (tpl or "").strip().lower()
    allowed_list = sorted(baseline.keys())
    calc_extra = (
        "For calculator React apps: preserve existing calc-digit-multicolor-keys and calc-yellow-digit-border "
        "on digit keys unless the user explicitly asks to remove them.\n"
        "For AC/Clear/Equals or other control keys, change only what the user asked for and keep the rest of the theme.\n"
        "To style only the + and - operator buttons with blue fill and purple border, add CSS classes "
        "ham-key-op-pm-plus and ham-key-op-pm-minus to those two buttons only (leave / * unchanged) "
        "and define matching rules in src/styles.css with visible blue background and purple border."
        if tpl_l == "calculator"
        else ""
    )
    system = (
        "You output exactly one JSON object and nothing else (no markdown, no code fences, no commentary). "
        "Schema keys: status (success|unsupported|failed_validation), summary (string), "
        "files (object mapping relative paths to full UTF-8 file text), checks (string array). "
        f"Each files key must be either an existing snapshot path from this list: {allowed_list}, "
        "or a new path under src/ with extension .tsx, .ts, .jsx, .js, or .css only. "
        "No path traversal, no other paths.\n"
        "If you cannot safely apply the user request, set status unsupported or failed_validation.\n"
        "When status is success, files must include complete contents for every path you modified or added.\n"
        f"{calc_extra}"
    )
    user_payload = {
        "user_request": last_user_plain,
        "current_files": _worker_current_files_payload(baseline),
    }
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=True)},
    ]

    job = _append_activity(job, store, "patch_requested", "Requesting patch from Hermes gateway")

    turn = complete_turn or complete_chat_turn
    try:
        raw = turn(messages)
    except GatewayCallError:
        job = store.mark_import_job_failed(
            import_job_id=job.id,
            phase="hermes_edit",
            error_code="HERMES_GATEWAY_ERROR",
            error_message="Hermes gateway refused or failed the edit request.",
        )
        job = _append_activity(job, store, "blocked", "Blocked: Hermes gateway error")
        return {
            "builder_intent": "build_or_create",
            "builder_operation": operation,
            "builder_edit_worker_blocked": True,
            "builder_edit_worker": {"worker": worker_id, "blocked_reason": "gateway_error"},
            "import_job_id": job.id,
            "source_snapshot_id": str(active_snapshot.id or "").strip() or None,
        }

    if _looks_like_mock_assistant_text(raw):
        job = store.mark_import_job_failed(
            import_job_id=job.id,
            phase="hermes_edit",
            error_code="HERMES_GATEWAY_MOCK",
            error_message="Mock gateway cannot produce structured builder patches.",
        )
        job = _append_activity(job, store, "blocked", "Blocked: gateway not configured for structured edits")
        return {
            "builder_intent": "build_or_create",
            "builder_operation": operation,
            "builder_edit_worker_blocked": True,
            "builder_edit_worker": {"worker": worker_id, "blocked_reason": "gateway_mock"},
            "import_job_id": job.id,
            "source_snapshot_id": str(active_snapshot.id or "").strip() or None,
        }

    job = _append_activity(job, store, "patch_received", "Patch received from Hermes gateway")

    payload = _extract_json_object(raw)
    if not payload:
        job = store.mark_import_job_failed(
            import_job_id=job.id,
            phase="hermes_edit",
            error_code="INVALID_JSON",
            error_message="Hermes gateway response was not valid JSON.",
        )
        job = _append_activity(job, store, "blocked", "Blocked: invalid structured response")
        return {
            "builder_intent": "build_or_create",
            "builder_operation": operation,
            "builder_edit_worker_blocked": True,
            "builder_edit_worker": {"worker": worker_id, "blocked_reason": "invalid_json"},
            "import_job_id": job.id,
            "source_snapshot_id": str(active_snapshot.id or "").strip() or None,
        }

    patch_files, err = _validate_gateway_patch_payload(payload, baseline=baseline)
    if err:
        job = store.mark_import_job_failed(
            import_job_id=job.id,
            phase="hermes_edit",
            error_code="PATCH_INVALID",
            error_message=f"Patch validation failed: {err}",
        )
        job = _append_activity(job, store, "blocked", f"Blocked: validation failed ({err})")
        return {
            "builder_intent": "build_or_create",
            "builder_operation": operation,
            "builder_edit_worker_blocked": True,
            "builder_edit_worker": {"worker": worker_id, "blocked_reason": err},
            "import_job_id": job.id,
            "source_snapshot_id": str(active_snapshot.id or "").strip() or None,
        }

    merged = _merge_file_maps(baseline, patch_files)
    if _no_op_merge(baseline, merged):
        job = store.mark_import_job_failed(
            import_job_id=job.id,
            phase="hermes_edit",
            error_code="NO_OP",
            error_message="Patch did not change files.",
        )
        job = _append_activity(job, store, "blocked", "Blocked: no changes applied")
        return {
            "builder_intent": "build_or_create",
            "builder_operation": operation,
            "builder_edit_worker_blocked": True,
            "builder_edit_worker": {"worker": worker_id, "blocked_reason": "no_op"},
            "import_job_id": job.id,
            "source_snapshot_id": str(active_snapshot.id or "").strip() or None,
        }

    if tpl_l == "calculator":
        if is_operator_plus_minus_blue_purple_border_edit(last_user_plain):
            verify_title = "Verifying + / - operator styling and preserved calculator theme"
        else:
            verify_title = "Verifying calculator theme preservation"
    else:
        verify_title = "Verifying snapshot files preserved"
    job = _append_activity(job, store, "verify", verify_title)

    if not verify_builder_gateway_patch(
        before=baseline,
        after=merged,
        user_plain=last_user_plain,
        template=tpl,
    ):
        job = store.mark_import_job_failed(
            import_job_id=job.id,
            phase="hermes_edit",
            error_code="VERIFY_FAILED",
            error_message="Post-edit verification failed.",
        )
        job = _append_activity(job, store, "blocked", "Blocked: verification failed")
        return {
            "builder_intent": "build_or_create",
            "builder_operation": operation,
            "builder_edit_worker_blocked": True,
            "builder_edit_worker": {"worker": worker_id, "blocked_reason": "verification_failed"},
            "import_job_id": job.id,
            "source_snapshot_id": str(active_snapshot.id or "").strip() or None,
        }

    digest = hashlib.sha256(json.dumps(merged, sort_keys=True).encode("utf-8")).hexdigest()
    artifact_uri, zip_size = materialize_inline_files_as_zip_artifact(
        workspace_id=workspace_id,
        project_id=project_id,
        files=merged,
    )

    entries_manifest: list[dict[str, Any]] = []
    total_bytes = 0
    for path, text in sorted(merged.items()):
        b = text.encode("utf-8")
        total_bytes += len(b)
        entries_manifest.append({"path": path, "size_bytes": len(b), "text": text})

    prev_meta = dict(active_snapshot.metadata or {})
    fp = hashlib.sha256(
        f"hermes_edit_v1\n{session_id}\n{last_user_plain.strip()}\n{digest}".encode(),
    ).hexdigest()[:24]

    snapshot = SourceSnapshot(
        workspace_id=workspace_id,
        project_id=project_id,
        project_source_id=preferred_source.id,
        digest_sha256=digest,
        size_bytes=zip_size,
        artifact_uri=artifact_uri,
        manifest={
            "kind": _MANIFEST_KIND_INLINE,
            "file_count": len(entries_manifest),
            "entries": [{"path": e["path"], "size_bytes": e["size_bytes"]} for e in entries_manifest],
            "inline_files": merged,
        },
        created_by=created_by,
        metadata={
            **prev_meta,
            "chat_scaffold": prev_meta.get("chat_scaffold", "1"),
            "builder_edit_worker": "hermes_gateway_v1",
            "import_job_id": job.id,
            "chat_scaffold_fingerprint": fp,
            "chat_scaffold_operation": operation,
        },
    )
    snapshot = store.upsert_source_snapshot(snapshot)

    src = preferred_source.model_copy(
        update={
            "active_snapshot_id": snapshot.id,
            "updated_at": _utc_now(),
        },
    )
    src = store.upsert_project_source(src)

    job = store.mark_import_job_succeeded(
        import_job_id=job.id,
        phase="materialized",
        source_snapshot_id=snapshot.id,
        stats={"file_count": len(merged), "inline_bytes": total_bytes, "artifact_zip_bytes": zip_size},
    )
    job = _append_activity(job, store, "snapshot_created", "Snapshot created from Hermes gateway patch")
    preview_meta = maybe_enqueue_chat_scaffold_cloud_runtime_job(
        workspace_id=workspace_id,
        project_id=project_id,
        source_snapshot_id=snapshot.id,
        session_id=session_id,
        requested_by=created_by,
    )
    if preview_meta:
        job = _append_activity(job, store, "preview_refresh", "Preview refresh started")
    job = _append_activity(job, store, "complete", "Builder edit complete")

    if tpl_l == "calculator":
        if is_operator_plus_minus_blue_purple_border_edit(last_user_plain):
            check_name = "plus_minus_blue_purple_preserve_calculator"
        else:
            check_name = "calculator_theme_preserve"
    else:
        check_name = "snapshot_baseline_paths_preserved"
    artifact_verification = {
        "verified": True,
        "skipped": False,
        "status": "ok",
        "requested_checks": [check_name],
        "passed_checks": [check_name],
        "failed_checks": [],
        "reason": "",
    }

    out: dict[str, Any] = {
        "builder_intent": "build_or_create",
        "builder_operation": operation,
        "scaffolded": True,
        "builder_edit_worker": {"worker": "hermes_gateway", "applied": True, "import_job_id": job.id},
        "project_source_id": src.id,
        "source_snapshot_id": snapshot.id,
        "import_job_id": job.id,
        "artifact_verification": artifact_verification,
    }
    out.update(preview_meta)
    return out
