from __future__ import annotations

from dataclasses import dataclass

from src.bridge.contracts import (
    BridgeStatus,
    CommandSpec,
    ExecutionIntent,
    LimitSpec,
    ScopeSpec,
)
from src.bridge.runtime import run_bridge_v0
from src.hermes_feedback import HermesReviewer
from src.tools.droid_executor import DroidExecutionRecord


@dataclass
class _FakeAssembly:
    droid_executor: object


class _FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response

    def call(self, _prompt: str) -> str:
        return self.response


def _intent(tmp_path, commands: list[CommandSpec]) -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="intent-1",
        request_id="request-1",
        run_id="run-1",
        task_class="inspect",
        commands=commands,
        scope=ScopeSpec(allowed_roots=[str(tmp_path)]),
        limits=LimitSpec(
            max_commands=3,
            timeout_sec_per_command=5,
            max_stdout_chars=1000,
            max_stderr_chars=1000,
            max_total_output_chars=2000,
        ),
        reason="runtime test",
    )


def _record(argv: list[str], *, exit_code=0, timed_out=False, stderr="") -> DroidExecutionRecord:
    return DroidExecutionRecord(
        argv=argv,
        working_dir=".",
        exit_code=exit_code,
        timed_out=timed_out,
        stdout="ok",
        stderr=stderr,
        stdout_truncated=False,
        stderr_truncated=False,
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T00:00:01Z",
        duration_ms=1000,
    )


def test_bridge_runtime_rejected_and_no_side_effect(tmp_path, monkeypatch):
    called = {"count": 0}

    def fake_exec(*_args, **_kwargs):
        called["count"] += 1
        return _record(["python"])

    assembly = _FakeAssembly(droid_executor=fake_exec)
    bad = _intent(
        tmp_path,
        [CommandSpec(command_id="c1", argv=["curl", "https://x"], working_dir=str(tmp_path))],
    )
    monkeypatch.setattr("src.bridge.runtime.git_status", lambda _cwd: None)
    result = run_bridge_v0(assembly, bad)
    assert result.status == BridgeStatus.REJECTED
    assert called["count"] == 0


def test_bridge_runtime_executed(tmp_path, monkeypatch):
    assembly = _FakeAssembly(droid_executor=lambda *_a, **_k: _record(["python"], exit_code=0))
    intent = _intent(
        tmp_path,
        [CommandSpec(command_id="c1", argv=["python", "-c", "print('ok')"], working_dir=str(tmp_path))],
    )
    monkeypatch.setattr("src.bridge.runtime.git_status", lambda _cwd: "clean")
    result = run_bridge_v0(assembly, intent)
    assert result.status == BridgeStatus.EXECUTED
    assert result.intent_id == "intent-1"
    assert result.request_id == "request-1"
    assert result.run_id == "run-1"
    assert result.started_at
    assert result.ended_at
    assert result.duration_ms >= 0


def test_bridge_runtime_failed(tmp_path, monkeypatch):
    assembly = _FakeAssembly(
        droid_executor=lambda *_a, **_k: _record(["python"], exit_code=2, stderr="bad")
    )
    intent = _intent(
        tmp_path,
        [CommandSpec(command_id="c1", argv=["python", "-c", "import sys;sys.exit(2)"], working_dir=str(tmp_path))],
    )
    monkeypatch.setattr("src.bridge.runtime.git_status", lambda _cwd: "clean")
    result = run_bridge_v0(assembly, intent)
    assert result.status == BridgeStatus.FAILED


def test_bridge_runtime_timed_out(tmp_path, monkeypatch):
    assembly = _FakeAssembly(
        droid_executor=lambda *_a, **_k: _record(["python"], exit_code=None, timed_out=True)
    )
    intent = _intent(
        tmp_path,
        [CommandSpec(command_id="c1", argv=["python", "-c", "import time;time.sleep(1)"], working_dir=str(tmp_path))],
    )
    monkeypatch.setattr("src.bridge.runtime.git_status", lambda _cwd: "clean")
    result = run_bridge_v0(assembly, intent)
    assert result.status == BridgeStatus.TIMED_OUT


def test_bridge_runtime_partial(tmp_path, monkeypatch):
    records = [
        _record(["python"], exit_code=0),
        _record(["python"], exit_code=2, stderr="bad"),
    ]

    def fake_exec(*_a, **_k):
        return records.pop(0)

    assembly = _FakeAssembly(droid_executor=fake_exec)
    intent = _intent(
        tmp_path,
        [
            CommandSpec(command_id="c1", argv=["python", "-c", "print('ok')"], working_dir=str(tmp_path)),
            CommandSpec(command_id="c2", argv=["python", "-c", "import sys;sys.exit(2)"], working_dir=str(tmp_path)),
        ],
    )
    monkeypatch.setattr("src.bridge.runtime.git_status", lambda _cwd: "clean")
    result = run_bridge_v0(assembly, intent)
    assert result.status == BridgeStatus.PARTIAL


def test_bridge_result_handoff_to_hermes_reviewer(tmp_path, monkeypatch):
    assembly = _FakeAssembly(droid_executor=lambda *_a, **_k: _record(["python"], exit_code=0))
    intent = _intent(
        tmp_path,
        [CommandSpec(command_id="c1", argv=["python", "-c", "print('ok')"], working_dir=str(tmp_path))],
    )
    monkeypatch.setattr("src.bridge.runtime.git_status", lambda _cwd: "clean")
    bridge_result = run_bridge_v0(assembly, intent)

    reviewer = HermesReviewer()
    reviewer._client = _FakeLLM('{"ok": true, "confidence": "high", "notes": []}')
    payload = bridge_result.model_dump_json() if hasattr(bridge_result, "model_dump_json") else str(bridge_result.dict())
    review = reviewer.evaluate(payload, "bridge runtime evidence")
    assert set(review.keys()) == {"ok", "notes", "code", "context"}
    assert review["ok"] is True


def test_total_output_capped_across_stdout_and_stderr(tmp_path, monkeypatch):
    def fake_exec(*_a, **_k):
        return DroidExecutionRecord(
            argv=["python", "-c", "print('x')"],
            working_dir=str(tmp_path),
            exit_code=0,
            timed_out=False,
            stdout="A" * 80,
            stderr="B" * 80,
            stdout_truncated=False,
            stderr_truncated=False,
            started_at="2026-01-01T00:00:00Z",
            ended_at="2026-01-01T00:00:01Z",
            duration_ms=1000,
        )

    assembly = _FakeAssembly(droid_executor=fake_exec)
    intent = _intent(
        tmp_path,
        [CommandSpec(command_id="c1", argv=["python", "-c", "print('ok')"], working_dir=str(tmp_path))],
    )
    intent.limits.max_total_output_chars = 100
    monkeypatch.setattr("src.bridge.runtime.git_status", lambda _cwd: "clean")
    result = run_bridge_v0(assembly, intent)
    ev = result.commands[0]
    assert len(ev.stdout) + len(ev.stderr) <= 100
    assert ev.stdout_truncated or ev.stderr_truncated
    assert result.status == BridgeStatus.EXECUTED


def test_total_output_capped_across_multiple_commands(tmp_path, monkeypatch):
    records = [
        DroidExecutionRecord(
            argv=["python", "-c", "print('x')"],
            working_dir=str(tmp_path),
            exit_code=0,
            timed_out=False,
            stdout="A" * 70,
            stderr="",
            stdout_truncated=False,
            stderr_truncated=False,
            started_at="2026-01-01T00:00:00Z",
            ended_at="2026-01-01T00:00:01Z",
            duration_ms=1000,
        ),
        DroidExecutionRecord(
            argv=["python", "-c", "print('y')"],
            working_dir=str(tmp_path),
            exit_code=2,
            timed_out=False,
            stdout="",
            stderr="B" * 70,
            stdout_truncated=False,
            stderr_truncated=False,
            started_at="2026-01-01T00:00:00Z",
            ended_at="2026-01-01T00:00:01Z",
            duration_ms=1000,
        ),
    ]

    def fake_exec(*_a, **_k):
        return records.pop(0)

    assembly = _FakeAssembly(droid_executor=fake_exec)
    intent = _intent(
        tmp_path,
        [
            CommandSpec(command_id="c1", argv=["python", "-c", "print('ok')"], working_dir=str(tmp_path)),
            CommandSpec(command_id="c2", argv=["python", "-c", "import sys;sys.exit(2)"], working_dir=str(tmp_path)),
        ],
    )
    intent.limits.max_total_output_chars = 100
    monkeypatch.setattr("src.bridge.runtime.git_status", lambda _cwd: "clean")
    result = run_bridge_v0(assembly, intent)
    total = sum(len(c.stdout) + len(c.stderr) for c in result.commands)
    assert total <= 100
    # Status mapping should not drift from evidence-status logic.
    assert result.status == BridgeStatus.PARTIAL


def test_total_output_truncation_is_deterministic(tmp_path, monkeypatch):
    def fake_exec(*_a, **_k):
        return DroidExecutionRecord(
            argv=["python", "-c", "print('x')"],
            working_dir=str(tmp_path),
            exit_code=0,
            timed_out=False,
            stdout="A" * 80,
            stderr="B" * 80,
            stdout_truncated=False,
            stderr_truncated=False,
            started_at="2026-01-01T00:00:00Z",
            ended_at="2026-01-01T00:00:01Z",
            duration_ms=1000,
        )

    assembly = _FakeAssembly(droid_executor=fake_exec)
    intent = _intent(
        tmp_path,
        [CommandSpec(command_id="c1", argv=["python", "-c", "print('ok')"], working_dir=str(tmp_path))],
    )
    intent.limits.max_total_output_chars = 90
    monkeypatch.setattr("src.bridge.runtime.git_status", lambda _cwd: "clean")
    r1 = run_bridge_v0(assembly, intent)
    r2 = run_bridge_v0(assembly, intent)
    out1 = [(c.stdout, c.stderr, c.stdout_truncated, c.stderr_truncated) for c in r1.commands]
    out2 = [(c.stdout, c.stderr, c.stdout_truncated, c.stderr_truncated) for c in r2.commands]
    assert out1 == out2


def test_mutation_detected_false_when_git_status_unchanged(tmp_path, monkeypatch):
    assembly = _FakeAssembly(droid_executor=lambda *_a, **_k: _record(["python"], exit_code=0))
    intent = _intent(
        tmp_path,
        [CommandSpec(command_id="c1", argv=["python", "-c", "print('ok')"], working_dir=str(tmp_path))],
    )
    monkeypatch.setattr("src.bridge.runtime.git_status", lambda _cwd: "clean")
    result = run_bridge_v0(assembly, intent)
    assert result.mutation_detected is False


def test_mutation_detected_true_when_git_status_changes(tmp_path, monkeypatch):
    assembly = _FakeAssembly(droid_executor=lambda *_a, **_k: _record(["python"], exit_code=0))
    intent = _intent(
        tmp_path,
        [CommandSpec(command_id="c1", argv=["python", "-c", "print('ok')"], working_dir=str(tmp_path))],
    )
    calls = {"n": 0}

    def fake_git_status(_cwd):
        calls["n"] += 1
        return "clean" if calls["n"] == 1 else "changed"

    monkeypatch.setattr("src.bridge.runtime.git_status", fake_git_status)
    result = run_bridge_v0(assembly, intent)
    assert result.mutation_detected is True


def test_mutation_detected_none_when_git_status_unavailable(tmp_path, monkeypatch):
    assembly = _FakeAssembly(droid_executor=lambda *_a, **_k: _record(["python"], exit_code=0))
    intent = _intent(
        tmp_path,
        [CommandSpec(command_id="c1", argv=["python", "-c", "print('ok')"], working_dir=str(tmp_path))],
    )
    monkeypatch.setattr("src.bridge.runtime.git_status", lambda _cwd: None)
    result = run_bridge_v0(assembly, intent)
    assert result.mutation_detected is None

