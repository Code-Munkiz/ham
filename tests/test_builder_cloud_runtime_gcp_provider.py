from __future__ import annotations

from src.ham.builder_cloud_runtime_gcp import (
    CloudRuntimePlan,
    FakeGcpCloudRuntimeClient,
    get_runtime_job_status,
    load_gcp_runtime_config,
    normalize_lifecycle_status,
    redact_runtime_logs,
    redact_provider_metadata,
    request_runtime,
    set_gcp_cloud_runtime_client_for_tests,
    validate_config,
)
from src.persistence.builder_runtime_job_store import CloudRuntimeJob


def _job() -> CloudRuntimeJob:
    return CloudRuntimeJob(
        workspace_id="ws_aaaaaaaaaaaaaaaa",
        project_id="proj_aaaaaaaaaaaaaaaa",
        source_snapshot_id="ssnp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        provider="cloud_run_poc",
        metadata={
            "source_handoff": {
                "handoff_status": "planned",
                "artifact_uri": "builder-artifact://bzip_test",
                "source_ref": "ssnp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:aaaaaaaaaaaaaaaa",
            }
        },
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
    assert cfg.timeout_seconds >= 30
    assert cfg.max_seconds >= cfg.timeout_seconds


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
    class _BoomClient:
        def submit_cloud_run_job(self, **kwargs):  # type: ignore[no-untyped-def]
            _ = kwargs
            raise AssertionError("dry-run should not call provider client")

    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_PROJECT", "my-internal-project")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_REGION", "us-central1")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_DRY_RUN", "true")
    set_gcp_cloud_runtime_client_for_tests(_BoomClient())
    try:
        result = request_runtime(_job())
        assert result.status == "planned"
        assert result.error_code is None
        assert result.plan.status == "planned"
        assert result.plan.runtime_kind == "cloud_run_job"
        payload = result.plan.model_dump(mode="json")
        payload_text = str(payload).lower()
        assert "my-internal-project" not in payload_text
        assert "us-central1" not in payload_text
    finally:
        set_gcp_cloud_runtime_client_for_tests(None)


def test_request_runtime_real_path_accepted_with_fake_client(monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_PROJECT", "my-internal-project")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_REGION", "us-central1")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_DRY_RUN", "false")
    set_gcp_cloud_runtime_client_for_tests(FakeGcpCloudRuntimeClient())
    try:
        result = request_runtime(_job())
        assert result.status == "accepted"
        assert result.error_code is None
        assert result.provider_job_id
        assert result.plan.status == "planned"
    finally:
        set_gcp_cloud_runtime_client_for_tests(None)


def test_request_runtime_real_path_failure_is_safely_mapped(monkeypatch) -> None:
    class _FailingClient:
        def submit_cloud_run_job(self, **kwargs):  # type: ignore[no-untyped-def]
            _ = kwargs
            raise RuntimeError("intentional provider failure")

    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_PROJECT", "my-internal-project")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_REGION", "us-central1")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_DRY_RUN", "false")
    set_gcp_cloud_runtime_client_for_tests(_FailingClient())
    try:
        result = request_runtime(_job())
        assert result.status == "unsupported"
        assert result.error_code == "CLOUD_RUNTIME_PROVIDER_SUBMIT_FAILED"
    finally:
        set_gcp_cloud_runtime_client_for_tests(None)


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


def test_get_runtime_job_status_dry_run_returns_planned_without_logs(monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_PROJECT", "proj-safe")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_REGION", "us-central1")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_DRY_RUN", "true")
    payload = get_runtime_job_status(provider_job_id="fake-crj-123")
    assert payload["provider_state"] == "planned"
    assert payload["logs_summary"] is None


def test_get_runtime_job_status_reads_fake_client_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_PROJECT", "proj-safe")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_REGION", "us-central1")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_DRY_RUN", "false")
    set_gcp_cloud_runtime_client_for_tests(FakeGcpCloudRuntimeClient())
    try:
        payload = get_runtime_job_status(provider_job_id="fake-crj-123")
        assert payload["provider_state"] in {"running", "provisioning"}
        assert payload["error_code"] is None
    finally:
        set_gcp_cloud_runtime_client_for_tests(None)


def test_redact_runtime_logs_masks_sensitive_tokens() -> None:
    assert redact_runtime_logs("token=abc123") == "log output redacted due to sensitive content"
    assert redact_runtime_logs("safe log line") == "safe log line"


def test_normalize_lifecycle_status_maps_provider_states() -> None:
    assert normalize_lifecycle_status("accepted") == "provider_accepted"
    assert normalize_lifecycle_status("running") == "running"
    assert normalize_lifecycle_status("ready") == "ready"


def test_request_runtime_rejects_missing_source_handoff_artifact(monkeypatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_ENABLED", "true")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_PROJECT", "my-internal-project")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_GCP_REGION", "us-central1")
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_DRY_RUN", "false")
    set_gcp_cloud_runtime_client_for_tests(FakeGcpCloudRuntimeClient())
    bad = _job()
    bad.metadata = {"source_handoff": {"handoff_status": "failed", "artifact_uri": ""}}
    try:
        result = request_runtime(bad)
        assert result.status == "unsupported"
        assert result.error_code == "CLOUD_RUNTIME_SOURCE_HANDOFF_FAILED"
    finally:
        set_gcp_cloud_runtime_client_for_tests(None)
