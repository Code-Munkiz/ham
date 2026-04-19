"""Allowlisted project settings writes to ``.ham/settings.json`` (v1 control plane)."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.memory_heist import _deep_merge, discover_config

MAX_SESSION_COMPACTION_MAX_TOKENS = 500_000
MAX_SESSION_COMPACTION_PRESERVE = 10_000
MAX_SESSION_TOOL_PRUNE_CHARS = 50_000
MAX_ROLE_INSTRUCTION_CHARS = 100_000

WRITE_REL_TARGET = ".ham/settings.json"
_BACKUP_SUBDIR = Path(".ham") / "_backups" / "settings"
_AUDIT_SUBDIR = Path(".ham") / "_audit" / "settings"


class SettingsWriteConflictError(Exception):
    """Raised when the on-disk settings file changed since preview (revision mismatch)."""


class MemoryHeistPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_compaction_max_tokens: int | None = Field(
        default=None,
        ge=1,
        le=MAX_SESSION_COMPACTION_MAX_TOKENS,
    )
    session_compaction_preserve: int | None = Field(
        default=None,
        ge=1,
        le=MAX_SESSION_COMPACTION_PRESERVE,
    )
    session_tool_prune_chars: int | None = Field(
        default=None,
        ge=1,
        le=MAX_SESSION_TOOL_PRUNE_CHARS,
    )


class SettingsChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_heist: MemoryHeistPatch | None = None
    architect_instruction_chars: int | None = Field(
        default=None,
        ge=1,
        le=MAX_ROLE_INSTRUCTION_CHARS,
    )
    commander_instruction_chars: int | None = Field(
        default=None,
        ge=1,
        le=MAX_ROLE_INSTRUCTION_CHARS,
    )
    critic_instruction_chars: int | None = Field(
        default=None,
        ge=1,
        le=MAX_ROLE_INSTRUCTION_CHARS,
    )

    def has_patch(self) -> bool:
        if self.memory_heist is not None and self.memory_heist.model_dump(exclude_none=True):
            return True
        return any(
            getattr(self, k) is not None
            for k in (
                "architect_instruction_chars",
                "commander_instruction_chars",
                "critic_instruction_chars",
            )
        )


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


def read_project_settings_document(root: Path) -> dict[str, Any]:
    path = root / ".ham" / "settings.json"
    data = _read_json_file(path)
    return dict(data) if data is not None else {}


def revision_for_document(doc: dict[str, Any]) -> str:
    canonical = json.dumps(doc, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_file_patch(changes: SettingsChanges) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    if changes.memory_heist is not None:
        nested = changes.memory_heist.model_dump(exclude_none=True)
        if nested:
            patch["memory_heist"] = nested
    if changes.architect_instruction_chars is not None:
        patch["architect_instruction_chars"] = changes.architect_instruction_chars
    if changes.commander_instruction_chars is not None:
        patch["commander_instruction_chars"] = changes.commander_instruction_chars
    if changes.critic_instruction_chars is not None:
        patch["critic_instruction_chars"] = changes.critic_instruction_chars
    return patch


def merge_patch_into_document(doc: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(doc)
    _deep_merge(out, patch)
    return out


def allowlisted_effective_slice(merged: dict[str, Any]) -> dict[str, Any]:
    mh = merged.get("memory_heist")
    section: dict[str, Any] = mh if isinstance(mh, dict) else {}

    def _mh(key: str) -> Any:
        if key in section:
            return section.get(key)
        return merged.get(key)

    return {
        "memory_heist": {
            "session_compaction_max_tokens": _mh("session_compaction_max_tokens"),
            "session_compaction_preserve": _mh("session_compaction_preserve"),
            "session_tool_prune_chars": _mh("session_tool_prune_chars"),
        },
        "architect_instruction_chars": merged.get("architect_instruction_chars"),
        "commander_instruction_chars": merged.get("commander_instruction_chars"),
        "critic_instruction_chars": merged.get("critic_instruction_chars"),
    }


def compute_leaf_diff(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    bmh = before.get("memory_heist") or {}
    amh = after.get("memory_heist") or {}
    if not isinstance(bmh, dict):
        bmh = {}
    if not isinstance(amh, dict):
        amh = {}
    for k in (
        "session_compaction_max_tokens",
        "session_compaction_preserve",
        "session_tool_prune_chars",
    ):
        vb, va = bmh.get(k), amh.get(k)
        if vb != va:
            diffs.append({"path": f"memory_heist.{k}", "old": vb, "new": va})
    for k in ("architect_instruction_chars", "commander_instruction_chars", "critic_instruction_chars"):
        vb, va = before.get(k), after.get(k)
        if vb != va:
            diffs.append({"path": k, "old": vb, "new": va})
    return diffs


def collect_warnings(root: Path, patch: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    local_path = root / ".ham" / "settings.local.json"
    local = _read_json_file(local_path)
    if not local:
        return warnings
    if patch.get("architect_instruction_chars") is not None and "architect_instruction_chars" in local:
        warnings.append(
            "settings.local.json sets architect_instruction_chars; it overrides .ham/settings.json."
        )
    if patch.get("commander_instruction_chars") is not None and "commander_instruction_chars" in local:
        warnings.append(
            "settings.local.json sets commander_instruction_chars; it overrides .ham/settings.json."
        )
    if patch.get("critic_instruction_chars") is not None and "critic_instruction_chars" in local:
        warnings.append(
            "settings.local.json sets critic_instruction_chars; it overrides .ham/settings.json."
        )
    mh_patch = patch.get("memory_heist")
    loc_mh = local.get("memory_heist")
    if isinstance(mh_patch, dict) and isinstance(loc_mh, dict):
        for k in mh_patch:
            if k in loc_mh:
                warnings.append(
                    f"settings.local.json sets memory_heist.{k}; it overrides .ham/settings.json."
                )
    return warnings


def proposal_digest(root: Path, changes: SettingsChanges) -> str:
    payload = {
        "root": str(root.resolve()),
        "changes": changes.model_dump(mode="json", exclude_none=True),
    }
    body = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _atomic_write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=2, ensure_ascii=True, sort_keys=True) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


@dataclass(frozen=True)
class PreviewResult:
    effective_before: dict[str, Any]
    effective_after: dict[str, Any]
    diff: list[dict[str, Any]]
    warnings: list[str]
    write_target: str
    proposal_digest: str
    base_revision: str


def preview_project_settings(root: Path, changes: SettingsChanges) -> PreviewResult:
    if not changes.has_patch():
        raise ValueError("at least one allowlisted field is required")
    root = root.resolve()
    patch = build_file_patch(changes)
    pc_before = discover_config(root)
    effective_before = allowlisted_effective_slice(pc_before.merged)
    doc = read_project_settings_document(root)
    new_doc = merge_patch_into_document(doc, patch)
    pc_after = discover_config(root, project_settings_replacement=new_doc)
    effective_after = allowlisted_effective_slice(pc_after.merged)
    diff = compute_leaf_diff(effective_before, effective_after)
    warnings = collect_warnings(root, patch)
    digest = proposal_digest(root, changes)
    return PreviewResult(
        effective_before=effective_before,
        effective_after=effective_after,
        diff=diff,
        warnings=warnings,
        write_target=WRITE_REL_TARGET,
        proposal_digest=digest,
        base_revision=revision_for_document(doc),
    )


@dataclass(frozen=True)
class ApplyResult:
    backup_id: str
    audit_id: str
    effective_after: dict[str, Any]
    diff_applied: list[dict[str, Any]]
    new_revision: str


def apply_project_settings(
    root: Path,
    changes: SettingsChanges,
    *,
    base_revision: str,
) -> ApplyResult:
    if not changes.has_patch():
        raise ValueError("at least one allowlisted field is required")
    root = root.resolve()
    doc = read_project_settings_document(root)
    if revision_for_document(doc) != base_revision:
        raise SettingsWriteConflictError(
            ".ham/settings.json changed since preview; run preview again.",
        )
    patch = build_file_patch(changes)
    effective_before = allowlisted_effective_slice(discover_config(root).merged)
    new_doc = merge_patch_into_document(doc, patch)
    backup_dir = root / _BACKUP_SUBDIR
    audit_dir = root / _AUDIT_SUBDIR
    backup_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_id = f"{stamp}_{uuid.uuid4().hex[:8]}"
    backup_path = backup_dir / f"{backup_id}.json"
    wrapper = {
        "format": 1,
        "document": doc,
        "captured_revision": revision_for_document(doc),
    }
    backup_path.write_text(
        json.dumps(wrapper, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    target = root / ".ham" / "settings.json"
    _atomic_write_json(target, new_doc)
    pc_after = discover_config(root)
    effective_after = allowlisted_effective_slice(pc_after.merged)
    diff_applied = compute_leaf_diff(effective_before, effective_after)
    new_rev = revision_for_document(read_project_settings_document(root))
    audit_id = f"{backup_id}-audit"
    audit_payload = {
        "audit_id": audit_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "apply",
        "project_root": str(root),
        "backup_id": backup_id,
        "proposal_digest": proposal_digest(root, changes),
        "diff": diff_applied,
        "previous_revision": base_revision,
        "new_revision": new_rev,
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
    )


@dataclass(frozen=True)
class RollbackResult:
    backup_id: str
    audit_id: str
    effective_after: dict[str, Any]
    new_revision: str


def rollback_project_settings(root: Path, backup_id: str) -> RollbackResult:
    root = root.resolve()
    backup_path = root / _BACKUP_SUBDIR / f"{backup_id}.json"
    if not backup_path.is_file():
        raise FileNotFoundError(f"backup {backup_id!r} not found")
    wrapper = json.loads(backup_path.read_text(encoding="utf-8"))
    document = wrapper.get("document")
    if not isinstance(document, dict):
        raise ValueError("invalid backup format")
    current = read_project_settings_document(root)
    rollback_dir = root / _BACKUP_SUBDIR
    audit_dir = root / _AUDIT_SUBDIR
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pre_rollback_id = f"{stamp}_{uuid.uuid4().hex[:8]}"
    pre_path = rollback_dir / f"{pre_rollback_id}.json"
    pre_path.write_text(
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
    target = root / ".ham" / "settings.json"
    _atomic_write_json(target, document)
    pc_after = discover_config(root)
    effective_after = allowlisted_effective_slice(pc_after.merged)
    new_rev = revision_for_document(read_project_settings_document(root))
    audit_id = f"{pre_rollback_id}-rollback-audit"
    audit_payload = {
        "audit_id": audit_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
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


def settings_writes_enabled() -> bool:
    return bool((os.environ.get("HAM_SETTINGS_WRITE_TOKEN") or "").strip())
