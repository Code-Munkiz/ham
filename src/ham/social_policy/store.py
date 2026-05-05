"""File-backed Social Policy store with preview / apply / rollback.

Mirrors :mod:`src.ham.settings_write` but for the SocialPolicy document.
This module does **no** outbound I/O: no provider calls, no scheduler, no
``.env`` mutation, no live transport. Tests assert this contract.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.ham.social_policy.schema import (
    DEFAULT_SOCIAL_POLICY,
    SOCIAL_POLICY_REL_PATH,
    SocialPolicy,
    SocialPolicyChanges,
    policy_to_safe_dict,
)

# Phrase strings are *literals*, not secrets. Used by API layer to enforce
# explicit operator confirmation before any write.
APPLY_CONFIRMATION_PHRASE = "SAVE SOCIAL POLICY"
ROLLBACK_CONFIRMATION_PHRASE = "RESTORE SOCIAL POLICY"
LIVE_AUTONOMY_CONFIRMATION_PHRASE = "ARM SOCIAL AUTONOMY"

_BACKUP_SUBDIR = Path(".ham") / "_backups" / "social_policy"
_AUDIT_SUBDIR = Path(".ham") / "_audit" / "social_policy"

# Backup ids are emitted by us; this regex prevents path traversal at the
# /rollback boundary.
_BACKUP_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z_[a-f0-9]{8}$")

# Bound how much of a JSONL/JSON file we will read for history / audit
# listings (mirrors the existing API helpers).
_MAX_LIST_ENTRIES = 25
_MAX_BYTES_SCANNED = 1_048_576


class SocialPolicyWriteConflictError(Exception):
    """The on-disk document changed since the preview was generated."""


class SocialPolicyApplyError(Exception):
    """Apply-time invariant violation (validation, phrase, persona, etc.)."""


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def social_policy_path(root: Path) -> Path:
    """Resolve the canonical document path under ``root``.

    ``HAM_SOCIAL_POLICY_PATH`` is an *escape hatch for tests*; production code
    paths always pass ``root = Path.cwd()`` (or the repo root) and let the
    relative path resolve naturally.
    """
    explicit = (os.environ.get("HAM_SOCIAL_POLICY_PATH") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    return (root / SOCIAL_POLICY_REL_PATH).resolve()


def _backup_dir(root: Path) -> Path:
    return (root / _BACKUP_SUBDIR).resolve()


def _audit_dir(root: Path) -> Path:
    return (root / _AUDIT_SUBDIR).resolve()


# ---------------------------------------------------------------------------
# Read / revision
# ---------------------------------------------------------------------------


def _read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.strip():
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def read_social_policy_document(root: Path) -> dict[str, Any]:
    """Return the raw on-disk document, or ``{}`` if missing/invalid."""
    return _read_json_file(social_policy_path(root)) or {}


def revision_for_document(doc: dict[str, Any]) -> str:
    canonical = json.dumps(doc, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _doc_to_policy_or_default(doc: dict[str, Any]) -> SocialPolicy:
    if not doc:
        return DEFAULT_SOCIAL_POLICY.model_copy(deep=True)
    return SocialPolicy.model_validate(doc)


def _policy_to_canonical_doc(policy: SocialPolicy) -> dict[str, Any]:
    return policy.model_dump(mode="json")


def proposal_digest(root: Path, changes: SocialPolicyChanges) -> str:
    payload = {
        "root": str(root.resolve()),
        "changes": changes.model_dump(mode="json"),
    }
    body = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


def _flatten(prefix: str, value: Any, out: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for key, sub in value.items():
            _flatten(f"{prefix}.{key}" if prefix else key, sub, out)
    else:
        out[prefix] = value


def compute_leaf_diff(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    flat_before: dict[str, Any] = {}
    flat_after: dict[str, Any] = {}
    _flatten("", before, flat_before)
    _flatten("", after, flat_after)
    keys = sorted(set(flat_before.keys()) | set(flat_after.keys()))
    diffs: list[dict[str, Any]] = []
    for key in keys:
        vb = flat_before.get(key)
        va = flat_after.get(key)
        if vb != va:
            diffs.append({"path": key, "old": vb, "new": va})
    return diffs


# ---------------------------------------------------------------------------
# Preview / Apply / Rollback
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PreviewResult:
    effective_before: dict[str, Any]
    effective_after: dict[str, Any]
    diff: list[dict[str, Any]]
    warnings: list[str]
    write_target: str
    proposal_digest: str
    base_revision: str
    live_autonomy_change: bool


@dataclass(frozen=True)
class ApplyResult:
    backup_id: str
    audit_id: str
    effective_after: dict[str, Any]
    diff_applied: list[dict[str, Any]]
    new_revision: str
    live_autonomy_change: bool


@dataclass(frozen=True)
class RollbackResult:
    backup_id: str
    audit_id: str
    effective_after: dict[str, Any]
    new_revision: str


def _atomic_write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=2, ensure_ascii=True, sort_keys=True) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _new_backup_id() -> str:
    return f"{_utc_stamp()}_{uuid.uuid4().hex[:8]}"


def _live_autonomy_changed(before: SocialPolicy, after: SocialPolicy) -> bool:
    return bool(before.live_autonomy_armed) != bool(after.live_autonomy_armed)


def preview_social_policy(root: Path, changes: SocialPolicyChanges) -> PreviewResult:
    """Compute before/after/diff for a proposed full-document replacement.

    No file is written. ``base_revision`` is the SHA-256 of the on-disk
    document at the moment of read; pass it back into :func:`apply_social_policy`
    so the apply can detect concurrent edits.
    """
    if not changes.has_patch():
        raise ValueError("changes must include at least one field")
    root = root.resolve()
    doc_before = read_social_policy_document(root)
    policy_before = _doc_to_policy_or_default(doc_before)
    policy_after = changes.policy
    effective_before = policy_to_safe_dict(policy_before)
    effective_after = policy_to_safe_dict(policy_after)
    diff = compute_leaf_diff(effective_before, effective_after)
    warnings: list[str] = []
    if not doc_before:
        warnings.append("no_existing_policy_document_first_apply_will_create_one")
    return PreviewResult(
        effective_before=effective_before,
        effective_after=effective_after,
        diff=diff,
        warnings=warnings,
        write_target=SOCIAL_POLICY_REL_PATH,
        proposal_digest=proposal_digest(root, changes),
        base_revision=revision_for_document(doc_before),
        live_autonomy_change=_live_autonomy_changed(policy_before, policy_after),
    )


def apply_social_policy(
    root: Path,
    changes: SocialPolicyChanges,
    *,
    base_revision: str,
) -> ApplyResult:
    """Atomic apply with revision check, pre-write backup, audit envelope."""
    if not changes.has_patch():
        raise ValueError("changes must include at least one field")
    root = root.resolve()
    doc_before = read_social_policy_document(root)
    if revision_for_document(doc_before) != base_revision:
        raise SocialPolicyWriteConflictError(
            ".ham/social_policy.json changed since preview; run preview again.",
        )
    policy_before = _doc_to_policy_or_default(doc_before)
    policy_after = changes.policy
    effective_before = policy_to_safe_dict(policy_before)
    new_doc = _policy_to_canonical_doc(policy_after)
    effective_after = policy_to_safe_dict(policy_after)

    backup_dir = _backup_dir(root)
    audit_dir = _audit_dir(root)
    backup_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)

    backup_id = _new_backup_id()
    backup_path = backup_dir / f"{backup_id}.json"
    wrapper = {
        "format": 1,
        "document": doc_before,
        "captured_revision": revision_for_document(doc_before),
    }
    backup_path.write_text(
        json.dumps(wrapper, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    target = social_policy_path(root)
    _atomic_write_json(target, new_doc)

    diff_applied = compute_leaf_diff(effective_before, effective_after)
    new_rev = revision_for_document(read_social_policy_document(root))
    live_change = _live_autonomy_changed(policy_before, policy_after)

    audit_id = f"{backup_id}-audit"
    audit_payload = {
        "audit_id": audit_id,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "action": "apply",
        "project_root": str(root),
        "backup_id": backup_id,
        "proposal_digest": proposal_digest(root, changes),
        "diff": diff_applied,
        "previous_revision": base_revision,
        "new_revision": new_rev,
        "live_autonomy_change": live_change,
        "result": "ok",
    }
    (audit_dir / f"{audit_id}.json").write_text(
        json.dumps(audit_payload, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return ApplyResult(
        backup_id=backup_id,
        audit_id=audit_id,
        effective_after=effective_after,
        diff_applied=diff_applied,
        new_revision=new_rev,
        live_autonomy_change=live_change,
    )


def rollback_social_policy(root: Path, backup_id: str) -> RollbackResult:
    """Restore a previously-captured backup; pre-rollback snapshot also kept."""
    root = root.resolve()
    if not _BACKUP_ID_RE.match(backup_id):
        raise ValueError("backup_id has invalid shape")
    backup_path = _backup_dir(root) / f"{backup_id}.json"
    if not backup_path.is_file():
        raise FileNotFoundError(f"backup {backup_id!r} not found")
    try:
        wrapper = json.loads(backup_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("invalid backup format") from exc
    document = wrapper.get("document") if isinstance(wrapper, dict) else None
    if not isinstance(document, dict):
        raise ValueError("invalid backup format")

    # Confirm the document we're about to restore is itself schema-valid.
    # An empty ``{}`` is the legitimate "no policy applied yet" state captured
    # by the very first apply's backup; treat it as valid (reads of ``{}``
    # already fall through to :data:`DEFAULT_SOCIAL_POLICY`).
    if document:
        try:
            SocialPolicy.model_validate(document)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"backup contains invalid policy: {exc}") from exc

    current = read_social_policy_document(root)
    backup_dir = _backup_dir(root)
    audit_dir = _audit_dir(root)
    backup_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)

    pre_rollback_id = _new_backup_id()
    (backup_dir / f"{pre_rollback_id}.json").write_text(
        json.dumps(
            {
                "format": 1,
                "document": current,
                "captured_revision": revision_for_document(current),
                "note": "auto-backup before rollback",
            },
            indent=2,
            ensure_ascii=True,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    target = social_policy_path(root)
    _atomic_write_json(target, document)
    new_rev = revision_for_document(read_social_policy_document(root))
    effective_after = policy_to_safe_dict(_doc_to_policy_or_default(document))

    audit_id = f"{pre_rollback_id}-rollback-audit"
    audit_payload = {
        "audit_id": audit_id,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "action": "rollback",
        "project_root": str(root),
        "restored_from_backup_id": backup_id,
        "pre_rollback_backup_id": pre_rollback_id,
        "new_revision": new_rev,
        "result": "ok",
    }
    (audit_dir / f"{audit_id}.json").write_text(
        json.dumps(audit_payload, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return RollbackResult(
        backup_id=pre_rollback_id,
        audit_id=audit_id,
        effective_after=effective_after,
        new_revision=new_rev,
    )


# ---------------------------------------------------------------------------
# Bounded listings (history / audit)
# ---------------------------------------------------------------------------


def _bounded_dir_listing(directory: Path, suffix: str) -> list[Path]:
    if not directory.is_dir():
        return []
    try:
        entries = [
            entry
            for entry in directory.iterdir()
            if entry.is_file() and entry.name.endswith(suffix)
        ]
    except OSError:
        return []
    entries.sort(key=lambda p: p.name, reverse=True)
    return entries[:_MAX_LIST_ENTRIES]


def list_backups(root: Path) -> list[dict[str, Any]]:
    """Return up to 25 most-recent backups as ``[{id, timestamp_iso, size}]``."""
    out: list[dict[str, Any]] = []
    for entry in _bounded_dir_listing(_backup_dir(root), ".json"):
        try:
            size = entry.stat().st_size
            mtime = datetime.fromtimestamp(entry.stat().st_mtime, tz=UTC)
        except OSError:
            continue
        if size > _MAX_BYTES_SCANNED:
            continue
        backup_id = entry.stem
        if not _BACKUP_ID_RE.match(backup_id):
            continue
        out.append(
            {
                "backup_id": backup_id,
                "timestamp_iso": mtime.isoformat().replace("+00:00", "Z"),
                "size_bytes": int(size),
            }
        )
    return out


def list_audit_envelopes(root: Path) -> list[dict[str, Any]]:
    """Return up to 25 most-recent audit envelopes (subset of fields)."""
    keys = {
        "audit_id",
        "timestamp",
        "action",
        "backup_id",
        "restored_from_backup_id",
        "pre_rollback_backup_id",
        "previous_revision",
        "new_revision",
        "live_autonomy_change",
        "diff",
        "result",
    }
    out: list[dict[str, Any]] = []
    for entry in _bounded_dir_listing(_audit_dir(root), ".json"):
        try:
            size = entry.stat().st_size
        except OSError:
            continue
        if size > _MAX_BYTES_SCANNED:
            continue
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        subset = {k: copy.deepcopy(v) for k, v in data.items() if k in keys}
        # Bound diff size on response.
        diff = subset.get("diff")
        if isinstance(diff, list):
            subset["diff"] = diff[:25]
        out.append(subset)
    return out


# ---------------------------------------------------------------------------
# Token presence helper (no value disclosure)
# ---------------------------------------------------------------------------


def social_policy_writes_enabled() -> bool:
    """Whether the policy write token is set; the value itself is never read out."""
    return bool((os.environ.get("HAM_SOCIAL_POLICY_WRITE_TOKEN") or "").strip())
