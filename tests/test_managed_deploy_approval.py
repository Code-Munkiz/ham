"""Managed deploy hook approval: policy (default off) + hard enforcement."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api import cursor_managed_deploy_approval as cda
from src.api import cursor_managed_deploy as cdd
from src.api.server import app
from src.ham.managed_deploy_approval_policy import (
    deploy_hook_allowed_in_policy_mode,
    managed_deploy_approval_mode,
)
from src.persistence.managed_deploy_approval import (
    ManagedDeployApproval,
    ManagedDeployApprovalStore,
    new_approval_id,
)
from src.persistence.control_plane_run import utc_now_iso


def test_policy_defaults_off() -> None:
    assert managed_deploy_approval_mode() == "off"


def test_hard_requires_approved_latest() -> None:
    assert not deploy_hook_allowed_in_policy_mode("hard", None)
    now = utc_now_iso()
    mid = new_approval_id()
    denied = ManagedDeployApproval(
        approval_id=mid,
        mission_registry_id=None,
        cursor_agent_id="a1",
        state="denied",
        decision_at=now,
        actor=None,
        source="operator_ui",
    )
    assert not deploy_hook_allowed_in_policy_mode("hard", denied)
    ap = new_approval_id()
    approved = ManagedDeployApproval(
        approval_id=ap,
        mission_registry_id=None,
        cursor_agent_id="a1",
        state="approved",
        decision_at=now,
        actor=None,
        source="operator_ui",
    )
    assert deploy_hook_allowed_in_policy_mode("hard", approved)


def _patch_stores(st: ManagedDeployApprovalStore) -> None:
    cdd._approval_store = st
    cda._store = st


def test_get_deploy_approval_includes_off_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    st = ManagedDeployApprovalStore(base_dir=tmp_path / "ap2")
    _patch_stores(st)
    monkeypatch.delenv("HAM_MANAGED_DEPLOY_APPROVAL_MODE", raising=False)
    c = TestClient(app)
    r = c.get("/api/cursor/managed/deploy-approval", params={"agent_id": "curs-agent-x"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["policy"] == "off"
    assert j["latest_approval"] is None
    assert j["deploy_hook_would_allow"] is True


def test_post_record_then_get(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    st = ManagedDeployApprovalStore(base_dir=tmp_path / "ap3")
    _patch_stores(st)
    monkeypatch.delenv("HAM_MANAGED_DEPLOY_APPROVAL_MODE", raising=False)
    c = TestClient(app)
    r = c.post(
        "/api/cursor/managed/deploy-approval",
        json={"agent_id": "z9", "state": "approved", "note": "ok", "source": "api"},
    )
    assert r.status_code == 200, r.text
    g = c.get("/api/cursor/managed/deploy-approval", params={"agent_id": "z9"})
    assert g.json()["latest_approval"]["state"] == "approved"


def test_hard_mode_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    st = ManagedDeployApprovalStore(base_dir=tmp_path / "ap4")
    _patch_stores(st)
    monkeypatch.setenv("HAM_MANAGED_DEPLOY_APPROVAL_MODE", "hard")
    assert managed_deploy_approval_mode() == "hard"
