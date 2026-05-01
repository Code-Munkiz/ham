"""Media provider registry (Phase 2G.5) — selection and capability metadata."""

from __future__ import annotations

import json

import pytest

from src.ham.media_provider_adapter import (
    OpenRouterImageProviderAdapter,
    SyntheticTestOnlyImageAdapter,
    UnconfiguredImageProviderAdapter,
    rebuild_image_generation_adapter_singleton,
)
from src.ham.media_provider_registry import (
    active_media_provider_id,
    build_selected_image_generation_adapter,
    normalized_ham_media_provider_env,
    provider_notes_for_capabilities,
)
from src.ham.model_capabilities import build_chat_capabilities_payload


def test_default_env_resolves_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_MEDIA_PROVIDER", raising=False)
    assert normalized_ham_media_provider_env() == "openrouter"


def test_openrouter_adapter_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_MEDIA_PROVIDER", "openrouter")
    monkeypatch.setenv("HAM_MEDIA_IMAGE_GENERATION_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-fake-long-key-for-plausible-xxxx")
    rebuild_image_generation_adapter_singleton()
    a = build_selected_image_generation_adapter()
    assert isinstance(a, OpenRouterImageProviderAdapter)


def test_comfy_returns_unconfigured_without_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_MEDIA_PROVIDER", "comfyui")
    monkeypatch.setenv("HAM_MEDIA_IMAGE_GENERATION_ENABLED", "true")
    monkeypatch.delenv("HAM_COMFYUI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-fake-long-key-for-plausible-xxxx")
    rebuild_image_generation_adapter_singleton()
    assert isinstance(build_selected_image_generation_adapter(), UnconfiguredImageProviderAdapter)


def test_comfy_selects_adapter_when_base_url_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.ham.comfyui_provider_adapter import ComfyUIImageProviderAdapter

    monkeypatch.setenv("HAM_MEDIA_PROVIDER", "comfyui")
    monkeypatch.setenv("HAM_MEDIA_IMAGE_GENERATION_ENABLED", "true")
    monkeypatch.setenv("HAM_COMFYUI_BASE_URL", "http://127.0.0.1:8188")
    rebuild_image_generation_adapter_singleton()
    assert isinstance(build_selected_image_generation_adapter(), ComfyUIImageProviderAdapter)


def test_unconfigured_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_MEDIA_PROVIDER", "unconfigured")
    assert active_media_provider_id() == "unconfigured"
    assert isinstance(build_selected_image_generation_adapter(), UnconfiguredImageProviderAdapter)


def test_synthetic_only_when_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_MEDIA_PROVIDER", "test_synthetic")
    monkeypatch.delenv("HAM_MEDIA_ALLOW_SYNTHETIC_ADAPTER", raising=False)
    assert isinstance(build_selected_image_generation_adapter(), UnconfiguredImageProviderAdapter)
    monkeypatch.setenv("HAM_MEDIA_ALLOW_SYNTHETIC_ADAPTER", "true")
    assert isinstance(build_selected_image_generation_adapter(), SyntheticTestOnlyImageAdapter)


def test_capabilities_comfyui_disables_generation_without_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_MEDIA_PROVIDER", "comfyui")
    monkeypatch.setenv("HAM_MEDIA_IMAGE_GENERATION_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-fake-long-key-for-plausible-xxxx")
    monkeypatch.delenv("HAM_COMFYUI_BASE_URL", raising=False)
    p = build_chat_capabilities_payload(model_id="x/y", gateway_mode="openrouter")
    gen = p["generation"]
    assert gen["active_media_provider"] == "comfyui"
    assert gen["supports_image_generation"] is False
    assert gen["supports_text_to_image"] is False
    assert gen["media_generation_provider"] is None
    raw = json.dumps(gen)
    assert "http://" not in raw
    assert "https://" not in raw
    assert "gs://" not in raw


def test_capabilities_comfyui_enables_generation_with_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_MEDIA_PROVIDER", "comfyui")
    monkeypatch.setenv("HAM_MEDIA_IMAGE_GENERATION_ENABLED", "true")
    monkeypatch.setenv("HAM_COMFYUI_BASE_URL", "http://127.0.0.1:8188")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    p = build_chat_capabilities_payload(model_id="x/y", gateway_mode="openrouter")
    gen = p["generation"]
    assert gen["active_media_provider"] == "comfyui"
    assert gen["supports_image_generation"] is True
    assert gen["supports_text_to_image"] is True
    assert gen["media_generation_provider"] == "comfyui"
    assert gen["supports_image_to_image"] is False
    raw = json.dumps(p)
    assert "127.0.0.1" not in raw
    assert "8188" not in raw


def test_capabilities_payload_no_internal_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_COMFYUI_BASE_URL", "http://192.168.77.88:8188/")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-fake-key")
    p = build_chat_capabilities_payload(model_id="x/y", gateway_mode="openrouter")
    raw = json.dumps(p)
    assert "192.168" not in raw
    assert ":8188" not in raw
    assert "gs://" not in raw


def test_provider_notes_unknown_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_MEDIA_PROVIDER", "totally-unknown-backend")
    n = provider_notes_for_capabilities()
    assert any("Unrecognized HAM_MEDIA_PROVIDER" in line for line in n)
