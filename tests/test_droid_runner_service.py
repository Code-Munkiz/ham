"""Tests for the inbound HAM droid runner (POST /v1/ham/droid-exec)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.ham.droid_runner.allowed_roots import cwd_allowed_under_roots, load_allowed_roots_from_env
from src.ham.droid_runner.argv_validate import validate_remote_droid_argv
from src.ham.droid_runner.service import app
from src.tools.droid_executor import DroidExecutionRecord


@pytest.fixture
def runner_audit_path(tmp_path, monkeypatch: pytest.MonkeyPatch) -> object:
    p = tmp_path / "runner_audit.jsonl"
    monkeypatch.setenv("HAM_DROID_RUNNER_AUDIT_FILE", str(p))
    return p


@pytest.fixture
def client(runner_audit_path: object) -> TestClient:
    return TestClient(app)


def _valid_argv(cwd_resolved: str, *, auto: bool = False) -> list[str]:
    argv: list[str] = [
        "droid",
        "exec",
        "--cwd",
        cwd_resolved,
        "--output-format",
        "json",
    ]
    if auto:
        argv.extend(["--auto", "low"])
    argv.append("prompt line for droid")
    return argv


def test_validate_rejects_non_droid_executable(tmp_path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    err = validate_remote_droid_argv(
        ["bash", "-c", "echo", "x"],
        expected_cwd=root,
    )
    assert err and "droid" in err.lower()


def test_validate_rejects_forbidden_flag(tmp_path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    bad = _valid_argv(str(root.resolve()))
    bad.insert(4, "--skip-permissions-unsafe")
    err = validate_remote_droid_argv(bad, expected_cwd=root)
    assert err and "Forbidden" in err


def test_validate_rejects_cwd_mismatch(tmp_path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    argv = _valid_argv(str(other.resolve()))
    err = validate_remote_droid_argv(argv, expected_cwd=root)
    assert err and "does not match" in err


def test_runner_unconfigured_returns_503(client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("HAM_DROID_RUNNER_ALLOWED_ROOTS", raising=False)
    monkeypatch.delenv("HAM_DROID_RUNNER_SERVICE_TOKEN", raising=False)
    r = client.post(
        "/v1/ham/droid-exec",
        json={"argv": ["droid"], "cwd": "/", "timeout_sec": 30},
        headers={"Authorization": "Bearer x"},
    )
    assert r.status_code == 503


def test_runner_missing_bearer_returns_401(client: TestClient, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HAM_DROID_RUNNER_SERVICE_TOKEN", "secret")
    root = tmp_path / "r"
    root.mkdir()
    r = client.post(
        "/v1/ham/droid-exec",
        json={
            "argv": _valid_argv(str(root.resolve())),
            "cwd": str(root.resolve()),
            "timeout_sec": 30,
        },
    )
    assert r.status_code == 401


def test_runner_invalid_bearer_returns_403(client: TestClient, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HAM_DROID_RUNNER_SERVICE_TOKEN", "secret")
    root = tmp_path / "r"
    root.mkdir()
    r = client.post(
        "/v1/ham/droid-exec",
        json={
            "argv": _valid_argv(str(root.resolve())),
            "cwd": str(root.resolve()),
            "timeout_sec": 30,
        },
        headers={"Authorization": "Bearer wrong"},
    )
    assert r.status_code == 403


def test_runner_missing_cwd_returns_422(client: TestClient, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HAM_DROID_RUNNER_SERVICE_TOKEN", "secret")
    root = tmp_path / "r"
    root.mkdir()
    missing = tmp_path / "nope"
    r = client.post(
        "/v1/ham/droid-exec",
        json={
            "argv": _valid_argv(str(root.resolve())),
            "cwd": str(missing.resolve()),
            "timeout_sec": 30,
        },
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code == 422


def test_runner_argv_forbidden_flag_returns_422(client: TestClient, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HAM_DROID_RUNNER_SERVICE_TOKEN", "secret")
    root = tmp_path / "r"
    root.mkdir()
    argv = _valid_argv(str(root.resolve()))
    argv.insert(6, "--skip-permissions-unsafe")
    r = client.post(
        "/v1/ham/droid-exec",
        json={
            "argv": argv,
            "cwd": str(root.resolve()),
            "timeout_sec": 30,
        },
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["detail"]["error"]["code"] == "ARGV_REJECTED"


def test_runner_non_droid_argv_returns_422(client: TestClient, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HAM_DROID_RUNNER_SERVICE_TOKEN", "secret")
    root = tmp_path / "r"
    root.mkdir()
    argv = _valid_argv(str(root.resolve()))
    argv[0] = "sh"
    r = client.post(
        "/v1/ham/droid-exec",
        json={
            "argv": argv,
            "cwd": str(root.resolve()),
            "timeout_sec": 30,
        },
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code == 422


@patch("src.ham.droid_runner.service.droid_executor")
def test_runner_structured_success(
    mock_ex: object,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("HAM_DROID_RUNNER_SERVICE_TOKEN", "secret")
    root = tmp_path / "r"
    root.mkdir()
    mock_ex.return_value = DroidExecutionRecord(
        argv=_valid_argv(str(root.resolve())),
        working_dir=str(root.resolve()),
        exit_code=0,
        timed_out=False,
        stdout=json.dumps({"result": "ok"}),
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        started_at="t0",
        ended_at="t1",
        duration_ms=42,
    )
    r = client.post(
        "/v1/ham/droid-exec",
        json={
            "argv": _valid_argv(str(root.resolve())),
            "cwd": str(root.resolve()),
            "timeout_sec": 30,
        },
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["exit_code"] == 0
    assert data["timed_out"] is False
    assert data["duration_ms"] == 42
    assert data["parsed_stdout"] == {"result": "ok"}
    mock_ex.assert_called_once()


@patch("src.ham.droid_runner.service.droid_executor")
def test_runner_structured_process_failure(
    mock_ex: object,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("HAM_DROID_RUNNER_SERVICE_TOKEN", "secret")
    root = tmp_path / "r"
    root.mkdir()
    mock_ex.return_value = DroidExecutionRecord(
        argv=_valid_argv(str(root.resolve())),
        working_dir=str(root.resolve()),
        exit_code=3,
        timed_out=False,
        stdout="",
        stderr="droid failed",
        stdout_truncated=False,
        stderr_truncated=False,
        started_at="t0",
        ended_at="t1",
        duration_ms=10,
    )
    r = client.post(
        "/v1/ham/droid-exec",
        json={
            "argv": _valid_argv(str(root.resolve())),
            "cwd": str(root.resolve()),
            "timeout_sec": 30,
        },
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["exit_code"] == 3
    assert data["stderr"] == "droid failed"
    assert "parsed_stdout" not in data


def test_cwd_allowed_under_roots_containment(tmp_path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    sub = allowed / "sub"
    sub.mkdir()
    assert cwd_allowed_under_roots(sub.resolve(), [allowed.resolve()])
    assert cwd_allowed_under_roots(allowed.resolve(), [allowed.resolve()])
    sibling = tmp_path / "other"
    sibling.mkdir()
    assert not cwd_allowed_under_roots(sibling.resolve(), [allowed.resolve()])


def test_load_allowed_roots_from_env_comma_separated(tmp_path, monkeypatch) -> None:
    r1 = tmp_path / "r1"
    r1.mkdir()
    r2 = tmp_path / "r2"
    r2.mkdir()
    monkeypatch.setenv(
        "HAM_DROID_RUNNER_ALLOWED_ROOTS",
        f"{r1.resolve()},{r2.resolve()}",
    )
    roots = load_allowed_roots_from_env()
    assert roots == [r1.resolve(), r2.resolve()]


def test_cwd_outside_allowed_roots_returns_422_and_audits(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    runner_audit_path,
) -> None:
    monkeypatch.setenv("HAM_DROID_RUNNER_SERVICE_TOKEN", "secret")
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    jail = tmp_path / "jail"
    jail.mkdir()
    monkeypatch.setenv("HAM_DROID_RUNNER_ALLOWED_ROOTS", str(allowed.resolve()))
    argv_cwd = jail.resolve()
    r = client.post(
        "/v1/ham/droid-exec",
        json={
            "argv": _valid_argv(str(argv_cwd)),
            "cwd": str(jail.resolve()),
            "timeout_sec": 30,
            "workflow_id": "readonly_repo_audit",
            "project_id": "project.x",
        },
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "CWD_NOT_ALLOWED"
    lines = Path(str(runner_audit_path)).read_text(encoding="utf-8").strip().splitlines()
    row = json.loads(lines[-1])
    assert row["status"] == "blocked"
    assert row["blocked_code"] == "CWD_NOT_ALLOWED"
    assert row["workflow_id"] == "readonly_repo_audit"
    assert row["project_id"] == "project.x"


def test_symlink_resolved_cwd_outside_allowed_roots_blocked(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    runner_audit_path,
) -> None:
    monkeypatch.setenv("HAM_DROID_RUNNER_SERVICE_TOKEN", "secret")
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    trap = allowed / "trap"
    trap.symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv("HAM_DROID_RUNNER_ALLOWED_ROOTS", str(allowed.resolve()))
    resolved = trap.resolve()
    assert resolved == outside.resolve()
    r = client.post(
        "/v1/ham/droid-exec",
        json={
            "argv": _valid_argv(str(resolved)),
            "cwd": str(trap),
            "timeout_sec": 30,
        },
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "CWD_NOT_ALLOWED"
    lines = Path(str(runner_audit_path)).read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(lines[-1])["status"] == "blocked"


@patch("src.ham.droid_runner.service.droid_executor")
def test_success_writes_audit_executed_row(
    mock_ex: object,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    runner_audit_path,
) -> None:
    monkeypatch.setenv("HAM_DROID_RUNNER_SERVICE_TOKEN", "secret")
    root = tmp_path / "r"
    root.mkdir()
    mock_ex.return_value = DroidExecutionRecord(
        argv=_valid_argv(str(root.resolve())),
        working_dir=str(root.resolve()),
        exit_code=0,
        timed_out=False,
        stdout="{}",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        started_at="t0",
        ended_at="t1",
        duration_ms=99,
    )
    digest = "a" * 64
    r = client.post(
        "/v1/ham/droid-exec",
        json={
            "argv": _valid_argv(str(root.resolve())),
            "cwd": str(root.resolve()),
            "timeout_sec": 30,
            "workflow_id": "safe_edit_low",
            "audit_id": "corr-1",
            "proposal_digest": digest,
            "project_id": "project.p",
            "session_id": "sess-9",
        },
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["runner_request_id"]
    assert data["workflow_id"] == "safe_edit_low"
    assert data["audit_id"] == "corr-1"
    assert data["proposal_digest"] == digest
    assert data["project_id"] == "project.p"
    assert data["session_id"] == "sess-9"
    lines = Path(str(runner_audit_path)).read_text(encoding="utf-8").strip().splitlines()
    row = json.loads(lines[-1])
    assert row["status"] == "executed"
    assert row["execution_ok"] is True
    assert row["exit_code"] == 0
    assert row["duration_ms"] == 99
    assert row["proposal_digest"] == digest
    assert row["ham_audit_id"] == "corr-1"


def test_argv_blocked_writes_audit_row(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    runner_audit_path,
) -> None:
    monkeypatch.setenv("HAM_DROID_RUNNER_SERVICE_TOKEN", "secret")
    root = tmp_path / "r"
    root.mkdir()
    argv = _valid_argv(str(root.resolve()))
    argv[0] = "sh"
    r = client.post(
        "/v1/ham/droid-exec",
        json={
            "argv": argv,
            "cwd": str(root.resolve()),
            "timeout_sec": 30,
            "workflow_id": "readonly_repo_audit",
        },
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code == 422
    row = json.loads(Path(str(runner_audit_path)).read_text(encoding="utf-8").strip().splitlines()[-1])
    assert row["status"] == "blocked"
    assert row["blocked_code"] == "ARGV_REJECTED"
    assert row["workflow_id"] == "readonly_repo_audit"


# ---------------------------------------------------------------------------
# Build Lane (P2 dark): mode="build" argv extras, default behavior unchanged.
# ---------------------------------------------------------------------------


def test_validate_build_mode_requires_auto_low(tmp_path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    # Argv is missing --auto low (auto=False).
    err = validate_remote_droid_argv(
        _valid_argv(str(root.resolve()), auto=False),
        expected_cwd=root,
        mode="build",
    )
    assert err and "Build mode requires `--auto low`" in err


def test_validate_build_mode_requires_output_format_json(tmp_path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    # Manually build argv that omits --output-format entirely.
    argv = [
        "droid",
        "exec",
        "--cwd",
        str(root.resolve()),
        "--auto",
        "low",
        "build prompt",
    ]
    err = validate_remote_droid_argv(argv, expected_cwd=root, mode="build")
    assert err and "Build mode requires `--output-format json`" in err


def test_validate_build_mode_accepts_full_argv(tmp_path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    err = validate_remote_droid_argv(
        _valid_argv(str(root.resolve()), auto=True),
        expected_cwd=root,
        mode="build",
    )
    assert err is None


def test_validate_audit_mode_unchanged_no_auto_required(tmp_path) -> None:
    """Default/audit mode must keep accepting argv without --auto low (regression guard)."""
    root = tmp_path / "r"
    root.mkdir()
    assert (
        validate_remote_droid_argv(
            _valid_argv(str(root.resolve()), auto=False),
            expected_cwd=root,
        )
        is None
    )
    assert (
        validate_remote_droid_argv(
            _valid_argv(str(root.resolve()), auto=False),
            expected_cwd=root,
            mode="audit",
        )
        is None
    )


def test_runner_build_mode_missing_auto_returns_422(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    runner_audit_path,
) -> None:
    monkeypatch.setenv("HAM_DROID_RUNNER_SERVICE_TOKEN", "secret")
    root = tmp_path / "r"
    root.mkdir()
    r = client.post(
        "/v1/ham/droid-exec",
        json={
            "argv": _valid_argv(str(root.resolve()), auto=False),
            "cwd": str(root.resolve()),
            "timeout_sec": 30,
            "mode": "build",
        },
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["detail"]["error"]["code"] == "ARGV_REJECTED"
    assert "auto" in body["detail"]["error"]["message"].lower()
    row = json.loads(
        Path(str(runner_audit_path)).read_text(encoding="utf-8").strip().splitlines()[-1]
    )
    assert row["status"] == "blocked"
    assert row["blocked_code"] == "ARGV_REJECTED"
    assert row["mode"] == "build"


@patch("src.ham.droid_runner.service._run_build_lane")
@patch("src.ham.droid_runner.service.droid_executor")
def test_runner_build_mode_full_argv_executes(
    mock_ex: object,
    mock_build_lane: object,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    runner_audit_path,
) -> None:
    """``mode=build`` + ``accept_pr=true`` executes droid then build lane (mocked)."""
    from src.ham.droid_runner.build_lane_output import OutputResult

    monkeypatch.setenv("HAM_DROID_RUNNER_SERVICE_TOKEN", "secret")
    root = tmp_path / "r"
    root.mkdir()
    argv = _valid_argv(str(root.resolve()), auto=True)
    mock_ex.return_value = DroidExecutionRecord(
        argv=argv,
        working_dir=str(root.resolve()),
        exit_code=0,
        timed_out=False,
        stdout="{}",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        started_at="t0",
        ended_at="t1",
        duration_ms=11,
    )
    mock_build_lane.return_value = OutputResult(
        target="github_pr",
        build_outcome="succeeded",
        target_ref={
            "pr_url": "https://github.com/Code-Munkiz/ham/pull/1234",
            "pr_branch": "ham-droid/aabbccdd",
            "pr_commit_sha": "deadbeef00000000",
        },
        error_summary=None,
        pr_url="https://github.com/Code-Munkiz/ham/pull/1234",
        pr_branch="ham-droid/aabbccdd",
        pr_commit_sha="deadbeef00000000",
    )
    r = client.post(
        "/v1/ham/droid-exec",
        json={
            "argv": argv,
            "cwd": str(root.resolve()),
            "timeout_sec": 30,
            "mode": "build",
            "accept_pr": True,
            "workflow_id": "safe_edit_low",
        },
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "build"
    assert data["build_outcome"] == "pr_opened"
    assert data["pr_url"] == "https://github.com/Code-Munkiz/ham/pull/1234"
    assert data["pr_branch"] == "ham-droid/aabbccdd"
    assert data["pr_commit_sha"] == "deadbeef00000000"
    row = json.loads(
        Path(str(runner_audit_path)).read_text(encoding="utf-8").strip().splitlines()[-1]
    )
    assert row["status"] == "executed"
    assert row["mode"] == "build"
    assert row["build_outcome"] == "pr_opened"
    # build lane invoked exactly once with the resolved cwd/run.
    assert mock_build_lane.call_count == 1


@patch("src.ham.droid_runner.service._run_build_lane")
@patch("src.ham.droid_runner.service.droid_executor")
def test_runner_build_mode_without_accept_pr_is_422_and_skips_droid(
    mock_ex: object,
    mock_build_lane: object,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    runner_audit_path,
) -> None:
    monkeypatch.setenv("HAM_DROID_RUNNER_SERVICE_TOKEN", "secret")
    root = tmp_path / "r"
    root.mkdir()
    argv = _valid_argv(str(root.resolve()), auto=True)
    r = client.post(
        "/v1/ham/droid-exec",
        json={
            "argv": argv,
            "cwd": str(root.resolve()),
            "timeout_sec": 30,
            "mode": "build",
            "workflow_id": "safe_edit_low",
        },
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "BUILD_MODE_REQUIRES_ACCEPT_PR"
    # Defense in depth: neither droid nor build lane should have run.
    assert getattr(mock_ex, "call_count", 0) == 0
    assert getattr(mock_build_lane, "call_count", 0) == 0
    row = json.loads(
        Path(str(runner_audit_path)).read_text(encoding="utf-8").strip().splitlines()[-1]
    )
    assert row["status"] == "blocked"
    assert row["blocked_code"] == "BUILD_MODE_REQUIRES_ACCEPT_PR"
    assert row["mode"] == "build"


@patch("src.ham.droid_runner.service._run_build_lane")
@patch("src.ham.droid_runner.service.droid_executor")
def test_runner_build_mode_skips_build_lane_when_droid_fails(
    mock_ex: object,
    mock_build_lane: object,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    runner_audit_path,
) -> None:
    monkeypatch.setenv("HAM_DROID_RUNNER_SERVICE_TOKEN", "secret")
    root = tmp_path / "r"
    root.mkdir()
    argv = _valid_argv(str(root.resolve()), auto=True)
    mock_ex.return_value = DroidExecutionRecord(
        argv=argv,
        working_dir=str(root.resolve()),
        exit_code=3,
        timed_out=False,
        stdout="",
        stderr="droid failed",
        stdout_truncated=False,
        stderr_truncated=False,
        started_at="t0",
        ended_at="t1",
        duration_ms=5,
    )
    r = client.post(
        "/v1/ham/droid-exec",
        json={
            "argv": argv,
            "cwd": str(root.resolve()),
            "timeout_sec": 30,
            "mode": "build",
            "accept_pr": True,
            "workflow_id": "safe_edit_low",
        },
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["exit_code"] == 3
    assert "build_outcome" not in data
    assert "pr_url" not in data
    assert mock_build_lane.call_count == 0
    row = json.loads(
        Path(str(runner_audit_path)).read_text(encoding="utf-8").strip().splitlines()[-1]
    )
    assert row["status"] == "executed"
    assert row["execution_ok"] is False
    assert "build_outcome" not in row


@patch("src.ham.droid_runner.service._run_build_lane")
@patch("src.ham.droid_runner.service.droid_executor")
def test_runner_build_mode_nothing_to_change_surfaces_outcome(
    mock_ex: object,
    mock_build_lane: object,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    runner_audit_path,
) -> None:
    from src.ham.droid_runner.build_lane_output import OutputResult

    monkeypatch.setenv("HAM_DROID_RUNNER_SERVICE_TOKEN", "secret")
    root = tmp_path / "r"
    root.mkdir()
    argv = _valid_argv(str(root.resolve()), auto=True)
    mock_ex.return_value = DroidExecutionRecord(
        argv=argv,
        working_dir=str(root.resolve()),
        exit_code=0,
        timed_out=False,
        stdout="{}",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        started_at="t0",
        ended_at="t1",
        duration_ms=8,
    )
    mock_build_lane.return_value = OutputResult(
        target="github_pr",
        build_outcome="nothing_to_change",
        target_ref={"pr_branch": "ham-droid/eeff0011"},
        error_summary=None,
        pr_url=None,
        pr_branch="ham-droid/eeff0011",
        pr_commit_sha=None,
    )
    r = client.post(
        "/v1/ham/droid-exec",
        json={
            "argv": argv,
            "cwd": str(root.resolve()),
            "timeout_sec": 30,
            "mode": "build",
            "accept_pr": True,
            "workflow_id": "safe_edit_low",
        },
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["build_outcome"] == "nothing_to_change"
    assert data["pr_url"] is None
    assert data["pr_branch"] == "ham-droid/eeff0011"


@patch("src.ham.droid_runner.service._run_build_lane")
@patch("src.ham.droid_runner.service.droid_executor")
def test_runner_build_lane_response_never_leaks_internal_markers(
    mock_ex: object,
    mock_build_lane: object,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Build lane response must not echo any forbidden internal markers."""
    from src.ham.droid_runner.build_lane_output import OutputResult

    monkeypatch.setenv("HAM_DROID_RUNNER_SERVICE_TOKEN", "secret")
    root = tmp_path / "r"
    root.mkdir()
    argv = _valid_argv(str(root.resolve()), auto=True)
    mock_ex.return_value = DroidExecutionRecord(
        argv=argv,
        working_dir=str(root.resolve()),
        exit_code=0,
        timed_out=False,
        stdout="{}",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        started_at="t0",
        ended_at="t1",
        duration_ms=4,
    )
    mock_build_lane.return_value = OutputResult(
        target="github_pr",
        build_outcome="succeeded",
        target_ref={
            "pr_url": "https://github.com/Code-Munkiz/ham/pull/55",
            "pr_branch": "ham-droid/abcd1234",
            "pr_commit_sha": "cafebabe",
        },
        error_summary=None,
        pr_url="https://github.com/Code-Munkiz/ham/pull/55",
        pr_branch="ham-droid/abcd1234",
        pr_commit_sha="cafebabe",
    )
    r = client.post(
        "/v1/ham/droid-exec",
        json={
            "argv": argv,
            "cwd": str(root.resolve()),
            "timeout_sec": 30,
            "mode": "build",
            "accept_pr": True,
            "workflow_id": "safe_edit_low",
            "pr_title": "ignore me",
            "pr_body": "ignore me too",
            "commit_message": "ignore",
        },
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code == 200
    raw = r.text
    # The runner is allowed to echo workflow_id back to HAM (callers correlate
    # on it), but must never echo secret env names or shell-level details.
    for forbidden in (
        "HAM_DROID_EXEC_TOKEN",
        "FACTORY_API_KEY",
        "HAM_DROID_RUNNER_TOKEN",
        "--skip-permissions-unsafe",
    ):
        assert forbidden not in raw, f"response leaks {forbidden!r}"


@patch("src.ham.droid_runner.service.droid_executor")
def test_runner_default_mode_omits_mode_in_audit_and_response(
    mock_ex: object,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    runner_audit_path,
) -> None:
    """No regression: default-mode requests still execute and audit identically."""
    monkeypatch.setenv("HAM_DROID_RUNNER_SERVICE_TOKEN", "secret")
    root = tmp_path / "r"
    root.mkdir()
    argv = _valid_argv(str(root.resolve()))
    mock_ex.return_value = DroidExecutionRecord(
        argv=argv,
        working_dir=str(root.resolve()),
        exit_code=0,
        timed_out=False,
        stdout="{}",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        started_at="t0",
        ended_at="t1",
        duration_ms=22,
    )
    r = client.post(
        "/v1/ham/droid-exec",
        json={
            "argv": argv,
            "cwd": str(root.resolve()),
            "timeout_sec": 30,
        },
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "mode" not in data
    row = json.loads(
        Path(str(runner_audit_path)).read_text(encoding="utf-8").strip().splitlines()[-1]
    )
    assert "mode" not in row
    assert row["status"] == "executed"
