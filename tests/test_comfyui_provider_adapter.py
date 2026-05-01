"""ComfyUIImageProviderAdapter — manifest load + mocked REST flow (Phase 2G.6)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.ham.comfyui_provider_adapter import (
    ComfyUIImageProviderAdapter,
    comfyui_defaults_width_height,
    comfyui_image_generation_ready,
    load_comfy_manifest_and_workflow,
)
from src.ham.media_provider_adapter import ImageGenerationError, SyntheticTestOnlyImageAdapter


def _tiny_png_bytes() -> bytes:
    return SyntheticTestOnlyImageAdapter().generate_image(prompt="", model_id=None).data


def test_sdxl_manifest_fields_and_license_flag() -> None:
    root = Path(__file__).resolve().parents[1]
    man_path = root / "configs" / "media" / "comfyui" / "sdxl_baseline.manifest.json"
    data = json.loads(man_path.read_text(encoding="utf-8"))
    assert data.get("workflow_id") == "sdxl_baseline"
    assert data.get("model_family") == "sdxl"
    assert data.get("license_check_required") is True
    assert "required_inputs" in data
    assert "comfy_patches" in data
    raw = json.dumps(data)
    assert "gs://" not in raw
    assert "C:\\" not in raw
    wf_name = data.get("workflow_file")
    assert wf_name
    wf_path = root / "configs" / "media" / "comfyui" / wf_name
    wf = json.loads(wf_path.read_text(encoding="utf-8"))
    wf_raw = json.dumps(wf)
    assert "<OPERATOR_SDXL" in wf_raw


def test_workflow_example_contains_only_placeholders_no_absolute_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    wf_path = root / "configs" / "media" / "comfyui" / "sdxl_baseline.workflow.example.json"
    raw = wf_path.read_text(encoding="utf-8")
    assert "gs://" not in raw
    assert ":\\" not in raw
    assert "/home/" not in raw
    assert "C:/" not in raw


def test_load_manifest_and_workflow_smoke() -> None:
    m, g = load_comfy_manifest_and_workflow("sdxl_baseline")
    assert m["workflow_id"] == "sdxl_baseline"
    assert isinstance(g, dict)
    assert "3" in g


def test_comfyui_generation_ready_requires_flag_and_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_MEDIA_IMAGE_GENERATION_ENABLED", "true")
    monkeypatch.delenv("HAM_COMFYUI_BASE_URL", raising=False)
    assert comfyui_image_generation_ready() is False
    monkeypatch.setenv("HAM_COMFYUI_BASE_URL", "http://127.0.0.1:8188")
    assert comfyui_image_generation_ready() is True


def test_comfyui_generation_mock_prompt_history_view(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_MEDIA_IMAGE_PROMPT_MAX_CHARS", "4000")

    png = _tiny_png_bytes()

    def make_client(*_a: object, **_k: object):
        fake = MagicMock()
        fake.post.return_value = httpx.Response(
            200,
            json={"prompt_id": "pid-abc", "number": 0, "node_errors": {}},
        )
        hist = {
            "pid-abc": {
                "outputs": {
                    "9": {"images": [{"filename": "out.png", "type": "output", "subfolder": ""}]}
                }
            }
        }
        fake.get.side_effect = [
            httpx.Response(200, json=hist),
            httpx.Response(200, content=png, headers={"content-type": "image/png"}),
        ]
        fake.__enter__ = lambda self_: fake
        fake.__exit__ = lambda *_: False
        return fake

    with patch.object(httpx, "Client", side_effect=make_client):
        adap = ComfyUIImageProviderAdapter(
            base_url="http://dummy-comfy.invalid",
            workflow_key="sdxl_baseline",
            timeout_sec=30.0,
            poll_sec=0.01,
        )
        r = adap.generate_image(prompt="a lighthouse at dusk", model_id=None, reference_image=None)
    assert r.mime == "image/png"
    assert r.data == png


def test_comfyui_rejects_reference_image() -> None:
    adap = ComfyUIImageProviderAdapter(base_url="http://x.invalid", workflow_key="sdxl_baseline")
    with pytest.raises(ImageGenerationError) as ei:
        adap.generate_image(
            prompt="x",
            model_id=None,
            reference_image=(b"x", "image/png"),
        )
    assert ei.value.code == "IMAGE_TO_IMAGE_NOT_SUPPORTED"


def test_comfyui_node_errors_yield_safe() -> None:
    adap = ComfyUIImageProviderAdapter(base_url="http://dummy.invalid", workflow_key="sdxl_baseline")

    err_body = {"error": {}, "prompt_id": None, "node_errors": {"4": {"class_type": "CheckpointLoader"}}}

    def make_client(**_kw: object):
        fake = MagicMock()
        fake.post.return_value = httpx.Response(200, json=err_body)
        fake.__enter__ = lambda self_: fake
        fake.__exit__ = lambda *_: False
        return fake

    with patch.object(httpx, "Client", side_effect=make_client):
        with pytest.raises(ImageGenerationError) as ei:
            adap.generate_image(prompt="ocean", model_id=None, reference_image=None)
        assert ei.value.code == "IMAGE_GEN_UPSTREAM_REJECTED"


def test_comfyui_output_too_large(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_MEDIA_IMAGE_PROMPT_MAX_CHARS", "4000")
    png = _tiny_png_bytes()
    monkeypatch.setattr(
        "src.ham.comfyui_provider_adapter.comfyui_output_max_bytes",
        lambda: len(png),
    )

    def make_client(**_kw: object):
        fake = MagicMock()
        fake.post.return_value = httpx.Response(
            200,
            json={"prompt_id": "pid-big", "number": 0, "node_errors": None},
        )
        hist = {
            "pid-big": {
                "outputs": {
                    "9": {"images": [{"filename": "big.png", "type": "output", "subfolder": ""}]}
                }
            }
        }
        fake.get.side_effect = [
            httpx.Response(200, json=hist),
            httpx.Response(200, content=png + b"p", headers={"content-type": "image/png"}),
        ]
        fake.__enter__ = lambda self_: fake
        fake.__exit__ = lambda *_: False
        return fake

    with patch.object(httpx, "Client", side_effect=make_client):
        adap = ComfyUIImageProviderAdapter(
            base_url="http://dummy-comfy.invalid",
            workflow_key="sdxl_baseline",
            poll_sec=0.01,
        )
        with pytest.raises(ImageGenerationError) as ei:
            adap.generate_image(prompt="sky", model_id=None, reference_image=None)
        assert ei.value.code == "IMAGE_GEN_OUTPUT_TOO_LARGE"


def test_comfyui_httpx_timeout_on_post(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_MEDIA_IMAGE_PROMPT_MAX_CHARS", "4000")

    def make_client(**_kw: object):
        fake = MagicMock()
        fake.post.side_effect = httpx.TimeoutException("timeout")
        fake.__enter__ = lambda self_: fake
        fake.__exit__ = lambda *_: False
        return fake

    with patch.object(httpx, "Client", side_effect=make_client):
        adap = ComfyUIImageProviderAdapter(
            base_url="http://dummy-comfy.invalid",
            workflow_key="sdxl_baseline",
            poll_sec=0.01,
            timeout_sec=10.0,
        )
        with pytest.raises(ImageGenerationError) as ei:
            adap.generate_image(prompt="cliff", model_id=None, reference_image=None)
        assert ei.value.code == "IMAGE_GEN_UPSTREAM_TIMEOUT"


def test_comfyui_patch_applies_dimensions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_COMFYUI_DEFAULT_WIDTH", "512")
    monkeypatch.setenv("HAM_COMFYUI_DEFAULT_HEIGHT", "768")
    assert comfyui_defaults_width_height() == (512, 768)


def test_load_manifest_sdxl_vanilla_aliases_to_baseline() -> None:
    from src.ham.comfyui_provider_adapter import comfyui_normalize_workflow_key, load_comfy_manifest_and_workflow

    assert comfyui_normalize_workflow_key("sdxl_vanilla") == "sdxl_baseline"
    m1, _g1 = load_comfy_manifest_and_workflow("sdxl_vanilla")
    m2, _g2 = load_comfy_manifest_and_workflow("sdxl_baseline")
    assert m1["workflow_id"] == m2["workflow_id"] == "sdxl_baseline"
