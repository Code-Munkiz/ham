"""Tests for Phase 2G.1 image generation REST surface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.generated_media_store import LocalDiskGeneratedMediaStore, reset_generated_media_store_for_tests, set_generated_media_store_for_tests
from src.ham.chat_attachment_store import (
    AttachmentRecord,
    LocalDiskAttachmentStore,
    kind_for_mime,
    set_chat_attachment_store_for_tests,
)
from src.ham.media_provider_adapter import (
    SyntheticTestOnlyImageAdapter,
    UnconfiguredImageProviderAdapter,
    set_image_generation_adapter_for_tests,
)


_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\x0dIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0bIDATx\x9cc``\x00\x00\x00\x02\x00\x01\xe2!\x03\x1a\x00\x00\x00"
    b"\x00IEND\xaeB`\x82"
)


client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_adapters() -> None:
    reset_generated_media_store_for_tests()
    set_image_generation_adapter_for_tests(None)
    set_chat_attachment_store_for_tests(None)
    yield
    reset_generated_media_store_for_tests()
    set_image_generation_adapter_for_tests(None)
    set_chat_attachment_store_for_tests(None)


@pytest.fixture
def local_gm_store(tmp_path: Path) -> LocalDiskGeneratedMediaStore:
    d = tmp_path / "gm"
    d.mkdir()
    store = LocalDiskGeneratedMediaStore(d)
    set_generated_media_store_for_tests(store)
    return store


def test_generate_image_not_configured_returns_503(local_gm_store: LocalDiskGeneratedMediaStore) -> None:
    _ = local_gm_store
    set_image_generation_adapter_for_tests(UnconfiguredImageProviderAdapter())
    r = client.post("/api/media/images/generate", json={"prompt": "red dot"})
    assert r.status_code == 503
    assert r.json()["detail"]["error"]["code"] == "IMAGE_GEN_NOT_CONFIGURED"


def test_generate_image_whitespace_only_prompt_rejected(local_gm_store: LocalDiskGeneratedMediaStore) -> None:
    _ = local_gm_store
    set_image_generation_adapter_for_tests(SyntheticTestOnlyImageAdapter())
    r = client.post("/api/media/images/generate", json={"prompt": "   "})
    assert r.status_code == 400


def test_generate_image_prompt_too_long(local_gm_store: LocalDiskGeneratedMediaStore, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_MEDIA_IMAGE_PROMPT_MAX_CHARS", "50")
    _ = local_gm_store
    set_image_generation_adapter_for_tests(SyntheticTestOnlyImageAdapter())
    r = client.post("/api/media/images/generate", json={"prompt": "x" * 80})
    assert r.status_code == 400


def test_generate_response_shape(local_gm_store: LocalDiskGeneratedMediaStore) -> None:
    _ = local_gm_store
    set_image_generation_adapter_for_tests(SyntheticTestOnlyImageAdapter())

    r = client.post("/api/media/images/generate", json={"prompt": "a simple test image", "model_id": "synthetic/x"})
    assert r.status_code == 200, r.text
    body = r.json()
    gid = body["generated_media_id"]
    assert gid.startswith("hamgm_")
    assert body["mime_type"] == "image/png"
    assert body["download_url"].endswith(f"/api/media/artifacts/{gid}/download")
    assert "gs://" not in json.dumps(body)


def test_metadata_no_storage_ref(local_gm_store: LocalDiskGeneratedMediaStore) -> None:
    _ = local_gm_store
    set_image_generation_adapter_for_tests(SyntheticTestOnlyImageAdapter())
    gid = (
        client.post("/api/media/images/generate", json={"prompt": "blue square", "model_id": "synthetic/x"})
        .json()["generated_media_id"]
    )

    m = client.get(f"/api/media/artifacts/{gid}")
    assert m.status_code == 200
    j = m.json()
    assert "storage_blob_key" not in j
    assert "gs://" not in json.dumps(j)
    assert j["generated_media_id"] == gid
    assert "download_url" in j


def test_download_headers_and_bytes(local_gm_store: LocalDiskGeneratedMediaStore) -> None:
    _ = local_gm_store
    set_image_generation_adapter_for_tests(SyntheticTestOnlyImageAdapter())
    gid = (
        client.post("/api/media/images/generate", json={"prompt": "green", "model_id": "x"})
        .json()["generated_media_id"]
    )
    d = client.get(f"/api/media/artifacts/{gid}/download")
    assert d.status_code == 200
    assert d.headers.get("cache-control") == "no-store"
    assert d.headers.get("content-type") == "image/png"
    assert len(d.content) >= 67


def _configure_ref_capable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_MEDIA_IMAGE_GENERATION_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-fake-long-key-for-plausible-xxxx")
    monkeypatch.setenv("HAM_MEDIA_IMAGE_DEFAULT_MODEL", "black-forest-labs/flux.2-pro")
    monkeypatch.setenv("HAM_MEDIA_IMAGE_TO_IMAGE_ENABLED", "true")


class CapturingSyntheticAdapter(SyntheticTestOnlyImageAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.last_ref: tuple[bytes, str] | None = None

    def generate_image(  # type: ignore[override]
        self,
        *,
        prompt: str,
        model_id: str | None,
        reference_image: tuple[bytes, str] | None = None,
    ):
        self.last_ref = reference_image
        return super().generate_image(prompt=prompt, model_id=model_id, reference_image=reference_image)


def test_generate_with_reference_resolves_attachment(
    local_gm_store: LocalDiskGeneratedMediaStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = local_gm_store
    _configure_ref_capable(monkeypatch)

    capturing = CapturingSyntheticAdapter()
    set_image_generation_adapter_for_tests(capturing)

    att = LocalDiskAttachmentStore(tmp_path / "att")
    set_chat_attachment_store_for_tests(att)
    aid = att.new_id()
    att.put(
        _TINY_PNG,
        AttachmentRecord(
            id=aid,
            filename="r.png",
            mime="image/png",
            size=len(_TINY_PNG),
            owner_key="",
            kind=kind_for_mime("image/png"),
        ),
    )

    r = client.post(
        "/api/media/images/generate",
        json={"prompt": "make it more minimal", "model_id": "x", "reference_attachment_id": aid},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["generated_from_reference_image"] is True

    gid = body["generated_media_id"]
    meta = client.get(f"/api/media/artifacts/{gid}").json()
    assert meta.get("generated_from_reference_image") is True

    ref = getattr(capturing, "last_ref", None)
    assert isinstance(ref, tuple)
    assert ref[1] == "image/png"
    assert isinstance(ref[0], bytes)


def test_reference_feature_disabled_returns_503(
    local_gm_store: LocalDiskGeneratedMediaStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = local_gm_store
    monkeypatch.setenv("HAM_MEDIA_IMAGE_GENERATION_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-fake-long-key-for-plausible-xxxx")
    monkeypatch.setenv("HAM_MEDIA_IMAGE_DEFAULT_MODEL", "black-forest-labs/flux.2-pro")
    monkeypatch.setenv("HAM_MEDIA_IMAGE_TO_IMAGE_ENABLED", "false")

    set_image_generation_adapter_for_tests(SyntheticTestOnlyImageAdapter())

    att = LocalDiskAttachmentStore(tmp_path / "ca")
    set_chat_attachment_store_for_tests(att)
    aid = att.new_id()
    att.put(
        _TINY_PNG,
        AttachmentRecord(
            id=aid,
            filename="r.png",
            mime="image/png",
            size=len(_TINY_PNG),
            owner_key="",
            kind=kind_for_mime("image/png"),
        ),
    )

    r = client.post(
        "/api/media/images/generate",
        json={"prompt": "edit", "reference_attachment_id": aid},
    )
    assert r.status_code == 503
    assert r.json()["detail"]["error"]["code"] == "IMAGE_TO_IMAGE_NOT_SUPPORTED"


def test_reference_not_found(local_gm_store: LocalDiskGeneratedMediaStore, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = local_gm_store
    _configure_ref_capable(monkeypatch)
    set_image_generation_adapter_for_tests(SyntheticTestOnlyImageAdapter())
    r = client.post(
        "/api/media/images/generate",
        json={
            "prompt": "redo",
            "reference_attachment_id": "hamatt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        },
    )
    assert r.status_code == 404


def test_reference_must_be_image_kind(
    local_gm_store: LocalDiskGeneratedMediaStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = local_gm_store
    _configure_ref_capable(monkeypatch)
    set_image_generation_adapter_for_tests(SyntheticTestOnlyImageAdapter())

    att = LocalDiskAttachmentStore(tmp_path / "ca2")
    set_chat_attachment_store_for_tests(att)
    aid = att.new_id()
    att.put(
        b"%PDF-1.4\n",
        AttachmentRecord(
            id=aid,
            filename="r.pdf",
            mime="application/pdf",
            size=8,
            owner_key="",
            kind="file",
        ),
    )

    r = client.post("/api/media/images/generate", json={"prompt": "ref", "reference_attachment_id": aid})
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "IMAGE_GEN_REFERENCE_NOT_IMAGE"


def test_reference_too_large(
    local_gm_store: LocalDiskGeneratedMediaStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = local_gm_store
    _configure_ref_capable(monkeypatch)
    monkeypatch.setenv("HAM_MEDIA_REFERENCE_IMAGE_MAX_BYTES", "180")
    set_image_generation_adapter_for_tests(SyntheticTestOnlyImageAdapter())

    blob = _TINY_PNG * 120
    assert len(blob) >= 181

    att = LocalDiskAttachmentStore(tmp_path / "ca3")
    set_chat_attachment_store_for_tests(att)
    aid = att.new_id()
    att.put(
        blob,
        AttachmentRecord(
            id=aid,
            filename="huge.png",
            mime="image/png",
            size=len(blob),
            owner_key="",
            kind="image",
        ),
    )

    r = client.post("/api/media/images/generate", json={"prompt": "x", "reference_attachment_id": aid})
    assert r.status_code == 413


def test_reference_forbidden_when_owner_mismatch(
    local_gm_store: LocalDiskGeneratedMediaStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = local_gm_store
    _configure_ref_capable(monkeypatch)
    set_image_generation_adapter_for_tests(SyntheticTestOnlyImageAdapter())

    att = LocalDiskAttachmentStore(tmp_path / "ca4")
    set_chat_attachment_store_for_tests(att)
    aid = att.new_id()
    att.put(
        _TINY_PNG,
        AttachmentRecord(
            id=aid,
            filename="r.png",
            mime="image/png",
            size=len(_TINY_PNG),
            owner_key="principal-a",
            kind=kind_for_mime("image/png"),
        ),
    )

    r = client.post(
        "/api/media/images/generate",
        json={"prompt": "crop", "reference_attachment_id": aid},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["error"]["code"] == "ATTACHMENT_FORBIDDEN"
