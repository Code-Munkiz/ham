"""Tests for Phase 2G.1 image generation REST surface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.generated_media_store import LocalDiskGeneratedMediaStore, reset_generated_media_store_for_tests, set_generated_media_store_for_tests
from src.ham.media_provider_adapter import (
    SyntheticTestOnlyImageAdapter,
    UnconfiguredImageProviderAdapter,
    set_image_generation_adapter_for_tests,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_adapters() -> None:
    reset_generated_media_store_for_tests()
    set_image_generation_adapter_for_tests(None)
    yield
    reset_generated_media_store_for_tests()
    set_image_generation_adapter_for_tests(None)


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
