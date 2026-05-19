"""Sanity-check Cloud Build wiring for ham-api Docker image metadata."""

from __future__ import annotations

from pathlib import Path


def test_cloudbuild_ham_api_yaml_wires_builder_metadata() -> None:
    root = Path(__file__).resolve().parents[1]
    yaml_path = root / "scripts" / "cloudbuild_ham_api.yaml"
    assert yaml_path.exists()
    text = yaml_path.read_text(encoding="utf-8")
    assert "_HAM_BUILD_SHA" in text
    assert "_HAM_BUILD_TIME" in text
    assert "_HAM_SERVICE_VERSION" in text
    assert "--build-arg=HAM_BUILD_SHA=${_HAM_BUILD_SHA}" in text
    assert "--tag=${_IMAGE}" in text
    assert "\nimages:" in text

