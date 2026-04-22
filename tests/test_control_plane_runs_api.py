"""API read surface for ControlPlaneRun (list + get)."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api import control_plane_runs as cpr_api
from src.api.server import app
from src.persistence.control_plane_run import (
    ControlPlaneRun,
    ControlPlaneRunStore,
    utc_now_iso,
)


def _register_project(client: TestClient, *, name: str, root: Path) -> str:
    res = client.post(
        "/api/projects",
        json={"name": name, "root": str(root), "description": ""},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _sample_run(*, project_id: str, ham_run_id: str, provider: str) -> ControlPlaneRun:
    now = utc_now_iso()
    return ControlPlaneRun(
        ham_run_id=ham_run_id,
        provider=provider,
        action_kind="launch",
        project_id=project_id,
        created_by=None,
        created_at=now,
        updated_at=now,
        committed_at=now,
        started_at=now,
        finished_at=None,
        last_observed_at=now,
        status="running",
        status_reason="test",
        proposal_digest="a" * 64,
        base_revision="v1",
        external_id="ext-1",
        workflow_id="w1" if provider == "factory_droid" else None,
        summary="summary line",
        error_summary=None,
        last_provider_status="PENDING" if provider == "cursor_cloud_agent" else None,
        audit_ref=None,
    )


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    cpr = tmp_path / "cpr"
    cpr.mkdir()
    st = ControlPlaneRunStore(base_dir=cpr)
    monkeypatch.setattr(cpr_api, "_store", st)
    return TestClient(app)


def test_list_by_project_id(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    pid = _register_project(client, name="p1", root=root)
    rid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    cpr_api._store.save(
        _sample_run(project_id=pid, ham_run_id=rid, provider="cursor_cloud_agent"),
        project_root_for_mirror=None,
    )

    res = client.get("/api/control-plane-runs", params={"project_id": pid})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "control_plane_run_list"
    assert len(body["runs"]) == 1
    row = body["runs"][0]
    assert row["ham_run_id"] == rid
    assert row["provider"] == "cursor_cloud_agent"
    assert "proposal_digest" not in row
    assert "project_root" not in row
    assert "created_by" not in row
    assert "base_revision" not in row


def test_list_provider_filter(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    pid = _register_project(client, name="p2", root=root)
    cpr_api._store.save(
        _sample_run(project_id=pid, ham_run_id="11111111-1111-1111-1111-111111111111", provider="cursor_cloud_agent"),
        project_root_for_mirror=None,
    )
    cpr_api._store.save(
        _sample_run(project_id=pid, ham_run_id="22222222-2222-2222-2222-222222222222", provider="factory_droid"),
        project_root_for_mirror=None,
    )
    res = client.get(
        "/api/control-plane-runs",
        params={"project_id": pid, "provider": "factory_droid", "limit": 10},
    )
    assert res.status_code == 200, res.text
    runs = res.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["provider"] == "factory_droid"


def test_get_by_ham_run_id(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    pid = _register_project(client, name="p3", root=root)
    rid = "33333333-3333-3333-3333-333333333333"
    cpr_api._store.save(
        _sample_run(project_id=pid, ham_run_id=rid, provider="cursor_cloud_agent"),
        project_root_for_mirror=None,
    )
    res = client.get(f"/api/control-plane-runs/{rid}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "control_plane_run"
    run = body["run"]
    assert run["ham_run_id"] == rid
    assert "proposal_digest" not in run


def test_get_missing_run_404(client: TestClient) -> None:
    missing = "44444444-4444-4444-4444-444444444444"
    res = client.get(f"/api/control-plane-runs/{missing}")
    assert res.status_code == 404


def test_list_unknown_project_404(client: TestClient) -> None:
    res = client.get("/api/control-plane-runs", params={"project_id": "project.unknown"})
    assert res.status_code == 404


def test_list_requires_project_id(client: TestClient) -> None:
    res = client.get("/api/control-plane-runs")
    assert res.status_code == 422
