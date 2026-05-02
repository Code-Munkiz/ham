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


def test_comfyui_checkpoint_env_override_updates_post_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """HAM_COMFYUI_CHECKPOINT_NAME must replace CheckpointLoaderSimple.ckpt_name (real workers)."""
    monkeypatch.setenv("HAM_MEDIA_IMAGE_PROMPT_MAX_CHARS", "4000")
    monkeypatch.setenv("HAM_COMFYUI_CHECKPOINT_NAME", "sd_xl_base_1.0.safetensors")
    png = _tiny_png_bytes()
    captured: dict[str, object] = {}

    def make_client(**_kw: object):
        fake = MagicMock()

        def _post(_url: str, **kw: object):
            captured["prompt_json"] = kw.get("json")
            return httpx.Response(200, json={"prompt_id": "pid-x", "number": 0, "node_errors": {}})

        fake.post.side_effect = _post
        hist = {
            "pid-x": {
                "outputs": {"9": {"images": [{"filename": "out.png", "type": "output", "subfolder": ""}]}}
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
        adap.generate_image(prompt="a lighthouse at dusk", model_id=None, reference_image=None)
    pj = captured.get("prompt_json") or {}
    graph = pj.get("prompt") or {}
    loader = graph.get("4") or {}
    assert loader.get("class_type") == "CheckpointLoaderSimple"
    assert (loader.get("inputs") or {}).get("ckpt_name") == "sd_xl_base_1.0.safetensors"


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


def test_comfyui_generate_video_mock_prompt_history_view(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_WORKFLOW", "comfy_video_local_poc")
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_TIMEOUT_SEC", "30")
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_OUTPUT_MAX_BYTES", "2000000")
    mp4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2avc1mp41"

    def make_client(**_kw: object):
        fake = MagicMock()
        fake.post.return_value = httpx.Response(200, json={"prompt_id": "vid-1", "number": 0, "node_errors": {}})
        hist = {
            "vid-1": {
                "outputs": {
                    "9": {"videos": [{"filename": "out.mp4", "type": "output", "subfolder": ""}]}
                }
            }
        }
        fake.get.side_effect = [
            httpx.Response(200, json=hist),
            httpx.Response(200, content=mp4, headers={"content-type": "video/mp4"}),
        ]
        fake.__enter__ = lambda self_: fake
        fake.__exit__ = lambda *_: False
        return fake

    with patch.object(httpx, "Client", side_effect=make_client):
        adap = ComfyUIImageProviderAdapter(
            base_url="http://dummy-comfy.invalid",
            workflow_key="sdxl_baseline",
            timeout_sec=5.0,
            poll_sec=0.01,
        )
        v = adap.generate_video(prompt="short clip", model_id=None)
    assert v.mime == "video/mp4"
    assert v.data == mp4


def test_comfyui_generate_video_from_gifs_array(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_WORKFLOW", "comfy_video_local_poc")
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_TIMEOUT_SEC", "30")
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_OUTPUT_MAX_BYTES", "2000000")
    gif = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x00\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"

    def make_client(**_kw: object):
        fake = MagicMock()
        fake.post.return_value = httpx.Response(200, json={"prompt_id": "vid-gif", "number": 0, "node_errors": {}})
        hist = {
            "vid-gif": {
                "outputs": {
                    "9": {"gifs": [{"filename": "out.gif", "type": "output", "subfolder": ""}]}
                }
            }
        }
        fake.get.side_effect = [
            httpx.Response(200, json=hist),
            httpx.Response(200, content=gif, headers={"content-type": "image/gif"}),
        ]
        fake.__enter__ = lambda self_: fake
        fake.__exit__ = lambda *_: False
        return fake

    with patch.object(httpx, "Client", side_effect=make_client):
        adap = ComfyUIImageProviderAdapter(
            base_url="http://dummy-comfy.invalid",
            workflow_key="sdxl_baseline",
            timeout_sec=5.0,
            poll_sec=0.01,
        )
        v = adap.generate_video(prompt="short gif clip", model_id=None)
    assert v.mime == "image/gif"
    assert v.data == gif


def test_comfyui_generate_video_from_images_array_animated_mp4(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_WORKFLOW", "comfy_video_local_poc")
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_TIMEOUT_SEC", "30")
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_OUTPUT_MAX_BYTES", "2000000")
    mp4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2avc1mp41"

    def make_client(**_kw: object):
        fake = MagicMock()
        fake.post.return_value = httpx.Response(200, json={"prompt_id": "vid-img-a", "number": 0, "node_errors": {}})
        hist = {
            "vid-img-a": {
                "outputs": {
                    "11": {
                        "images": [{"filename": "clip.mp4", "type": "output", "subfolder": ""}],
                        "animated": [True],
                    }
                }
            }
        }
        fake.get.side_effect = [
            httpx.Response(200, json=hist),
            httpx.Response(200, content=mp4, headers={"content-type": "video/mp4"}),
        ]
        fake.__enter__ = lambda self_: fake
        fake.__exit__ = lambda *_: False
        return fake

    with patch.object(httpx, "Client", side_effect=make_client):
        adap = ComfyUIImageProviderAdapter(
            base_url="http://dummy-comfy.invalid",
            workflow_key="sdxl_baseline",
            timeout_sec=5.0,
            poll_sec=0.01,
        )
        v = adap.generate_video(prompt="short mp4 clip", model_id=None)
    assert v.mime == "video/mp4"
    assert v.data == mp4


def test_comfyui_generate_video_from_images_array_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_WORKFLOW", "comfy_video_local_poc")
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_TIMEOUT_SEC", "30")
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_OUTPUT_MAX_BYTES", "2000000")
    webm = b"\x1a\x45\xdf\xa3\x93B\x82\x88webm"

    def make_client(**_kw: object):
        fake = MagicMock()
        fake.post.return_value = httpx.Response(200, json={"prompt_id": "vid-img-b", "number": 0, "node_errors": {}})
        hist = {
            "vid-img-b": {
                "outputs": {
                    "11": {
                        "images": [{"filename": "clip.webm", "type": "output", "subfolder": ""}],
                    }
                }
            }
        }
        fake.get.side_effect = [
            httpx.Response(200, json=hist),
            httpx.Response(200, content=webm, headers={"content-type": "application/octet-stream"}),
        ]
        fake.__enter__ = lambda self_: fake
        fake.__exit__ = lambda *_: False
        return fake

    with patch.object(httpx, "Client", side_effect=make_client):
        adap = ComfyUIImageProviderAdapter(
            base_url="http://dummy-comfy.invalid",
            workflow_key="sdxl_baseline",
            timeout_sec=5.0,
            poll_sec=0.01,
        )
        v = adap.generate_video(prompt="short webm clip", model_id=None)
    assert v.mime == "video/webm"
    assert v.data == webm


def test_comfyui_generate_video_images_array_png_is_not_video(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_WORKFLOW", "comfy_video_local_poc")
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_TIMEOUT_SEC", "1")
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_OUTPUT_MAX_BYTES", "2000000")
    png = _tiny_png_bytes()

    def make_client(**_kw: object):
        fake = MagicMock()
        fake.post.return_value = httpx.Response(200, json={"prompt_id": "vid-img-png", "number": 0, "node_errors": {}})
        hist = {
            "vid-img-png": {
                "outputs": {
                    "11": {
                        "images": [{"filename": "frame.png", "type": "output", "subfolder": ""}],
                    }
                }
            }
        }

        def _get(url: str, **_kwargs: object) -> httpx.Response:
            if "/history/" in url:
                return httpx.Response(200, json=hist)
            return httpx.Response(200, content=png, headers={"content-type": "image/png"})

        fake.get.side_effect = _get
        fake.__enter__ = lambda self_: fake
        fake.__exit__ = lambda *_: False
        return fake

    with patch.object(httpx, "Client", side_effect=make_client):
        adap = ComfyUIImageProviderAdapter(
            base_url="http://dummy-comfy.invalid",
            workflow_key="sdxl_baseline",
            timeout_sec=5.0,
            poll_sec=0.01,
        )
        with pytest.raises(ImageGenerationError) as ei:
            adap.generate_video(prompt="png should not pass", model_id=None)
    assert ei.value.code == "VIDEO_GEN_UPSTREAM_TIMEOUT"


def test_comfyui_generate_video_rejects_non_video_mime_and_no_leak(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_WORKFLOW", "comfy_video_local_poc")
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_TIMEOUT_SEC", "30")
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_OUTPUT_MAX_BYTES", "2000000")
    png = _tiny_png_bytes()

    def make_client(**_kw: object):
        fake = MagicMock()
        fake.post.return_value = httpx.Response(200, json={"prompt_id": "vid-mime", "number": 0, "node_errors": {}})
        hist = {
            "vid-mime": {
                "outputs": {
                    "11": {
                        "images": [{"filename": "clip.mp4", "type": "output", "subfolder": ""}],
                    }
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
            timeout_sec=5.0,
            poll_sec=0.01,
        )
        with pytest.raises(ImageGenerationError) as ei:
            adap.generate_video(prompt="bad mime", model_id=None)
    assert ei.value.code == "VIDEO_GEN_NO_VIDEO"
    msg = str(ei.value)
    assert "dummy-comfy.invalid" not in msg
    assert "/view" not in msg


def test_animatediff_manifest_and_example_shapes() -> None:
    root = Path(__file__).resolve().parents[1]
    man_path = root / "configs" / "media" / "comfyui" / "animatediff_sdxl_gen1_mp4.manifest.json"
    data = json.loads(man_path.read_text(encoding="utf-8"))
    assert data.get("workflow_id") == "animatediff_sdxl_gen1_mp4"
    assert data.get("fallback_workflow") == "comfy_video_local_poc"
    patches = data.get("comfy_patches") or {}
    assert patches.get("prompt") == {"node": "2", "input": "text"}
    assert patches.get("negative_prompt") == {"node": "3", "input": "text"}
    assert patches.get("seed") == {"node": "6", "input": "seed"}
    raw_m = json.dumps(data)
    assert "gs://" not in raw_m
    assert "C:\\" not in raw_m

    wf_name = data.get("workflow_file")
    assert wf_name
    wf_path = root / "configs" / "media" / "comfyui" / wf_name
    wf = json.loads(wf_path.read_text(encoding="utf-8"))
    wf_raw = json.dumps(wf)
    assert "gs://" not in wf_raw
    assert ":\\" not in wf_raw and "C:/" not in wf_raw and "/home/" not in wf_raw
    five = wf.get("5") or {}
    assert five.get("class_type") == "ADE_AnimateDiffLoaderGen1"
    assert five.get("inputs", {}).get("model_name") == "mm_sdxl_v10_beta.ckpt"


def test_comfy_generate_video_animatediff_patches_and_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_WORKFLOW", "animatediff_sdxl_gen1_mp4")
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_TIMEOUT_SEC", "30")
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_OUTPUT_MAX_BYTES", "2000000")
    monkeypatch.setenv("HAM_MEDIA_IMAGE_PROMPT_MAX_CHARS", "4000")
    monkeypatch.setenv("HAM_COMFYUI_CHECKPOINT_NAME", "sd_xl_base_1.0.safetensors")
    monkeypatch.setenv("HAM_COMFYUI_DEFAULT_NEGATIVE_PROMPT", "neg-from-env")
    monkeypatch.setenv("HAM_COMFYUI_ANIMATEDIFF_MODEL_NAME", "mm_override.ckpt")
    monkeypatch.setenv("HAM_COMFYUI_ANIMATEDIFF_BETA_SCHEDULE", "custom-beta")

    mp4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2avc1mp41"
    captured: dict[str, object] = {}

    def make_client(**_kw: object):
        fake = MagicMock()

        def _post(_url: str, **kw: object):
            captured["prompt_json"] = kw.get("json")
            return httpx.Response(200, json={"prompt_id": "vid-ad", "number": 0, "node_errors": {}})

        fake.post.side_effect = _post
        hist = {
            "vid-ad": {
                "outputs": {
                    "9": {
                        "images": [{"filename": "clip.mp4", "type": "output", "subfolder": ""}],
                        "animated": [True],
                    }
                }
            }
        }
        fake.get.side_effect = [
            httpx.Response(200, json=hist),
            httpx.Response(200, content=mp4, headers={"content-type": "video/mp4"}),
        ]
        fake.__enter__ = lambda self_: fake
        fake.__exit__ = lambda *_: False
        return fake

    with patch.object(httpx, "Client", side_effect=make_client):
        adap = ComfyUIImageProviderAdapter(
            base_url="http://dummy-comfy.invalid",
            workflow_key="sdxl_baseline",
            timeout_sec=5.0,
            poll_sec=0.01,
        )
        v = adap.generate_video(prompt="robot monkey typing", model_id=None)

    pj = captured.get("prompt_json") or {}
    graph = pj.get("prompt") or {}
    assert v.mime == "video/mp4"

    assert (graph.get("2") or {}).get("inputs", {}).get("text") == "robot monkey typing"
    assert (graph.get("3") or {}).get("inputs", {}).get("text") == "neg-from-env"
    seed_val = (graph.get("6") or {}).get("inputs", {}).get("seed")
    assert isinstance(seed_val, int)

    ck = (graph.get("1") or {}).get("inputs", {}).get("ckpt_name")
    assert ck == "sd_xl_base_1.0.safetensors"

    ld = graph.get("5") or {}
    assert ld.get("class_type") == "ADE_AnimateDiffLoaderGen1"
    assert ld.get("inputs", {}).get("model_name") == "mm_override.ckpt"
    assert ld.get("inputs", {}).get("beta_schedule") == "custom-beta"


def test_comfy_generate_video_poc_ignores_negative_patch_when_manifest_omits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_WORKFLOW", "comfy_video_local_poc")
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_TIMEOUT_SEC", "30")
    monkeypatch.setenv("HAM_COMFYUI_VIDEO_OUTPUT_MAX_BYTES", "2000000")
    monkeypatch.setenv("HAM_MEDIA_IMAGE_PROMPT_MAX_CHARS", "4000")
    monkeypatch.setenv("HAM_COMFYUI_DEFAULT_NEGATIVE_PROMPT", "THIS_SHOULD_NOT_APPEAR_IN_POC")
    captured: dict[str, object] = {}

    mp4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2avc1mp41"

    def make_client(**_kw: object):
        fake = MagicMock()

        def _post(_url: str, **kw: object):
            captured["prompt_json"] = kw.get("json")
            return httpx.Response(200, json={"prompt_id": "vid-p", "number": 0, "node_errors": {}})

        fake.post.side_effect = _post
        hist = {
            "vid-p": {"outputs": {"9": {"videos": [{"filename": "out.mp4", "type": "output", "subfolder": ""}]}}}
        }
        fake.get.side_effect = [
            httpx.Response(200, json=hist),
            httpx.Response(200, content=mp4, headers={"content-type": "video/mp4"}),
        ]
        fake.__enter__ = lambda self_: fake
        fake.__exit__ = lambda *_: False
        return fake

    with patch.object(httpx, "Client", side_effect=make_client):
        adap = ComfyUIImageProviderAdapter(base_url="http://dummy.invalid", workflow_key="sdxl_baseline", poll_sec=0.01)
        adap.generate_video(prompt="x", model_id=None)

    graph = (captured.get("prompt_json") or {}).get("prompt") or {}
    assert (graph.get("7") or {}).get("inputs", {}).get("text") != "THIS_SHOULD_NOT_APPEAR_IN_POC"
