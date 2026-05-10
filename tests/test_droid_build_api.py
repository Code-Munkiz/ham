"""
Gated Factory Droid Build API — POST /api/droid/build/preview + /launch.

These tests lock the safety contract for the mutating Build router:

- ``safe_edit_low`` is hardcoded server-side and is never accepted from the
  client and never echoed in user-facing response fields.
- Every gate (operator, project, build_lane_enabled, github_repo, confirmed,
  accept_pr, digest, ``HAM_DROID_EXEC_TOKEN``) fails closed without ever
  reaching the runner.
- The launch executor is mocked; no real ``droid``, ``git``, ``gh``, or
  network call is made.
- The read-only audit router (``/api/droid/launch``) remains scoped to
  ``readonly_repo_audit`` only — never a mutating workflow.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api import droid_build as build_api
from src.api.clerk_gate import get_ham_clerk_actor
from src.api.server import app, fastapi_app
from src.ham.clerk_auth import HamActor
from src.ham.droid_workflows.registry import REGISTRY_REVISION
from src.persistence.project_store import (
    ProjectStore,
    set_project_store_for_tests,
)
from src.registry.projects import ProjectRecord

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_store(tmp_path: Path) -> ProjectStore:
    """Use a tmp file-backed store so tests never touch ~/.ham/projects.json."""
    store = ProjectStore(store_path=tmp_path / "projects.json")
    set_project_store_for_tests(store)
    yield store
    set_project_store_for_tests(None)


@pytest.fixture
def cleanup_overrides() -> Any:
    yield
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def operator_actor() -> HamActor:
    return HamActor(
        user_id="user_op",
        org_id=None,
        session_id="sess_o",
        email="operator@example.test",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


@pytest.fixture
def normie_actor() -> HamActor:
    return HamActor(
        user_id="user_normie",
        org_id=None,
        session_id="sess_n",
        email="normie@example.test",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


@pytest.fixture
def enforce_clerk_with_operator_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "true")
    monkeypatch.setenv("HAM_WORKSPACE_OPERATOR_EMAILS", "operator@example.test")


def _client(actor: HamActor | None = None) -> TestClient:
    if actor is not None:
        fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: actor
    return TestClient(app)


def _register_build_project(
    store: ProjectStore,
    *,
    name: str,
    root: Path,
    build_lane_enabled: bool = True,
    github_repo: str | None = "Code-Munkiz/ham",
) -> ProjectRecord:
    rec = store.make_record(name=name, root=str(root), description="")
    rec = rec.model_copy(
        update={
            "build_lane_enabled": build_lane_enabled,
            "github_repo": github_repo,
        }
    )
    return store.register(rec)


def _make_outcome(
    *,
    ok: bool = True,
    pr_url: str | None = "https://github.com/Code-Munkiz/ham/pull/9001",
    pr_branch: str | None = "ham-droid/abc12345",
    pr_commit_sha: str | None = "deadbeefcafe1234",
    build_outcome: str | None = "pr_opened",
    summary: str | None = "Updated docs and comments.",
    ham_run_id: str | None = "11111111-2222-3333-4444-555555555555",
    control_plane_status: str | None = "succeeded",
    error_summary: str | None = None,
) -> build_api.DroidBuildLaunchOutcome:
    return build_api.DroidBuildLaunchOutcome(
        ok=ok,
        ham_run_id=ham_run_id,
        control_plane_status=control_plane_status,
        pr_url=pr_url,
        pr_branch=pr_branch,
        pr_commit_sha=pr_commit_sha,
        build_outcome=build_outcome,  # type: ignore[arg-type]
        summary=summary,
        error_summary=error_summary,
    )


# ---------------------------------------------------------------------------
# Preview gates
# ---------------------------------------------------------------------------


def test_preview_rejects_workflow_id_field(isolated_store: ProjectStore, tmp_path: Path) -> None:
    """Client may never set workflow_id — even safe_edit_low must be 422."""
    root = tmp_path / "r"
    root.mkdir()
    rec = _register_build_project(isolated_store, name="p1", root=root)
    res = _client().post(
        "/api/droid/build/preview",
        json={
            "project_id": rec.id,
            "user_prompt": "tidy docs",
            "workflow_id": "safe_edit_low",
        },
    )
    assert res.status_code == 422


def test_preview_rejects_other_extra_fields(isolated_store: ProjectStore, tmp_path: Path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    rec = _register_build_project(isolated_store, name="p_extra", root=root)
    res = _client().post(
        "/api/droid/build/preview",
        json={
            "project_id": rec.id,
            "user_prompt": "tidy docs",
            "auto_level": "high",
        },
    )
    assert res.status_code == 422


def test_preview_unknown_project_404(isolated_store: ProjectStore) -> None:
    res = _client().post(
        "/api/droid/build/preview",
        json={"project_id": "project.unknown", "user_prompt": "x"},
    )
    assert res.status_code == 404
    assert res.json()["detail"]["error"]["code"] == "PROJECT_NOT_FOUND"


def test_preview_rejects_project_with_build_lane_disabled(
    isolated_store: ProjectStore, tmp_path: Path
) -> None:
    root = tmp_path / "r"
    root.mkdir()
    rec = _register_build_project(
        isolated_store, name="p_disabled", root=root, build_lane_enabled=False
    )
    res = _client().post(
        "/api/droid/build/preview",
        json={"project_id": rec.id, "user_prompt": "tidy docs"},
    )
    assert res.status_code == 422
    assert res.json()["detail"]["error"]["code"] == "BUILD_LANE_NOT_ENABLED_FOR_PROJECT"


def test_preview_rejects_project_without_github_repo(
    isolated_store: ProjectStore, tmp_path: Path
) -> None:
    root = tmp_path / "r"
    root.mkdir()
    rec = _register_build_project(isolated_store, name="p_norepo", root=root, github_repo=None)
    res = _client().post(
        "/api/droid/build/preview",
        json={"project_id": rec.id, "user_prompt": "tidy docs"},
    )
    assert res.status_code == 422
    assert res.json()["detail"]["error"]["code"] == "BUILD_LANE_PROJECT_MISSING_GITHUB_REPO"


def test_preview_requires_clerk_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch, isolated_store: ProjectStore
) -> None:
    monkeypatch.setenv("HAM_CLERK_REQUIRE_AUTH", "1")
    monkeypatch.delenv("HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS", raising=False)
    fastapi_app.dependency_overrides.pop(get_ham_clerk_actor, None)
    res = TestClient(app).post(
        "/api/droid/build/preview",
        json={"project_id": "x", "user_prompt": "y"},
    )
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "CLERK_SESSION_REQUIRED"


def test_preview_rejects_non_operator(
    isolated_store: ProjectStore,
    tmp_path: Path,
    normie_actor: HamActor,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    root = tmp_path / "r"
    root.mkdir()
    rec = _register_build_project(isolated_store, name="p_normie", root=root)
    res = _client(normie_actor).post(
        "/api/droid/build/preview",
        json={"project_id": rec.id, "user_prompt": "tidy docs"},
    )
    assert res.status_code == 403
    assert res.json()["detail"]["error"]["code"] == "WORKSPACE_OPERATOR_REQUIRED"


def test_preview_succeeds_for_operator(
    isolated_store: ProjectStore,
    tmp_path: Path,
    operator_actor: HamActor,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    root = tmp_path / "r"
    root.mkdir()
    rec = _register_build_project(isolated_store, name="p_ok", root=root)
    res = _client(operator_actor).post(
        "/api/droid/build/preview",
        json={"project_id": rec.id, "user_prompt": "Tidy README typos."},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "droid_build_preview"
    assert body["project_id"] == rec.id
    assert body["is_readonly"] is False
    assert body["will_open_pull_request"] is True
    assert body["requires_approval"] is True
    assert isinstance(body["proposal_digest"], str) and len(body["proposal_digest"]) == 64
    assert body["base_revision"] == REGISTRY_REVISION


def test_preview_response_does_not_leak_workflow_internals(
    isolated_store: ProjectStore,
    tmp_path: Path,
    operator_actor: HamActor,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    root = tmp_path / "r"
    root.mkdir()
    rec = _register_build_project(isolated_store, name="p_leak", root=root)
    res = _client(operator_actor).post(
        "/api/droid/build/preview",
        json={"project_id": rec.id, "user_prompt": "Tidy README."},
    )
    assert res.status_code == 200, res.text
    raw = res.text.lower()
    for forbidden in (
        "safe_edit_low",
        "low_edit",
        "--auto low",
        "--auto",
        "ham_droid_exec_token",
        "argv",
        "droid exec",
        "registry_revision",
    ):
        assert forbidden not in raw, f"preview leaks {forbidden!r}: {raw}"
    body = res.json()
    assert "workflow_id" not in body


# ---------------------------------------------------------------------------
# Launch gates
# ---------------------------------------------------------------------------


def _make_preview(client: TestClient, project_id: str, prompt: str) -> dict[str, Any]:
    r = client.post(
        "/api/droid/build/preview",
        json={"project_id": project_id, "user_prompt": prompt},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_launch_requires_confirmed(
    isolated_store: ProjectStore,
    tmp_path: Path,
    operator_actor: HamActor,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    root = tmp_path / "r"
    root.mkdir()
    rec = _register_build_project(isolated_store, name="p_l1", root=root)
    client = _client(operator_actor)
    pv = _make_preview(client, rec.id, "Tidy README.")
    res = client.post(
        "/api/droid/build/launch",
        json={
            "project_id": rec.id,
            "user_prompt": "Tidy README.",
            "proposal_digest": pv["proposal_digest"],
            "base_revision": pv["base_revision"],
            "confirmed": False,
            "accept_pr": True,
        },
    )
    assert res.status_code == 422
    assert res.json()["detail"]["error"]["code"] == "DROID_BUILD_LAUNCH_REQUIRES_CONFIRMATION"


def test_launch_requires_accept_pr(
    isolated_store: ProjectStore,
    tmp_path: Path,
    operator_actor: HamActor,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    root = tmp_path / "r"
    root.mkdir()
    rec = _register_build_project(isolated_store, name="p_l2", root=root)
    client = _client(operator_actor)
    pv = _make_preview(client, rec.id, "Tidy README.")
    res = client.post(
        "/api/droid/build/launch",
        json={
            "project_id": rec.id,
            "user_prompt": "Tidy README.",
            "proposal_digest": pv["proposal_digest"],
            "base_revision": pv["base_revision"],
            "confirmed": True,
            "accept_pr": False,
        },
    )
    assert res.status_code == 422
    assert res.json()["detail"]["error"]["code"] == "DROID_BUILD_LAUNCH_REQUIRES_ACCEPT_PR"


def test_launch_rejects_stale_digest(
    isolated_store: ProjectStore,
    tmp_path: Path,
    operator_actor: HamActor,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    root = tmp_path / "r"
    root.mkdir()
    rec = _register_build_project(isolated_store, name="p_l3", root=root)
    client = _client(operator_actor)
    pv = _make_preview(client, rec.id, "Tidy README.")
    res = client.post(
        "/api/droid/build/launch",
        json={
            "project_id": rec.id,
            "user_prompt": "Different prompt — digest should now mismatch.",
            "proposal_digest": pv["proposal_digest"],
            "base_revision": pv["base_revision"],
            "confirmed": True,
            "accept_pr": True,
        },
    )
    assert res.status_code == 409
    assert res.json()["detail"]["error"]["code"] == "DROID_BUILD_LAUNCH_PREVIEW_STALE"


def test_launch_rejects_non_operator(
    isolated_store: ProjectStore,
    tmp_path: Path,
    normie_actor: HamActor,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    root = tmp_path / "r"
    root.mkdir()
    rec = _register_build_project(isolated_store, name="p_l4", root=root)
    res = _client(normie_actor).post(
        "/api/droid/build/launch",
        json={
            "project_id": rec.id,
            "user_prompt": "Tidy README.",
            "proposal_digest": "0" * 64,
            "base_revision": REGISTRY_REVISION,
            "confirmed": True,
            "accept_pr": True,
        },
    )
    assert res.status_code == 403
    assert res.json()["detail"]["error"]["code"] == "WORKSPACE_OPERATOR_REQUIRED"


def test_launch_returns_unconfigured_when_token_missing_and_does_not_call_runner(
    isolated_store: ProjectStore,
    tmp_path: Path,
    operator_actor: HamActor,
    monkeypatch: pytest.MonkeyPatch,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    monkeypatch.delenv("HAM_DROID_EXEC_TOKEN", raising=False)
    root = tmp_path / "r"
    root.mkdir()
    rec = _register_build_project(isolated_store, name="p_l5", root=root)
    client = _client(operator_actor)
    pv = _make_preview(client, rec.id, "Tidy README.")

    sentinel: dict[str, bool] = {"called": False}

    def _boom(**_: Any) -> Any:  # pragma: no cover - must not be called
        sentinel["called"] = True
        raise AssertionError("executor must not be reached when token is missing")

    with patch("src.api.droid_build.execute_droid_build_workflow", _boom):
        res = client.post(
            "/api/droid/build/launch",
            json={
                "project_id": rec.id,
                "user_prompt": "Tidy README.",
                "proposal_digest": pv["proposal_digest"],
                "base_revision": pv["base_revision"],
                "confirmed": True,
                "accept_pr": True,
            },
        )
    assert sentinel["called"] is False
    assert res.status_code == 503
    assert res.json()["detail"]["error"]["code"] == "BUILD_LANE_UNCONFIGURED"


def test_launch_unknown_project_404(
    isolated_store: ProjectStore,
    operator_actor: HamActor,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    res = _client(operator_actor).post(
        "/api/droid/build/launch",
        json={
            "project_id": "project.nope",
            "user_prompt": "x",
            "proposal_digest": "0" * 64,
            "base_revision": REGISTRY_REVISION,
            "confirmed": True,
            "accept_pr": True,
        },
    )
    assert res.status_code == 404
    assert res.json()["detail"]["error"]["code"] == "PROJECT_NOT_FOUND"


def test_launch_happy_path_with_mocked_executor(
    isolated_store: ProjectStore,
    tmp_path: Path,
    operator_actor: HamActor,
    monkeypatch: pytest.MonkeyPatch,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_DROID_EXEC_TOKEN", "test-only-not-deployed")
    root = tmp_path / "r"
    root.mkdir()
    rec = _register_build_project(isolated_store, name="p_l_happy", root=root)
    client = _client(operator_actor)
    pv = _make_preview(client, rec.id, "Tidy README.")

    captured: dict[str, Any] = {}

    def _fake_executor(**kwargs: Any) -> build_api.DroidBuildLaunchOutcome:
        captured.update(kwargs)
        return _make_outcome()

    with patch(
        "src.api.droid_build.execute_droid_build_workflow",
        side_effect=_fake_executor,
    ):
        res = client.post(
            "/api/droid/build/launch",
            json={
                "project_id": rec.id,
                "user_prompt": "Tidy README.",
                "proposal_digest": pv["proposal_digest"],
                "base_revision": pv["base_revision"],
                "confirmed": True,
                "accept_pr": True,
            },
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "droid_build_launch"
    assert body["ok"] is True
    assert body["ham_run_id"] == "11111111-2222-3333-4444-555555555555"
    assert body["control_plane_status"] == "succeeded"
    assert body["pr_url"] == "https://github.com/Code-Munkiz/ham/pull/9001"
    assert body["pr_branch"] == "ham-droid/abc12345"
    assert body["pr_commit_sha"] == "deadbeefcafe1234"
    assert body["build_outcome"] == "pr_opened"
    assert body["summary"] == "Updated docs and comments."
    assert body["is_readonly"] is False
    assert body["will_open_pull_request"] is True
    assert body["requires_approval"] is True
    # Executor was called with the correct, hardcoded internals — never the
    # client workflow_id, never the env token in payload.
    assert captured["project_id"] == rec.id
    assert captured["proposal_digest"] == pv["proposal_digest"]
    assert "workflow_id" not in captured

    # Response body must not leak any internal workflow markers.
    raw = res.text.lower()
    for forbidden in (
        "safe_edit_low",
        "low_edit",
        "--auto low",
        "ham_droid_exec_token",
        "argv",
        "droid exec",
    ):
        assert forbidden not in raw, f"launch leaks {forbidden!r}"


def test_launch_failure_propagates_friendly_error(
    isolated_store: ProjectStore,
    tmp_path: Path,
    operator_actor: HamActor,
    monkeypatch: pytest.MonkeyPatch,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    monkeypatch.setenv("HAM_DROID_EXEC_TOKEN", "test-only-not-deployed")
    root = tmp_path / "r"
    root.mkdir()
    rec = _register_build_project(isolated_store, name="p_l_fail", root=root)
    client = _client(operator_actor)
    pv = _make_preview(client, rec.id, "Tidy README.")

    failure = _make_outcome(
        ok=False,
        pr_url=None,
        pr_branch="ham-droid/abc12345",
        pr_commit_sha=None,
        build_outcome="push_blocked",
        summary=None,
        control_plane_status="failed",
        error_summary="git push failed: branch protection rejected",
    )
    with patch(
        "src.api.droid_build.execute_droid_build_workflow",
        return_value=failure,
    ):
        res = client.post(
            "/api/droid/build/launch",
            json={
                "project_id": rec.id,
                "user_prompt": "Tidy README.",
                "proposal_digest": pv["proposal_digest"],
                "base_revision": pv["base_revision"],
                "confirmed": True,
                "accept_pr": True,
            },
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is False
    assert body["build_outcome"] == "push_blocked"
    assert body["pr_url"] is None
    assert body["control_plane_status"] == "failed"
    assert "branch protection" in (body.get("error_summary") or "")


# ---------------------------------------------------------------------------
# Scope lock — never expose safe_edit_low through this router; audit lane
# remains scoped to readonly_repo_audit.
# ---------------------------------------------------------------------------


def test_router_only_targets_safe_edit_low_internally() -> None:
    """The constant is hardcoded to safe_edit_low and the workflow is mutating + token-gated."""
    from src.ham.droid_workflows.registry import get_workflow

    assert build_api._BUILD_WORKFLOW_ID == "safe_edit_low"
    wf = get_workflow(build_api._BUILD_WORKFLOW_ID)
    assert wf is not None
    assert wf.mutates is True
    assert wf.requires_launch_token is True


def test_audit_router_still_rejects_mutating_workflows() -> None:
    """Regression: /api/droid/launch (audit) is locked to readonly_repo_audit only."""
    from src.api import droid_audit as audit_api
    from src.ham.droid_workflows.registry import get_workflow

    assert audit_api._AUDIT_WORKFLOW_ID == "readonly_repo_audit"
    wf = get_workflow(audit_api._AUDIT_WORKFLOW_ID)
    assert wf is not None
    assert wf.mutates is False
    assert wf.requires_launch_token is False


def test_audit_launch_rejects_safe_edit_low_payload(
    isolated_store: ProjectStore,
    tmp_path: Path,
    operator_actor: HamActor,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    """Regression: any attempt to smuggle workflow_id into /api/droid/launch is 422."""
    root = tmp_path / "r"
    root.mkdir()
    rec = _register_build_project(isolated_store, name="p_audit_reg", root=root)
    res = _client(operator_actor).post(
        "/api/droid/launch",
        json={
            "project_id": rec.id,
            "user_prompt": "tidy README",
            "proposal_digest": "0" * 64,
            "base_revision": REGISTRY_REVISION,
            "confirmed": True,
            "workflow_id": "safe_edit_low",
        },
    )
    assert res.status_code == 422


def test_token_env_name_is_never_in_responses(
    isolated_store: ProjectStore,
    tmp_path: Path,
    operator_actor: HamActor,
    enforce_clerk_with_operator_allowlist: None,
    cleanup_overrides: None,
) -> None:
    """A non-deploy regression: HAM_DROID_EXEC_TOKEN must never appear in any response body."""
    # Token unset (default deploy posture) — every gate path returns errors that
    # must not echo the env name.
    os.environ.pop("HAM_DROID_EXEC_TOKEN", None)
    root = tmp_path / "r"
    root.mkdir()
    rec = _register_build_project(isolated_store, name="p_tok", root=root)
    client = _client(operator_actor)

    pv = client.post(
        "/api/droid/build/preview",
        json={"project_id": rec.id, "user_prompt": "Tidy README."},
    )
    assert "HAM_DROID_EXEC_TOKEN".lower() not in pv.text.lower()
    pv_body = pv.json()

    lr = client.post(
        "/api/droid/build/launch",
        json={
            "project_id": rec.id,
            "user_prompt": "Tidy README.",
            "proposal_digest": pv_body["proposal_digest"],
            "base_revision": pv_body["base_revision"],
            "confirmed": True,
            "accept_pr": True,
        },
    )
    assert lr.status_code == 503
    assert "HAM_DROID_EXEC_TOKEN".lower() not in lr.text.lower()
