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
