"""Unit tests for :class:`GcsAttachmentStore` using in-memory blob fakes."""
from __future__ import annotations


from typing import Any
from unittest.mock import MagicMock

import pytest

import src.ham.chat_attachment_store as attachment_mod
from src.ham.chat_attachment_store import AttachmentRecord, GcsAttachmentStore


class _FakeBlob:
    __test__ = False

    def __init__(self) -> None:
        self.payload: bytes | None = None
        self.ct: str | None = None

    def exists(self) -> bool:
        return self.payload is not None

    def upload_from_string(self, data: str | bytes, content_type: str | None = None, **_kw: Any) -> None:
        self.payload = data if isinstance(data, bytes) else data.encode("utf-8")
        self.ct = content_type

    def download_as_bytes(self) -> bytes:
        if self.payload is None:
            raise OSError("no data")
        return self.payload


class _FakeBucket:
    __test__ = False

    def __init__(self) -> None:
        self._blobs: dict[str, _FakeBlob] = {}

    def blob(self, name: str) -> _FakeBlob:
        if name not in self._blobs:
            self._blobs[name] = _FakeBlob()
        return self._blobs[name]


_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\x0dIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0bIDATx\x9cc``\x00\x00\x00\x02\x00\x01\xe2!\x03\x1a\x00\x00\x00"
    b"\x00IEND\xaeB`\x82"
)


def test_gcs_store_put_get_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        attachment_mod,
        "_import_gcs_storage",
        lambda: pytest.fail("unexpected real GCS import"),
        raising=True,
    )

    bucket = _FakeBucket()
    client = MagicMock()
    store = GcsAttachmentStore("dummy-bucket", prefix="tst/", _inject_client_bucket=(client, bucket))

    aid = "hamatt_" + "a" * 64

    rec = AttachmentRecord(
        id=aid,
        filename="p.png",
        mime="image/png",
        size=len(_TINY_PNG),
        owner_key="u1",
        kind="image",
    )
    store.put(_TINY_PNG, rec)

    meta = store.get_meta(aid)
    assert meta is not None and meta.filename == "p.png"

    got = store.get(aid)
    assert got is not None
    data, mr = got
    assert data == _TINY_PNG and mr.mime == "image/png"
    assert store.exists(aid) is True


def test_build_store_gcs_missing_bucket_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CHAT_ATTACHMENT_STORE", "gcs")
    monkeypatch.delenv("HAM_CHAT_ATTACHMENT_BUCKET", raising=False)
    monkeypatch.delenv("HAM_CHAT_ATTACHMENT_GCS_BUCKET", raising=False)

    monkeypatch.setattr(attachment_mod, "_singleton", None)

    with pytest.raises(ValueError, match="HAM_CHAT_ATTACHMENT_BUCKET"):
        attachment_mod.build_chat_attachment_store()


def test_prefix_normalizes_for_object_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        attachment_mod,
        "_import_gcs_storage",
        lambda: pytest.fail("unexpected real GCS import"),
        raising=True,
    )

    bucket = _FakeBucket()
    store_a = GcsAttachmentStore(
        "b",
        prefix=" chat-attachments/ ",
        _inject_client_bucket=(MagicMock(), bucket),
    )
    aid = "hamatt_" + "c" * 64
    rec = AttachmentRecord(
        id=aid,
        filename="x.png",
        mime="image/png",
        size=1,
        owner_key="",
        kind="image",
    )
    store_a.put(b"x", rec)
    key = store_a._key_data(aid)
    assert key.startswith("chat-attachments/")
    assert key.endswith(f"{aid}.bin")
