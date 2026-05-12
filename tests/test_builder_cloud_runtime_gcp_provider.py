from __future__ import annotations

from src.ham.builder_cloud_runtime_gcp import (
    CloudRuntimePlan,
    load_gcp_runtime_config,
    redact_provider_metadata,
    request_runtime,
    validate_config,
)
from src.persistence.builder_runtime_job_store import CloudRuntimeJob


def _job() -> CloudRuntimeJob:
    return CloudRuntimeJob(
        workspace_id="ws_aaaaaaaaaaaaaaaa",
        project_id="proj_aaaaaaaaaaaaaaaa",
        source_snapshot_id="ssnp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        provider="cloud_run_poc",
    )


def test_config_defaults_are_safe(monkeypatch) -> None:
    monkeypatch.delenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_ENABLED", raising=False)
    monkeypatch.delenv("HAM_BUILDER_CLOUD_RUNTIME_DRY_RUN", raising=False)
    monkeypatch.delenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_PROJECT", raising=False)
    monkeypatch.delenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_REGION", raising=False)
    cfg = load_gcp_runtime_config()
    assert cfg.enabled is False
    assert cfg.dry_run is True
    assert cfg.gcp_project_present is False
    assert cfg.gcp_region_present is False


def test_validate_config_reports_missing_project_and_region(monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_ENABLED", "true")
    monkeypatch.delenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_PROJECT", raising=False)
    monkeypatch.delenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_REGION", raising=False)
    cfg = load_gcp_runtime_config()
    status, error_code, warnings = validate_config(cfg)
    assert status == "invalid_config"
    assert error_code == "CLOUD_RUNTIME_CONFIG_MISSING"
    assert len(warnings) >= 1


def test_request_runtime_dry_run_plans_without_leaking_config(monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_PROJECT", "my-internal-project")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_REGION", "us-central1")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_DRY_RUN", "true")
    result = request_runtime(_job())
    assert result.status == "planned"
    assert result.error_code is None
    assert result.plan.status == "planned"
    assert result.plan.runtime_kind == "cloud_run_job"
    payload = result.plan.model_dump(mode="json")
    payload_text = str(payload).lower()
    assert "my-internal-project" not in payload_text
    assert "us-central1" not in payload_text


def test_redact_provider_metadata_drops_sensitive_keys_and_values() -> None:
    safe = redact_provider_metadata(
        {
            "api_key": "should-drop",
            "plain": "safe",
            "nested_secret": "token=hidden",
        }
    )
    assert "api_key" not in safe
    assert safe["plain"] == "safe"
    assert "nested_secret" not in safe


def test_plan_model_is_strict() -> None:
    plan = CloudRuntimePlan(
        provider="cloud_run_poc",
        project_id="proj_123",
        workspace_id="ws_123",
        status="planned",
        runtime_kind="cloud_run_job",
    )
    assert plan.preview_strategy == "none"
