"""File-backed GoHAM Social autonomy profile store.

This module owns the preview / apply / rollback lifecycle for the singleton
``.ham/social_autonomy.json`` document. It is intentionally pure local file I/O:
no provider transports, no scheduler, and no ``.env`` loading.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from src.ham.social_autonomy.schema import GoHamSocialProfile, profile_to_safe_dict

_LOG = logging.getLogger(__name__)

_SOCIAL_AUTONOMY_STORE_BACKEND_ENV = "HAM_SOCIAL_AUTONOMY_STORE_BACKEND"

SOCIAL_AUTONOMY_REL_PATH = Path(".ham") / "social_autonomy.json"

_STORE_SUBDIR = "social_autonomy"
_BACKUP_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z_[a-f0-9]{8}$")
_SENSITIVE_KEY_RE = re.compile(r"(token|secret|password|credential|api[_-]?key)", re.IGNORECASE)


class SocialAutonomyStoreError(Exception):
    """Base exception for autonomy store failures."""


class SocialAutonomyWriteAuthError(SocialAutonomyStoreError):
    """Raised when ``HAM_SOCIAL_AUTONOMY_WRITE_TOKEN`` does not authorize a write."""


class SocialAutonomyPathError(SocialAutonomyStoreError):
    """Raised when the configured path is unsafe to write."""


@dataclass(frozen=True)
class ApplyResult:
    """Result metadata from a successful autonomy profile apply."""

    audit_id: str
    effective_after: dict[str, Any]
    new_revision: str
    backup_id: str | None = None


@dataclass(frozen=True)
class RollbackResult:
    """Result metadata from a successful autonomy profile rollback."""

    backup_id: str
    audit_id: str
    effective_after: dict[str, Any]
    new_revision: str


@dataclass(frozen=True)
class _StorePaths:
    document: Path
    artifact_root: Path
    audit_dir: Path
    backup_dir: Path


def _default_profile() -> GoHamSocialProfile:
    stamp = "1970-01-01T00:00:00Z"
    return GoHamSocialProfile.model_validate(
        {
            "profile_id": "goham-social-default",
            "status": "draft",
            "goal": "Configure GoHAM Social before launch.",
            "persona_id": "ham-canonical",
            "channels": {
                "x": {"enabled": False, "available": True},
                "telegram": {"enabled": False, "available": True},
                "discord": {"enabled": False, "available": False},
            },
            "actions_allowed_per_channel": {
                "x": ["reply", "broadcast"],
                "telegram": ["message", "activity"],
                "discord": [],
            },
            "daily_caps": {"x": 0, "telegram": 0, "discord": 0},
            "cadence": "manual",
            "quiet_hours": None,
            "forbidden_topics": [],
            "safety_rules": [
                "credential_request",
                "price_guarantee",
                "mass_tagging",
                "repeated_payload",
                "no_external_links",
                "payload_min_length",
            ],
            "learning_enabled": True,
            "emergency_stop": False,
            "created_at": stamp,
            "updated_at": stamp,
        }
    )


def social_autonomy_path(root: Path | None = None) -> Path:
    """Return the configured profile document path.

    ``HAM_SOCIAL_AUTONOMY_PATH`` is honored as a test/operator override. When it
    is absent, the document lives at ``<root>/.ham/social_autonomy.json``.
    """
    return _store_paths(root).document


def _store_paths(root: Path | None = None) -> _StorePaths:
    base_root = (root or Path.cwd()).resolve()
    explicit = (os.environ.get("HAM_SOCIAL_AUTONOMY_PATH") or "").strip()
    if explicit:
        configured = Path(explicit).expanduser()
        if not configured.is_absolute():
            configured = base_root / configured
        document = configured
        artifact_root = configured.parent.resolve(strict=False)
    else:
        artifact_root = base_root / ".ham"
        document = artifact_root / "social_autonomy.json"

    return _StorePaths(
        document=document,
        artifact_root=artifact_root,
        audit_dir=artifact_root / "_audit" / _STORE_SUBDIR,
        backup_dir=artifact_root / "_backups" / _STORE_SUBDIR,
    )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _assert_safe_write_path(paths: _StorePaths) -> None:
    root = paths.artifact_root.resolve(strict=False)
    parent = paths.document.parent.resolve(strict=False)
    if not _is_relative_to(parent, root):
        raise SocialAutonomyPathError("HAM_SOCIAL_AUTONOMY_PATH parent escapes configured root.")
    if paths.document.exists() and not paths.document.is_file():
        raise SocialAutonomyPathError("HAM_SOCIAL_AUTONOMY_PATH is not a regular file.")
    if paths.document.is_symlink():
        target = paths.document.resolve(strict=True)
        if not _is_relative_to(target, root):
            raise SocialAutonomyPathError(
                "Refusing to write through HAM_SOCIAL_AUTONOMY_PATH symlink outside root."
            )


def _read_document_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SocialAutonomyStoreError(f"Unable to read social autonomy profile: {exc}") from exc


def _parse_document_bytes(raw: bytes | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SocialAutonomyStoreError("Invalid social autonomy profile JSON.") from exc
    if not isinstance(parsed, dict):
        raise SocialAutonomyStoreError("Social autonomy profile JSON must be an object.")
    return parsed


def _doc_to_profile_or_default(doc: dict[str, Any] | None) -> GoHamSocialProfile:
    if not doc:
        return _default_profile()
    return GoHamSocialProfile.model_validate(doc)


def read_social_autonomy_profile(root: Path | None = None) -> GoHamSocialProfile:
    """Read the persisted profile, or return a default draft without writing."""
    paths = _store_paths(root)
    raw = _read_document_bytes(paths.document)
    return _doc_to_profile_or_default(_parse_document_bytes(raw))


def preview_social_autonomy_profile(
    root: Path | None,
    candidate: GoHamSocialProfile | dict[str, Any],
) -> dict[str, Any]:
    """Return a normalized candidate profile dict without persisting anything."""
    profile = _coerce_profile(candidate)
    return profile_to_safe_dict(profile)


def revision_for_bytes(raw: bytes | None) -> str:
    """Return a stable SHA-256 digest for optional document bytes."""
    return hashlib.sha256(raw or b"").hexdigest()


def revision_for_profile(profile: GoHamSocialProfile) -> str:
    """Return the digest for the canonical JSON bytes of a profile."""
    return revision_for_bytes(_canonical_profile_bytes(profile))


def _coerce_profile(candidate: GoHamSocialProfile | dict[str, Any]) -> GoHamSocialProfile:
    if isinstance(candidate, GoHamSocialProfile):
        return candidate
    return GoHamSocialProfile.model_validate(candidate)


def _canonical_profile_bytes(profile: GoHamSocialProfile) -> bytes:
    doc = profile.model_dump(mode="json")
    text = json.dumps(doc, indent=2, ensure_ascii=True, sort_keys=True) + "\n"
    return text.encode("utf-8")


def _atomic_write_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_bytes(raw)
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _iso_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _new_id() -> str:
    return f"{_utc_stamp()}_{uuid.uuid4().hex[:8]}"


def _redact_json_content(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if _SENSITIVE_KEY_RE.search(str(key)):
                out[str(key)] = "[REDACTED]"
            else:
                out[str(key)] = _redact_json_content(item)
        return out
    if isinstance(value, list):
        return [_redact_json_content(item) for item in value]
    return value


def _snapshot_from_bytes(raw: bytes | None) -> dict[str, Any]:
    doc = _parse_document_bytes(raw)
    profile = _doc_to_profile_or_default(doc)
    return _redact_json_content(profile_to_safe_dict(profile))


def _require_write_token(token: str | None) -> None:
    expected = (os.environ.get("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN") or "").strip()
    if not expected or token != expected:
        raise SocialAutonomyWriteAuthError(
            "HAM_SOCIAL_AUTONOMY_WRITE_TOKEN is required for social autonomy writes."
        )


def apply_social_autonomy_profile(
    root: Path | None,
    candidate: GoHamSocialProfile | dict[str, Any],
    *,
    token: str | None,
    actor: str = "system",
) -> ApplyResult:
    """Persist a profile atomically, writing a verbatim prior-byte backup and audit."""
    _require_write_token(token)
    paths = _store_paths(root)
    _assert_safe_write_path(paths)

    profile = _coerce_profile(candidate)
    after_raw = _canonical_profile_bytes(profile)
    before_raw = _read_document_bytes(paths.document)
    backup_id: str | None = None
    if before_raw is not None:
        backup_id = _new_id()
        paths.backup_dir.mkdir(parents=True, exist_ok=True)
        (paths.backup_dir / f"{backup_id}.json").write_bytes(before_raw)

    _atomic_write_bytes(paths.document, after_raw)

    audit_id = _write_audit_envelope(
        paths,
        op="apply",
        actor=actor,
        before_raw=before_raw,
        after_raw=after_raw,
        backup_id=backup_id,
    )
    return ApplyResult(
        backup_id=backup_id,
        audit_id=audit_id,
        effective_after=profile_to_safe_dict(profile),
        new_revision=revision_for_bytes(after_raw),
    )


def save_profile(
    root: Path | None,
    profile: GoHamSocialProfile,
    *,
    actor: str = "system",
) -> ApplyResult:
    """Persist an internally-trusted profile mutation with audit.

    Autonomous tick execution is not an operator-facing write route, so it must
    not depend on ``HAM_SOCIAL_AUTONOMY_WRITE_TOKEN`` being configured. This
    helper shares the same atomic write, backup, path-safety, and audit envelope
    behavior as ``apply_social_autonomy_profile`` while intentionally omitting
    the external write-token gate.
    """

    paths = _store_paths(root)
    _assert_safe_write_path(paths)

    after_raw = _canonical_profile_bytes(profile)
    before_raw = _read_document_bytes(paths.document)
    backup_id: str | None = None
    if before_raw is not None:
        backup_id = _new_id()
        paths.backup_dir.mkdir(parents=True, exist_ok=True)
        (paths.backup_dir / f"{backup_id}.json").write_bytes(before_raw)

    _atomic_write_bytes(paths.document, after_raw)
    audit_id = _write_audit_envelope(
        paths,
        op="apply",
        actor=actor,
        before_raw=before_raw,
        after_raw=after_raw,
        backup_id=backup_id,
    )
    return ApplyResult(
        backup_id=backup_id,
        audit_id=audit_id,
        effective_after=profile_to_safe_dict(profile),
        new_revision=revision_for_bytes(after_raw),
    )


def _write_audit_envelope(
    paths: _StorePaths,
    *,
    op: str,
    actor: str,
    before_raw: bytes | None,
    after_raw: bytes | None,
    backup_id: str | None = None,
    restored_from_backup_id: str | None = None,
) -> str:
    paths.audit_dir.mkdir(parents=True, exist_ok=True)
    audit_id = _new_id()
    payload = {
        "audit_id": audit_id,
        "op": op,
        "timestamp": _iso_timestamp(),
        "actor": actor,
        "backup_id": backup_id,
        "restored_from_backup_id": restored_from_backup_id,
        "before_digest": revision_for_bytes(before_raw),
        "after_digest": revision_for_bytes(after_raw),
        "before": _snapshot_from_bytes(before_raw),
        "after": _snapshot_from_bytes(after_raw),
        "result": "ok",
    }
    (paths.audit_dir / f"{audit_id}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return audit_id


def rollback_social_autonomy_profile(
    root: Path | None,
    backup_id: str,
    *,
    token: str | None,
    actor: str = "system",
) -> RollbackResult:
    """Restore a previously captured backup byte-for-byte and audit the rollback."""
    _require_write_token(token)
    if not _BACKUP_ID_RE.match(backup_id):
        raise ValueError("backup_id has invalid shape")

    paths = _store_paths(root)
    _assert_safe_write_path(paths)
    backup_path = paths.backup_dir / f"{backup_id}.json"
    try:
        backup_raw = backup_path.read_bytes()
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"backup {backup_id!r} not found") from exc
    _doc_to_profile_or_default(_parse_document_bytes(backup_raw))

    before_raw = _read_document_bytes(paths.document)
    _atomic_write_bytes(paths.document, backup_raw)
    audit_id = _write_audit_envelope(
        paths,
        op="rollback",
        actor=actor,
        before_raw=before_raw,
        after_raw=backup_raw,
        restored_from_backup_id=backup_id,
    )
    restored = _doc_to_profile_or_default(_parse_document_bytes(backup_raw))
    return RollbackResult(
        backup_id=backup_id,
        audit_id=audit_id,
        effective_after=profile_to_safe_dict(restored),
        new_revision=revision_for_bytes(backup_raw),
    )


def social_autonomy_writes_enabled() -> bool:
    """Return whether the autonomy write token env var is configured."""
    return bool((os.environ.get("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN") or "").strip())


# ---------------------------------------------------------------------------
# Protocol + file-backend wrapper + factory
# ---------------------------------------------------------------------------


@runtime_checkable
class SocialAutonomyStoreProtocol(Protocol):
    """Backend-agnostic social autonomy profile store contract.

    Both :class:`SocialAutonomyFileStore` (file-backed) and
    ``FirestoreSocialAutonomyStore`` satisfy this Protocol. Callers should
    treat :func:`get_social_autonomy_store` as returning this Protocol type.
    """

    def read(self, root: Path | None = None) -> GoHamSocialProfile: ...
    def preview(
        self,
        root: Path | None,
        candidate: GoHamSocialProfile | dict[str, Any],
    ) -> dict[str, Any]: ...
    def apply(
        self,
        root: Path | None,
        candidate: GoHamSocialProfile | dict[str, Any],
        *,
        token: str | None,
        actor: str = "system",
    ) -> ApplyResult: ...
    def save(
        self,
        root: Path | None,
        profile: GoHamSocialProfile,
        *,
        actor: str = "system",
    ) -> ApplyResult: ...
    def rollback(
        self,
        root: Path | None,
        backup_id: str,
        *,
        token: str | None,
        actor: str = "system",
    ) -> RollbackResult: ...
    def writes_enabled(self) -> bool: ...
    def path(self, root: Path | None = None) -> Path: ...


class SocialAutonomyFileStore:
    """File-backed social autonomy profile store (wraps module-level functions)."""

    def read(self, root: Path | None = None) -> GoHamSocialProfile:
        return read_social_autonomy_profile(root)

    def preview(
        self,
        root: Path | None,
        candidate: GoHamSocialProfile | dict[str, Any],
    ) -> dict[str, Any]:
        return preview_social_autonomy_profile(root, candidate)

    def apply(
        self,
        root: Path | None,
        candidate: GoHamSocialProfile | dict[str, Any],
        *,
        token: str | None,
        actor: str = "system",
    ) -> ApplyResult:
        return apply_social_autonomy_profile(root, candidate, token=token, actor=actor)

    def save(
        self,
        root: Path | None,
        profile: GoHamSocialProfile,
        *,
        actor: str = "system",
    ) -> ApplyResult:
        return save_profile(root, profile, actor=actor)

    def rollback(
        self,
        root: Path | None,
        backup_id: str,
        *,
        token: str | None,
        actor: str = "system",
    ) -> RollbackResult:
        return rollback_social_autonomy_profile(root, backup_id, token=token, actor=actor)

    def writes_enabled(self) -> bool:
        return social_autonomy_writes_enabled()

    def path(self, root: Path | None = None) -> Path:
        return social_autonomy_path(root)


def build_social_autonomy_store() -> SocialAutonomyStoreProtocol:
    """Pick a social autonomy profile store backend based on env.

    Defaults to :class:`SocialAutonomyFileStore` so local dev keeps working
    without any env vars. ``HAM_SOCIAL_AUTONOMY_STORE_BACKEND=firestore``
    selects the Firestore backend (lazy-imported so the SDK is not required
    for local dev).
    """
    backend = (os.environ.get(_SOCIAL_AUTONOMY_STORE_BACKEND_ENV) or "").strip().lower()
    if backend == "firestore":
        from src.ham.social_autonomy.firestore_store import (  # noqa: PLC0415
            FirestoreSocialAutonomyStore,
        )

        return FirestoreSocialAutonomyStore()
    if backend not in ("", "file"):
        _LOG.warning(
            "Unknown %s=%r; falling back to file backend.",
            _SOCIAL_AUTONOMY_STORE_BACKEND_ENV,
            backend,
        )
    return SocialAutonomyFileStore()


_social_autonomy_store_singleton: SocialAutonomyStoreProtocol | None = None


def get_social_autonomy_store() -> SocialAutonomyStoreProtocol:
    """Lazy singleton accessor for the configured social autonomy profile store."""
    global _social_autonomy_store_singleton
    if _social_autonomy_store_singleton is None:
        _social_autonomy_store_singleton = build_social_autonomy_store()
    return _social_autonomy_store_singleton


def social_autonomy_profile_persisted(
    store: SocialAutonomyStoreProtocol,
    root: Path | None = None,
) -> bool:
    """Return whether a persisted autonomy profile exists for the configured backend."""
    backend = (os.environ.get(_SOCIAL_AUTONOMY_STORE_BACKEND_ENV) or "").strip().lower()
    if backend == "firestore":
        from src.ham.social_autonomy.firestore_store import FirestoreSocialAutonomyStore

        if isinstance(store, FirestoreSocialAutonomyStore):
            return store.profile_document_exists(root)
        return False
    return social_autonomy_path(root).is_file()


def load_social_autonomy_profile_for_tick(
    root: Path | str | None = None,
) -> tuple[GoHamSocialProfile | None, SocialAutonomyStoreProtocol]:
    """Load the autonomy profile for tick execution via the configured store backend.

    Returns ``(None, store)`` when no profile is persisted in the active backend.
    Firestore SDK failures propagate as :class:`FirestoreSocialAutonomyStoreError`
    without falling back to the file backend.
    """
    store = get_social_autonomy_store()
    resolved = Path(root) if root is not None else Path.cwd()
    if not social_autonomy_profile_persisted(store, resolved):
        return None, store
    try:
        profile = store.read(resolved)
    except SocialAutonomyStoreError as exc:
        if isinstance(exc.__cause__, json.JSONDecodeError):
            raise exc.__cause__ from exc
        raise
    return profile, store


def set_social_autonomy_store_for_tests(
    store: SocialAutonomyStoreProtocol | None,
) -> None:
    """Replace the global social autonomy store (``None`` restores lazy default)."""
    global _social_autonomy_store_singleton
    _social_autonomy_store_singleton = store
