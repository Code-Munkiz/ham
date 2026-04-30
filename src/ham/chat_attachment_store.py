"""
HAM workspace chat file attachments: local disk store (dev / default) with a pluggable
interface for a future GCS implementation (see :class:`GcsAttachmentStore` stub).

All blob paths are under a configured base directory; attachment IDs are opaque
random tokens (never user-supplied paths).
"""
from __future__ import annotations

import json
import os
import re
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Opaque id prefix for logs / routing; body is unguessable random.
_ID_RE = re.compile(r"^hamatt_[A-Za-z0-9_\-]{8,200}$")

CHAT_UPLOAD_ALLOWED_MIME = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
        "image/gif",
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "text/markdown",
    }
)


def is_safe_attachment_id(aid: str) -> bool:
    return bool(aid and _ID_RE.match(aid.strip()))


def _normalize_mime(m: str) -> str:
    x = (m or "").strip().lower()
    if x == "image/jpg":
        return "image/jpeg"
    return x


def kind_for_mime(mime: str) -> str:
    m = _normalize_mime(mime)
    if m.startswith("image/"):
        return "image"
    return "file"


@dataclass
class AttachmentRecord:
    id: str
    filename: str
    mime: str
    size: int
    owner_key: str
    kind: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "filename": self.filename,
            "mime": self.mime,
            "size": self.size,
            "owner_key": self.owner_key,
            "kind": self.kind,
        }


class ChatAttachmentStore(ABC):
    """Pluggable storage for chat attachment bytes (local disk, future GCS, etc.)."""

    @abstractmethod
    def new_id(self) -> str: ...

    @abstractmethod
    def put(self, data: bytes, rec: AttachmentRecord) -> None: ...

    @abstractmethod
    def get(self, aid: str) -> tuple[bytes, AttachmentRecord] | None:
        """Return (bytes, record) or None if missing."""
        ...

    @abstractmethod
    def get_meta(self, aid: str) -> AttachmentRecord | None: ...


def default_attachment_max_bytes() -> int:
    raw = (os.environ.get("HAM_CHAT_ATTACHMENT_MAX_BYTES") or "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    raw_img = (os.environ.get("HAM_CHAT_IMAGE_MAX_BYTES") or "").strip()
    if raw_img:
        try:
            return max(1, int(raw_img))
        except ValueError:
            pass
    return 20 * 1024 * 1024


def default_attachment_dir() -> Path:
    env = (os.environ.get("HAM_CHAT_ATTACHMENT_DIR") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    base = (os.environ.get("HAM_DATA_DIR") or "").strip()
    if base:
        return (Path(base).expanduser().resolve() / "chat-attachments")
    return Path(os.environ.get("TMPDIR", "/tmp") or "/tmp") / "ham-chat-attachments"


def safe_upload_filename(name: str) -> str:
    s = (name or "").strip() or "attachment"
    s = s.replace("\x00", "").replace("\\", "_").replace("/", "_")
    if ".." in s:
        s = s.replace("..", "_")
    return s[:200]


def _meta_path(base: Path, aid: str) -> Path:
    return base / f"{aid}.meta.json"


def _data_path(base: Path, aid: str) -> Path:
    return base / f"{aid}.bin"


class LocalDiskAttachmentStore(ChatAttachmentStore):
    """
    Store blobs as ``{id}.bin`` and JSON metadata as ``{id}.meta.json`` under a base directory.
    """

    def __init__(self, base: Path) -> None:
        self._base = Path(base)
        self._base.mkdir(parents=True, exist_ok=True)

    def new_id(self) -> str:
        return f"hamatt_{secrets.token_hex(32)}"

    def put(self, data: bytes, rec: AttachmentRecord) -> None:
        aid = rec.id
        if not is_safe_attachment_id(aid):
            raise ValueError("Invalid attachment id.")
        dpath = _data_path(self._base, aid)
        mpath = _meta_path(self._base, aid)
        dpath.write_bytes(data)
        mpath.write_text(
            json.dumps(rec.to_dict(), ensure_ascii=False, indent=0),
            encoding="utf-8",
        )

    def get(self, aid: str) -> tuple[bytes, AttachmentRecord] | None:
        meta = self.get_meta(aid)
        if meta is None:
            return None
        dpath = _data_path(self._base, aid)
        if not dpath.is_file():
            return None
        return dpath.read_bytes(), meta

    def get_meta(self, aid: str) -> AttachmentRecord | None:
        if not is_safe_attachment_id(aid):
            return None
        mpath = _meta_path(self._base, aid)
        if not mpath.is_file():
            return None
        try:
            doc = json.loads(mpath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return None
        if not isinstance(doc, dict):
            return None
        try:
            return AttachmentRecord(
                id=str(doc.get("id") or aid),
                filename=str(doc.get("filename") or "file"),
                mime=_normalize_mime(str(doc.get("mime") or "application/octet-stream")),
                size=int(doc.get("size") or 0),
                owner_key=str(doc.get("owner_key") or ""),
                kind=str(doc.get("kind") or "file"),
            )
        except (TypeError, ValueError):
            return None


class GcsAttachmentStore(ChatAttachmentStore):
    """
    Placeholder for a future GCS-backed store (set ``HAM_CHAT_ATTACHMENT_STORE=gcs`` +
    ``HAM_CHAT_ATTACHMENT_GCS_BUCKET`` + ADC). Not implemented in this PR — use
    :class:`LocalDiskAttachmentStore` for production until wired.
    """

    def new_id(self) -> str:  # pragma: no cover
        raise NotImplementedError("GCS attachment store is not implemented yet. Use HAM_CHAT_ATTACHMENT_STORE=local.")

    def put(self, data: bytes, rec: AttachmentRecord) -> None:  # pragma: no cover
        raise NotImplementedError("GCS attachment store is not implemented yet.")

    def get(self, aid: str) -> tuple[bytes, AttachmentRecord] | None:  # pragma: no cover
        raise NotImplementedError("GCS attachment store is not implemented yet.")

    def get_meta(self, aid: str) -> AttachmentRecord | None:  # pragma: no cover
        raise NotImplementedError("GCS attachment store is not implemented yet.")


def build_chat_attachment_store() -> ChatAttachmentStore:
    mode = (os.environ.get("HAM_CHAT_ATTACHMENT_STORE") or "local").strip().lower()
    if mode in ("gcs", "google", "gcp"):
        return GcsAttachmentStore()
    return LocalDiskAttachmentStore(default_attachment_dir())


_singleton: ChatAttachmentStore | None = None


def get_chat_attachment_store() -> ChatAttachmentStore:
    global _singleton
    if _singleton is None:
        _singleton = build_chat_attachment_store()
    return _singleton


def set_chat_attachment_store_for_tests(store: ChatAttachmentStore) -> None:
    """Test hook to replace the process-global store."""
    global _singleton
    _singleton = store
