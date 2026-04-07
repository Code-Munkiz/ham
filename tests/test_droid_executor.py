from __future__ import annotations

import subprocess
from importlib import import_module

from src.tools.droid_executor import DroidExecutionRecord, droid_executor


def test_droid_executor_success_case(tmp_path):
    result = droid_executor(
        ["python", "-c", "print('ok')"],
        working_dir=str(tmp_path),
        timeout_sec=5,
    )
    assert isinstance(result, DroidExecutionRecord)
    assert result.timed_out is False
    assert result.exit_code == 0
    assert "ok" in result.stdout


def test_droid_executor_non_zero_exit_with_stderr(tmp_path):
    result = droid_executor(
        ["python", "-c", "import sys;sys.stderr.write('bad');sys.exit(2)"],
        working_dir=str(tmp_path),
        timeout_sec=5,
    )
    assert result.timed_out is False
    assert result.exit_code == 2
    assert "bad" in result.stderr


def test_droid_executor_timeout(tmp_path):
    result = droid_executor(
        ["python", "-c", "import time;time.sleep(2)"],
        working_dir=str(tmp_path),
        timeout_sec=1,
    )
    assert result.timed_out is True
    assert result.exit_code is None


def test_droid_executor_output_truncation_flags(tmp_path):
    big = "x" * 5000
    result = droid_executor(
        ["python", "-c", f"print('{big}')"],
        working_dir=str(tmp_path),
        timeout_sec=5,
        max_stdout_chars=200,
    )
    assert result.stdout_truncated is True
    assert len(result.stdout) == 200


def test_droid_executor_deterministic_capture(tmp_path):
    r1 = droid_executor(["python", "-c", "print('stable')"], working_dir=str(tmp_path))
    r2 = droid_executor(["python", "-c", "print('stable')"], working_dir=str(tmp_path))
    assert r1.exit_code == r2.exit_code == 0
    assert "stable" in r1.stdout
    assert "stable" in r2.stdout


def test_droid_executor_calls_subprocess_with_shell_false(monkeypatch, tmp_path):
    seen: dict[str, object] = {}
    module = import_module("src.tools.droid_executor")

    def fake_run(*args, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    result = droid_executor(["python", "-c", "print('ok')"], working_dir=str(tmp_path))
    assert result.exit_code == 0
    assert seen.get("shell") is False
    assert seen.get("capture_output") is True

