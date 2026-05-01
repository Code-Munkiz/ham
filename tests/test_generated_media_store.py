"""Unit tests for ``GeneratedMediaRecord`` persistence (local disk)."""

from __future__ import annotations

from pathlib import Path

from src.ham.generated_media_store import GeneratedMediaRecord, LocalDiskGeneratedMediaStore, is_safe_generated_media_id


def test_generated_media_roundtrip_local(tmp_path: Path) -> None:
    store = LocalDiskGeneratedMediaStore(tmp_path)
    gmid = store.new_id()
    assert gmid.startswith("hamgm_")
    assert is_safe_generated_media_id(gmid)

    png = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\x0dIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0bIDATx\x9cc``\x00\x00\x00\x02\x00\x01\xe2!\x03\x1a\x00\x00\x00"
        b"\x00IEND\xaeB`\x82"
    )

    rec0 = GeneratedMediaRecord(
        id=gmid,
        media_type="image",
        mime="image/png",
        size_bytes=len(png),
        owner_key="owner_test",
        status="ready",
        safe_display_name="ham-generated.png",
        prompt_digest="a" * 64,
        prompt_excerpt="tiny",
        provider_slug="test_synthetic",
        model_id="x/y",
        width=1,
        height=1,
        storage_blob_key=None,
    )
    store.put(png, rec0)

    meta = store.get_meta(gmid)
    assert meta is not None
    payload = meta.to_public_meta()
    assert "storage_blob_key" not in payload
    assert payload["mime_type"] == "image/png"
    assert payload["generated_media_id"] == gmid

    got = store.get(gmid)
    assert got is not None
    blob, mr = got
    assert blob == png
    assert mr.mime == "image/png"
