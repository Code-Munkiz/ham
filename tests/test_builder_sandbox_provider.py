from __future__ import annotations

from src.ham.builder_sandbox_provider import load_gcp_gke_runtime_config


def test_load_gcp_gke_runtime_config_uses_higher_default_start_timeout(monkeypatch) -> None:
    monkeypatch.delenv("HAM_BUILDER_GCP_RUNTIME_START_TIMEOUT_SECONDS", raising=False)
    cfg = load_gcp_gke_runtime_config()
    assert cfg.start_timeout_seconds == 300


def test_load_gcp_gke_runtime_config_start_timeout_override(monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_GCP_RUNTIME_START_TIMEOUT_SECONDS", "420")
    cfg = load_gcp_gke_runtime_config()
    assert cfg.start_timeout_seconds == 420
