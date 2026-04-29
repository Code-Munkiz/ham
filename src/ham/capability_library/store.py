"""Atomic read/write, revision conflicts, file lock, and audit for capability library v1."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.ham.capability_library.paths import audit_dir, index_path, lock_path
from src.ham.capability_library.schema import (
    SCHEMA_VERSION,
    CapabilityLibraryIndex,
    LibraryEntry,
    utc_now_iso,
)
from src.ham.capability_library.validate import validate_ref_in_catalogs


class CapabilityLibraryWriteConflictError(Exception):
    """Raised when index.json changed since the client base_revision."""


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


def revision_for_index(doc: CapabilityLibraryIndex) -> str:
    raw = doc.model_dump(mode="json")
    canonical = json.dumps(raw, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _acquire_lock_fd(fd: int) -> None:
    if sys.platform == "win32":
        import msvcrt

        if os.fstat(fd).st_size == 0:
            os.write(fd, b"\n")
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX)


def _release_lock_fd(fd: int) -> None:
    if sys.platform == "win32":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


@contextlib.contextmanager
def _index_lock(root: Path):
    lp = lock_path(root)
    lp.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lp), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        _acquire_lock_fd(fd)
        yield
    finally:
        _release_lock_fd(fd)
        os.close(fd)


def _atomic_write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=2, ensure_ascii=True, sort_keys=True) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _append_audit_event(root: Path, payload: dict[str, Any]) -> str:
    ad = audit_dir(root)
    ad.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    audit_id = f"{stamp}_{uuid.uuid4().hex[:8]}"
    line = json.dumps(
        {"audit_id": audit_id, **payload},
        ensure_ascii=True,
    )
    (ad / f"{audit_id}.jsonl").write_text(line + "\n", encoding="utf-8")
    return audit_id


def read_capability_library(root: Path) -> tuple[CapabilityLibraryIndex, str]:
    root = root.resolve()
    p = index_path(root)
    raw = _read_json_file(p)
    if not raw:
        idx = CapabilityLibraryIndex()
    else:
        if raw.get("schema_version") and raw["schema_version"] != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported capability library schema {raw.get('schema_version')!r}; expected {SCHEMA_VERSION!r}",
            )
        idx = CapabilityLibraryIndex.from_disk(raw)
    return idx, revision_for_index(idx)


def _commit(
    root: Path,
    new_index: CapabilityLibraryIndex,
    *,
    disk_revision_before: str,
    action: str,
    details: dict[str, Any],
) -> tuple[str, str]:
    """Must be called with ``_index_lock`` held. ``disk_revision_before`` is the revision read under that lock."""
    new_rev = revision_for_index(new_index)
    _atomic_write_json(index_path(root), new_index.model_dump(mode="json"))
    audit_id = _append_audit_event(
        root,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "project_root": str(root),
            "details": details,
            "previous_revision": disk_revision_before,
            "new_revision": new_rev,
            "result": "ok",
        },
    )
    return new_rev, audit_id


@dataclass(frozen=True)
class SaveResult:
    new_revision: str
    audit_id: str
    index: CapabilityLibraryIndex


def save_entry(
    root: Path,
    *,
    ref: str,
    notes: str,
    expect_revision: str,
) -> SaveResult:
    root = root.resolve()
    validate_ref_in_catalogs(ref)
    with _index_lock(root):
        current, rev = read_capability_library(root)
        if rev != expect_revision:
            raise CapabilityLibraryWriteConflictError(
                ".ham/capability-library/v1/index.json changed since read; refetch and retry.",
            )
        now = utc_now_iso()
        by_ref: dict[str, LibraryEntry] = {e.ref: e for e in current.entries}
        if ref in by_ref:
            e = by_ref[ref]
            by_ref[ref] = LibraryEntry(
                ref=e.ref,
                notes=notes,
                user_order=e.user_order,
                created_at=e.created_at,
                updated_at=now,
            )
        else:
            next_order = max((e.user_order for e in current.entries), default=-1) + 1
            by_ref[ref] = LibraryEntry(
                ref=ref,
                notes=notes,
                user_order=next_order,
                created_at=now,
                updated_at=now,
            )
        new_index = CapabilityLibraryIndex(entries=list(by_ref.values()))
        new_rev, audit_id = _commit(
            root,
            new_index,
            disk_revision_before=rev,
            action="save",
            details={"ref": ref},
        )
        return SaveResult(new_revision=new_rev, audit_id=audit_id, index=new_index)


def remove_entry(
    root: Path,
    *,
    ref: str,
    expect_revision: str,
) -> tuple[str, str, CapabilityLibraryIndex]:
    root = root.resolve()
    with _index_lock(root):
        current, rev = read_capability_library(root)
        if rev != expect_revision:
            raise CapabilityLibraryWriteConflictError(
                ".ham/capability-library/v1/index.json changed since read; refetch and retry.",
            )
        kept = [e for e in current.entries if e.ref != ref]
        if len(kept) == len(current.entries):
            raise KeyError(f"ref not in library: {ref!r}")
        new_index = CapabilityLibraryIndex(entries=kept)
        new_rev, audit_id = _commit(
            root,
            new_index,
            disk_revision_before=rev,
            action="remove",
            details={"ref": ref},
        )
        return new_rev, audit_id, new_index


def reorder_entries(
    root: Path,
    *,
    order: list[str],
    expect_revision: str,
) -> tuple[str, str, CapabilityLibraryIndex]:
    root = root.resolve()
    with _index_lock(root):
        current, rev = read_capability_library(root)
        if rev != expect_revision:
            raise CapabilityLibraryWriteConflictError(
                ".ham/capability-library/v1/index.json changed since read; refetch and retry.",
            )
        known = {e.ref: e for e in current.entries}
        if set(order) != set(known.keys()):
            raise ValueError("order must be a permutation of all library refs")
        reordered: list[LibraryEntry] = []
        now = utc_now_iso()
        for i, ref in enumerate(order):
            e = known[ref]
            reordered.append(
                LibraryEntry(
                    ref=e.ref,
                    notes=e.notes,
                    user_order=i,
                    created_at=e.created_at,
                    updated_at=now,
                ),
            )
        new_index = CapabilityLibraryIndex(entries=reordered)
        new_rev, audit_id = _commit(
            root,
            new_index,
            disk_revision_before=rev,
            action="reorder",
            details={"order": order},
        )
        return new_rev, audit_id, new_index
