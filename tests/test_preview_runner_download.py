from __future__ import annotations

import importlib.util
from pathlib import Path
from zipfile import ZipFile

import pytest


def _load_module():
    module_path = Path("docker/preview-runner/download_preview_source.py").resolve()
    spec = importlib.util.spec_from_file_location("download_preview_source", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load download_preview_source module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_gs_uri_accepts_bucket_and_object() -> None:
    module = _load_module()
    bucket, object_path = module.parse_gs_uri("gs://preview-bucket/path/to/preview-source.zip")
    assert bucket == "preview-bucket"
    assert object_path == "path/to/preview-source.zip"


@pytest.mark.parametrize(
    "uri",
    (
        "https://example.com/preview.zip",
        "gs://preview-bucket",
        "gs:///obj.zip",
        "gs://preview-bucket/",
    ),
)
def test_parse_gs_uri_rejects_invalid_inputs(uri: str) -> None:
    module = _load_module()
    with pytest.raises(ValueError):
        module.parse_gs_uri(uri)


def test_safe_extract_zip_rejects_path_traversal(tmp_path: Path) -> None:
    module = _load_module()
    archive_path = tmp_path / "payload.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.txt", "bad")
    with pytest.raises(ValueError):
        module.safe_extract_zip(archive_path, tmp_path / "dest")


def test_safe_extract_zip_extracts_valid_archive(tmp_path: Path) -> None:
    module = _load_module()
    archive_path = tmp_path / "payload.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("package.json", '{"name":"demo"}')
        archive.writestr("src/main.tsx", "console.log('ok')")
    destination = tmp_path / "dest"
    module.safe_extract_zip(archive_path, destination)
    assert (destination / "package.json").exists()
    assert (destination / "src" / "main.tsx").exists()
