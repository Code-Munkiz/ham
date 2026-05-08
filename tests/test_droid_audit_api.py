"""Read-only Factory Droid audit API — POST /api/droid/preview + /launch."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api import droid_audit as audit_api
from src.api.clerk_gate import get_ham_clerk_actor
from src.api.server import app, fastapi_app
from src.ham.droid_workflows.preview_launch import DroidLaunchResult
from src.ham.droid_workflows.registry import REGISTRY_REVISION


def _register_project(client: TestClient, *, name: str, root: Path) -> str:
    res = client.post(
        "/api/projects",
        json={"name": name, "root": str(root), "description": ""},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


def test_preview_returns_digest_and_friendly_flags(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    pid = _register_project(client, name="p_audit", root=root)
    res = client.post(
        "/api/droid/preview",
        json={"project_id": pid, "user_prompt": "Audit security and architecture."},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "droid_audit_preview"
    assert body["project_id"] == pid
    assert body["is_readonly"] is True
    assert body["mutates"] is False
    assert isinstance(body["proposal_digest"], str) and len(body["proposal_digest"]) == 64
    assert body["base_revision"] == REGISTRY_REVISION
    assert "summary_preview" in body


def test_preview_unknown_project_404(client: TestClient) -> None:
    res = client.post(
        "/api/droid/preview",
        json={"project_id": "project.unknown", "user_prompt": "x"},
    )
    assert res.status_code == 404
    assert res.json()["detail"]["error"]["code"] == "PROJECT_NOT_FOUND"


def test_preview_validates_body(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    pid = _register_project(client, name="p_v1", root=root)
    res = client.post(
        "/api/droid/preview",
        json={"project_id": pid, "user_prompt": ""},
    )
    assert res.status_code == 422


def test_preview_rejects_extra_fields(client: TestClient, tmp_path: Path) -> None:
    """The router never accepts workflow_id from the client (locked to readonly_repo_audit)."""
    root = tmp_path / "r"
    root.mkdir()
    pid = _register_project(client, name="p_v2", root=root)
    res = client.post(
        "/api/droid/preview",
        json={
            "project_id": pid,
            "user_prompt": "x",
            "workflow_id": "safe_edit_low",
        },
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------


def _make_preview(client: TestClient, pid: str, prompt: str) -> dict:
    r = client.post(
        "/api/droid/preview",
        json={"project_id": pid, "user_prompt": prompt},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _ok_record(root: Path) -> DroidLaunchResult:
    return DroidLaunchResult(
        ok=True,
        blocking_reason=None,
        workflow_id="readonly_repo_audit",
        audit_id="aud-1",
        runner_id="local",
        cwd=str(root),
        exit_code=0,
        duration_ms=42,
        summary="audit ok",
        stdout="{}",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        parsed_json={"result": "ok"},
        session_id="s-1",
        timed_out=False,
        ham_run_id="11111111-1111-1111-1111-111111111111",
        control_plane_status="succeeded",
    )


def test_launch_requires_confirmed(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    pid = _register_project(client, name="p_l1", root=root)
    pv = _make_preview(client, pid, "audit risks")
    res = client.post(
        "/api/droid/launch",
        json={
            "project_id": pid,
            "user_prompt": "audit risks",
            "proposal_digest": pv["proposal_digest"],
            "base_revision": pv["base_revision"],
            "confirmed": False,
        },
    )
    assert res.status_code == 422
    assert res.json()["detail"]["error"]["code"] == "DROID_AUDIT_LAUNCH_REQUIRES_CONFIRMATION"


def test_launch_rejects_stale_digest(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    pid = _register_project(client, name="p_l2", root=root)
    pv = _make_preview(client, pid, "audit risks")
    res = client.post(
        "/api/droid/launch",
        json={
            "project_id": pid,
            "user_prompt": "audit risks DIFFERENT",
            "proposal_digest": pv["proposal_digest"],
            "base_revision": pv["base_revision"],
            "confirmed": True,
        },
    )
    assert res.status_code == 409
    assert res.json()["detail"]["error"]["code"] == "DROID_AUDIT_LAUNCH_PREVIEW_STALE"


def test_launch_rejects_stale_base_revision(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    pid = _register_project(client, name="p_l3", root=root)
    pv = _make_preview(client, pid, "audit risks")
    res = client.post(
        "/api/droid/launch",
        json={
            "project_id": pid,
            "user_prompt": "audit risks",
            "proposal_digest": pv["proposal_digest"],
            "base_revision": "old-revision",
            "confirmed": True,
        },
    )
    assert res.status_code == 409


def test_launch_unknown_project_404(client: TestClient) -> None:
    res = client.post(
        "/api/droid/launch",
        json={
            "project_id": "project.nope",
            "user_prompt": "x",
            "proposal_digest": "0" * 64,
            "base_revision": REGISTRY_REVISION,
            "confirmed": True,
        },
    )
    assert res.status_code == 404


@patch("src.api.droid_audit.execute_droid_workflow")
def test_launch_success_returns_friendly_payload(
    mock_exec, client: TestClient, tmp_path: Path
) -> None:
    root = tmp_path / "r"
    root.mkdir()
    pid = _register_project(client, name="p_l4", root=root)
    pv = _make_preview(client, pid, "audit security")
    mock_exec.return_value = _ok_record(root)
    res = client.post(
        "/api/droid/launch",
        json={
            "project_id": pid,
            "user_prompt": "audit security",
            "proposal_digest": pv["proposal_digest"],
            "base_revision": pv["base_revision"],
            "confirmed": True,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "droid_audit_launch"
    assert body["ok"] is True
    assert body["ham_run_id"] == "11111111-1111-1111-1111-111111111111"
    assert body["control_plane_status"] == "succeeded"
    assert body["is_readonly"] is True
    assert body["blocking_reason"] is None


@patch("src.api.droid_audit.execute_droid_workflow")
def test_launch_failure_propagates_blocking_reason(
    mock_exec, client: TestClient, tmp_path: Path
) -> None:
    root = tmp_path / "r"
    root.mkdir()
    pid = _register_project(client, name="p_l5", root=root)
    pv = _make_preview(client, pid, "audit big")
    rec = _ok_record(root)
    mock_exec.return_value = DroidLaunchResult(
        **{
            **rec.__dict__,
            "ok": False,
            "blocking_reason": "droid exec failed (exit 7)",
            "exit_code": 7,
            "control_plane_status": "failed",
        }
    )
    res = client.post(
        "/api/droid/launch",
        json={
            "project_id": pid,
            "user_prompt": "audit big",
            "proposal_digest": pv["proposal_digest"],
            "base_revision": pv["base_revision"],
            "confirmed": True,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is False
    assert body["control_plane_status"] == "failed"
    assert "failed" in (body["blocking_reason"] or "").lower()


# ---------------------------------------------------------------------------
# Clerk gate
# ---------------------------------------------------------------------------


def test_preview_requires_clerk_when_auth_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "1")
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
    fastapi_app.dependency_overrides.pop(get_ham_clerk_actor, None)
    c = TestClient(app)
    res = c.post(
        "/api/droid/preview",
        json={"project_id": "x", "user_prompt": "y"},
    )
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "CLERK_SESSION_REQUIRED"


def test_launch_requires_clerk_when_auth_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "1")
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
    fastapi_app.dependency_overrides.pop(get_ham_clerk_actor, None)
    c = TestClient(app)
    res = c.post(
        "/api/droid/launch",
        json={
            "project_id": "x",
            "user_prompt": "y",
            "proposal_digest": "0" * 64,
            "base_revision": REGISTRY_REVISION,
            "confirmed": True,
        },
    )
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# Scope lock — never expose safe_edit_low through this router
# ---------------------------------------------------------------------------


def test_router_only_targets_readonly_repo_audit() -> None:
    assert audit_api._AUDIT_WORKFLOW_ID == "readonly_repo_audit"
    from src.ham.droid_workflows.registry import get_workflow

    wf = get_workflow(audit_api._AUDIT_WORKFLOW_ID)
    assert wf is not None
    assert wf.mutates is False
    assert wf.requires_launch_token is False
