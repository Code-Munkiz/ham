"""GCS-backed object reads/writes for managed snapshots."""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable


@runtime_checkable
class SnapshotObjectStorage(Protocol):
    def bucket_name(self) -> str | None:
        """Return bucket identifier for audit rows."""

    def write_object(self, object_path: str, data: bytes, *, content_type: str | None = None) -> None:
        """Write UTF-8/bytes blob (object_path uses forward slashes, no gs:// prefix)."""

    def read_object(self, object_path: str) -> bytes | None:
        """Return blob bytes or None if missing."""

    def object_exists(self, object_path: str) -> bool: ...


class DictSnapshotObjectStorage:
    """In-memory storage for pytest (no network)."""

    __slots__ = ("_objs", "_bucket")

    def __init__(self, bucket: str = "test-bucket") -> None:
        self._objs: dict[str, bytes] = {}
        self._bucket = bucket

    def bucket_name(self) -> str | None:
        return self._bucket

    def write_object(self, object_path: str, data: bytes, *, content_type: str | None = None) -> None:
        del content_type  # MVP: ignore
        self._objs[object_path] = data

    def read_object(self, object_path: str) -> bytes | None:
        return self._objs.get(object_path)

    def object_exists(self, object_path: str) -> bool:
        return object_path in self._objs


class GoogleCloudSnapshotObjectStorage:
    """Real GCS uploads (lazy client)."""

    __slots__ = ("_bucket_name", "_client")

    def __init__(
        self,
        bucket_name: str,
        *,
        client: object | None = None,
    ) -> None:
        self._bucket_name = bucket_name.strip()
        self._client = client

    def bucket_name(self) -> str | None:
        return self._bucket_name or None

    def _blob(self, object_path: str):
        from google.cloud import storage  # noqa: PLC0415

        cl = self._client or storage.Client()
        bucket = cl.bucket(self._bucket_name)
        return bucket.blob(object_path)

    def write_object(self, object_path: str, data: bytes, *, content_type: str | None = None) -> None:
        b = self._blob(object_path)
        b.upload_from_string(data, content_type=content_type or "application/octet-stream")

    def read_object(self, object_path: str) -> bytes | None:
        b = self._blob(object_path)
        if not b.exists():
            return None
        return bytes(b.download_as_bytes())

    def object_exists(self, object_path: str) -> bool:
        return bool(self._blob(object_path).exists())


def gcs_snapshot_bucket_from_env() -> str | None:
    raw = (os.environ.get("HAM_MANAGED_SNAPSHOT_GCS_BUCKET") or "").strip()
    return raw or None


def snapshot_object_storage_from_env() -> GoogleCloudSnapshotObjectStorage | None:
    b = gcs_snapshot_bucket_from_env()
    return GoogleCloudSnapshotObjectStorage(b) if b else None
