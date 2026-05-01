"""
HAM-generated media bytes (distinct from user chat attachments).

Opaque ids use ``hamgm_`` prefix. Blobs mirror attachment layout: ``{id}.bin`` + ``{id}.meta.json``
under ``HAM_GENERATED_MEDIA_PREFIX`` when using GCS, or beside local base dir.

Environment::

    HAM_GENERATED_MEDIA_STORE=local|gcs     (default: local)

Local::

    HAM_GENERATED_MEDIA_DIR or HAM_DATA_DIR/generated-media

GCS::

    HAM_GENERATED_MEDIA_BUCKET — if unset when store is gcs, falls back to chat attachment bucket
    HAM_GENERATED_MEDIA_PREFIX — default generated-media/

``storage_blob_key`` inside metadata is internal only — never expose to APIs.
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

_ID_RE = re.compile(r"^hamgm_[A-Za-z0-9_\-]{8,200}$")


def is_safe_generated_media_id(gmid: str) -> bool:
    return bool(gmid and _ID_RE.match(gmid.strip()))


@dataclass
class GeneratedMediaRecord:
    id: str
    media_type: str  # "image"
    mime: str
    size_bytes: int
    owner_key: str
    status: str  # ready | failed
    safe_display_name: str
    prompt_digest: str
    prompt_excerpt: str
    provider_slug: str | None
    model_id: str | None
    width: int | None
    height: int | None
    storage_blob_key: str | None  # internal: object key relative to bucket prefix

    def to_meta_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "media_type": self.media_type,
            "mime": self.mime,
            "size_bytes": self.size_bytes,
            "owner_key": self.owner_key,
            "status": self.status,
            "safe_display_name": self.safe_display_name,
            "prompt_digest": self.prompt_digest,
            "prompt_excerpt": self.prompt_excerpt,
            "provider_slug": self.provider_slug,
            "model_id": self.model_id,
            "width": self.width,
            "height": self.height,
            "storage_blob_key": self.storage_blob_key,
        }

    def to_public_meta(self) -> dict[str, Any]:
        """Metadata safe for GET /api/media/artifacts/{id} (no storage_blob_key)."""
        return {
            "generated_media_id": self.id,
            "media_type": self.media_type,
            "mime_type": self.mime,
            "size_bytes": self.size_bytes,
            "status": self.status,
            "safe_display_name": self.safe_display_name,
            "prompt_excerpt": self.prompt_excerpt,
            "provider": self.provider_slug,
            "model_id": self.model_id,
            "width": self.width,
            "height": self.height,
        }


class GeneratedMediaStore(ABC):
    """Pluggable persistence for synthesized media bytes."""

    @abstractmethod
    def new_id(self) -> str: ...

    @abstractmethod
    def put(self, data: bytes, rec: GeneratedMediaRecord) -> None: ...

    @abstractmethod
    def get(self, gmid: str) -> tuple[bytes, GeneratedMediaRecord] | None: ...

    @abstractmethod
    def get_meta(self, gmid: str) -> GeneratedMediaRecord | None: ...


def _meta_path(base: Path, gmid: str) -> Path:
    return base / f"{gmid}.meta.json"


def _data_path(base: Path, gmid: str) -> Path:
    return base / f"{gmid}.bin"


class LocalDiskGeneratedMediaStore(GeneratedMediaStore):
    def __init__(self, base: Path) -> None:
        self._base = Path(base)
        self._base.mkdir(parents=True, exist_ok=True)

    def new_id(self) -> str:
        return f"hamgm_{secrets.token_hex(32)}"

    def put(self, data: bytes, rec: GeneratedMediaRecord) -> None:
        gid = rec.id
        if not is_safe_generated_media_id(gid):
            raise ValueError("Invalid generated media id.")
        blob_key = f"{gid}.bin"
        updated = GeneratedMediaRecord(
            id=rec.id,
            media_type=rec.media_type,
            mime=rec.mime,
            size_bytes=rec.size_bytes,
            owner_key=rec.owner_key,
            status=rec.status,
            safe_display_name=rec.safe_display_name,
            prompt_digest=rec.prompt_digest,
            prompt_excerpt=rec.prompt_excerpt,
            provider_slug=rec.provider_slug,
            model_id=rec.model_id,
            width=rec.width,
            height=rec.height,
            storage_blob_key=blob_key,
        )
        _data_path(self._base, gid).write_bytes(data)
        _meta_path(self._base, gid).write_text(
            json.dumps(updated.to_meta_dict(), ensure_ascii=False, indent=0),
            encoding="utf-8",
        )

    def get_meta(self, gmid: str) -> GeneratedMediaRecord | None:
        if not is_safe_generated_media_id(gmid):
            return None
        mpath = _meta_path(self._base, gmid)
        if not mpath.is_file():
            return None
        try:
            doc = json.loads(mpath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return None
        if not isinstance(doc, dict):
            return None
        try:
            return _record_from_meta(doc, gmid)
        except (TypeError, ValueError):
            return None

    def get(self, gmid: str) -> tuple[bytes, GeneratedMediaRecord] | None:
        meta = self.get_meta(gmid)
        if meta is None:
            return None
        dpath = _data_path(self._base, gmid)
        if not dpath.is_file():
            return None
        return dpath.read_bytes(), meta


def _record_from_meta(doc: dict[str, Any], fallback_id: str) -> GeneratedMediaRecord:
    w = doc.get("width")
    h = doc.get("height")
    return GeneratedMediaRecord(
        id=str(doc.get("id") or fallback_id),
        media_type=str(doc.get("media_type") or "image"),
        mime=str(doc.get("mime") or "application/octet-stream"),
        size_bytes=int(doc.get("size_bytes") or 0),
        owner_key=str(doc.get("owner_key") or ""),
        status=str(doc.get("status") or "ready"),
        safe_display_name=str(doc.get("safe_display_name") or "generated.png"),
        prompt_digest=str(doc.get("prompt_digest") or ""),
        prompt_excerpt=str(doc.get("prompt_excerpt") or ""),
        provider_slug=doc.get("provider_slug") if doc.get("provider_slug") else None,
        model_id=doc.get("model_id") if doc.get("model_id") else None,
        width=int(w) if w is not None else None,
        height=int(h) if h is not None else None,
        storage_blob_key=str(doc.get("storage_blob_key") or "") or None,
    )


def _import_gcs_storage() -> Any:
    try:
        from google.cloud import storage as gcs_storage  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "google-cloud-storage is required when HAM_GENERATED_MEDIA_STORE=gcs. "
            "Install it with: pip install google-cloud-storage",
        ) from exc
    return gcs_storage


def _normalized_gcs_prefix(raw: str) -> str:
    p = (raw or "").strip()
    if not p:
        return ""
    return p.strip("/").rstrip("/") + "/" if p.strip("/") else ""


class GcsGeneratedMediaStore(GeneratedMediaStore):
    def __init__(
        self,
        bucket_name: str,
        *,
        prefix: str = "",
        _inject_client_bucket: tuple[Any, Any] | None = None,
    ) -> None:
        if not bucket_name.strip():
            raise ValueError("GCS generated media store requires a non-empty bucket name.")
        self._pfx = _normalized_gcs_prefix(prefix)

        if _inject_client_bucket is not None:
            self._client, self._bucket = _inject_client_bucket
            return

        gcs_storage = _import_gcs_storage()
        self._client = gcs_storage.Client()
        self._bucket = self._client.bucket(bucket_name.strip())

    def _key_meta(self, gmid: str) -> str:
        return f"{self._pfx}{gmid}.meta.json"

    def _key_data(self, gmid: str) -> str:
        return f"{self._pfx}{gmid}.bin"

    def new_id(self) -> str:
        return f"hamgm_{secrets.token_hex(32)}"

    def put(self, data: bytes, rec: GeneratedMediaRecord) -> None:
        gid = rec.id
        if not is_safe_generated_media_id(gid):
            raise ValueError("Invalid generated media id.")
        data_key = self._key_data(gid)
        updated = GeneratedMediaRecord(
            id=rec.id,
            media_type=rec.media_type,
            mime=rec.mime,
            size_bytes=rec.size_bytes,
            owner_key=rec.owner_key,
            status=rec.status,
            safe_display_name=rec.safe_display_name,
            prompt_digest=rec.prompt_digest,
            prompt_excerpt=rec.prompt_excerpt,
            provider_slug=rec.provider_slug,
            model_id=rec.model_id,
            width=rec.width,
            height=rec.height,
            storage_blob_key=data_key,
        )
        kb = self._bucket.blob(data_key)
        kb.upload_from_string(data, content_type=rec.mime)
        km = self._bucket.blob(self._key_meta(gid))
        km.upload_from_string(
            json.dumps(updated.to_meta_dict(), ensure_ascii=False, indent=0),
            content_type="application/json; charset=utf-8",
        )

    def get_meta(self, gmid: str) -> GeneratedMediaRecord | None:
        if not is_safe_generated_media_id(gmid):
            return None
        km = self._bucket.blob(self._key_meta(gmid))
        try:
            if not km.exists():
                return None
            raw = km.download_as_bytes()
            doc = json.loads(raw.decode("utf-8"))
        except Exception:
            return None
        if not isinstance(doc, dict):
            return None
        try:
            return _record_from_meta(doc, gmid)
        except (TypeError, ValueError):
            return None

    def get(self, gmid: str) -> tuple[bytes, GeneratedMediaRecord] | None:
        meta = self.get_meta(gmid)
        if meta is None:
            return None
        kb = self._bucket.blob(self._key_data(gmid))
        try:
            if not kb.exists():
                return None
            data = kb.download_as_bytes()
        except Exception:
            return None
        return data, meta


def generated_media_bucket_from_env() -> str:
    b = (os.environ.get("HAM_GENERATED_MEDIA_BUCKET") or "").strip()
    if b:
        return b
    return (
        (os.environ.get("HAM_CHAT_ATTACHMENT_BUCKET") or "").strip()
        or (os.environ.get("HAM_CHAT_ATTACHMENT_GCS_BUCKET") or "").strip()
    )


def generated_media_prefix_from_env() -> str:
    return (os.environ.get("HAM_GENERATED_MEDIA_PREFIX") or "generated-media/").strip()


def default_generated_media_dir() -> Path:
    env = (os.environ.get("HAM_GENERATED_MEDIA_DIR") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    base = (os.environ.get("HAM_DATA_DIR") or "").strip()
    if base:
        return (Path(base).expanduser().resolve() / "generated-media")
    return Path(os.environ.get("TMPDIR", "/tmp") or "/tmp") / "ham-generated-media"


def build_generated_media_store() -> GeneratedMediaStore:
    mode = (os.environ.get("HAM_GENERATED_MEDIA_STORE") or "local").strip().lower()
    if mode in ("gcs", "google", "gcp"):
        bucket = generated_media_bucket_from_env()
        if not bucket:
            raise ValueError(
                "HAM_GENERATED_MEDIA_STORE=gcs requires HAM_GENERATED_MEDIA_BUCKET or "
                "HAM_CHAT_ATTACHMENT_BUCKET (fallback)",
            )
        return GcsGeneratedMediaStore(bucket, prefix=generated_media_prefix_from_env())
    return LocalDiskGeneratedMediaStore(default_generated_media_dir())


_singleton: GeneratedMediaStore | None = None


def get_generated_media_store() -> GeneratedMediaStore:
    global _singleton
    if _singleton is None:
        _singleton = build_generated_media_store()
    return _singleton


def set_generated_media_store_for_tests(store: GeneratedMediaStore) -> None:
    global _singleton
    _singleton = store


def reset_generated_media_store_for_tests() -> None:
    global _singleton
    _singleton = None
