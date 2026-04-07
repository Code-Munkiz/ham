from __future__ import annotations

import json
from dataclasses import dataclass

import main as main_mod
from src.bridge.contracts import (
    BridgeResult,
    BridgeStatus,
    CommandEvidence,
    CommandState,
    ExecutionIntent,
    PolicyDecision,
)


@dataclass
class _FakeAssembly:
    user_prompt: str
    droid_executor: object = object()


def _bridge_result() -> BridgeResult:
    return BridgeResult(
        intent_id="intent-1",
        request_id="request-1",
        run_id="run-1",
        status=BridgeStatus.EXECUTED,
        policy_decision=PolicyDecision(
            accepted=True,
            reasons=[],
            policy_version="bridge-v0",
        ),
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T00:00:01Z",
        duration_ms=1000,
        commands=[
            CommandEvidence(
                command_id="cmd-1",
                argv=["python", "-c", "print('ok')"],
                working_dir=".",
                status=CommandState.EXECUTED,
                exit_code=0,
                timed_out=False,
                stdout="ok",
                stderr="",
                stdout_truncated=False,
                stderr_truncated=False,
                started_at="2026-01-01T00:00:00Z",
                ended_at="2026-01-01T00:00:01Z",
                duration_ms=1000,
            )
        ],
        summary="ok",
    )


def test_main_normal_path_builds_intent_and_invokes_bridge_and_review(monkeypatch, capsys):
    seen: dict[str, object] = {}
    counts = {"bridge": 0, "review": 0}

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(main_mod, "assemble_ham_run", lambda prompt: _FakeAssembly(user_prompt=prompt))

    def fake_bridge(assembly, intent):
        counts["bridge"] += 1
        seen["assembly"] = assembly
        seen["intent"] = intent
        return _bridge_result()

    class _FakeReviewer:
        def evaluate(self, code: str, context: str | None = None):
            counts["review"] += 1
            seen["review_code"] = code
            seen["review_context"] = context
            return {"ok": True, "notes": [], "code": "x", "context": "y"}

    monkeypatch.setattr(main_mod, "run_bridge_v0", fake_bridge)
    monkeypatch.setattr(main_mod, "HermesReviewer", _FakeReviewer)

    rc = main_mod.main(["do thing"])
    out = capsys.readouterr().out

    assert rc == 0
    assert isinstance(seen["intent"], ExecutionIntent)
    intent = seen["intent"]
    assert intent.task_class == "inspect"
    assert len(intent.commands) == 1
    assert intent.scope.allow_write is False
    assert intent.scope.allow_network is False
    assert "review_code" in seen
    assert "review_context" in seen
    assert counts["bridge"] == 1
    assert counts["review"] == 1
    lines = [line for line in out.splitlines() if line.startswith("RUNTIME_RESULT:")]
    assert len(lines) == 1
    payload = json.loads(lines[0].split(":", 1)[1].strip())
    assert set(payload.keys()) == {
        "bridge_result",
        "hermes_review",
        "intent_profile_id",
        "prompt_summary",
    }
    assert set(payload["bridge_result"].keys()) >= {"intent_id", "request_id", "run_id", "status", "commands"}
    assert set(payload["hermes_review"].keys()) == {"ok", "notes", "code", "context"}


def test_main_reviewer_failure_does_not_break_primary_artifact(monkeypatch, capsys):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(main_mod, "assemble_ham_run", lambda prompt: _FakeAssembly(user_prompt=prompt))
    monkeypatch.setattr(main_mod, "run_bridge_v0", lambda _assembly, _intent: _bridge_result())

    class _BoomReviewer:
        def evaluate(self, _code: str, _context: str | None = None):
            raise RuntimeError("review crashed")

    monkeypatch.setattr(main_mod, "HermesReviewer", _BoomReviewer)

    rc = main_mod.main(["do thing"])
    out = capsys.readouterr().out
    assert rc == 0
    line = next(line for line in out.splitlines() if line.startswith("RUNTIME_RESULT:"))
    payload = json.loads(line.split(":", 1)[1].strip())
    assert set(payload["bridge_result"].keys()) >= {"intent_id", "request_id", "run_id", "status", "commands"}
    assert payload["hermes_review"]["ok"] is False


def test_main_output_shape_is_deterministic(monkeypatch, capsys):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(main_mod, "assemble_ham_run", lambda prompt: _FakeAssembly(user_prompt=prompt))
    monkeypatch.setattr(main_mod, "run_bridge_v0", lambda _assembly, _intent: _bridge_result())

    class _FakeReviewer:
        def evaluate(self, _code: str, _context: str | None = None):
            return {"ok": True, "notes": [], "code": "a", "context": "b"}

    monkeypatch.setattr(main_mod, "HermesReviewer", _FakeReviewer)

    rc = main_mod.main(["determinism"])
    out = capsys.readouterr().out
    assert rc == 0

    line = next(line for line in out.splitlines() if line.startswith("RUNTIME_RESULT:"))
    payload = json.loads(line.split(":", 1)[1].strip())
    assert set(payload.keys()) == {
        "bridge_result",
        "hermes_review",
        "intent_profile_id",
        "prompt_summary",
    }
    bridge = payload["bridge_result"]
    review = payload["hermes_review"]
    assert set(bridge.keys()) >= {"intent_id", "request_id", "run_id", "status", "commands"}
    assert set(review.keys()) == {"code", "context", "notes", "ok"}


def test_selector_chooses_git_status_profile(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    seen: dict[str, object] = {}
    monkeypatch.setattr(main_mod, "assemble_ham_run", lambda prompt: _FakeAssembly(user_prompt=prompt))

    def fake_bridge(_assembly, intent):
        seen["intent"] = intent
        return _bridge_result()

    class _FakeReviewer:
        def evaluate(self, _code: str, _context: str | None = None):
            return {"ok": True, "notes": [], "code": "x", "context": "y"}

    monkeypatch.setattr(main_mod, "run_bridge_v0", fake_bridge)
    monkeypatch.setattr(main_mod, "HermesReviewer", _FakeReviewer)
    rc = main_mod.main(["show status"])
    assert rc == 0
    intent = seen["intent"]
    assert len(intent.commands) == 1
    assert intent.commands[0].argv == ["git", "status", "--short"]
    assert intent.scope.allow_write is False
    assert intent.scope.allow_network is False


def test_selector_chooses_git_diff_profile(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    seen: dict[str, object] = {}
    monkeypatch.setattr(main_mod, "assemble_ham_run", lambda prompt: _FakeAssembly(user_prompt=prompt))

    def fake_bridge(_assembly, intent):
        seen["intent"] = intent
        return _bridge_result()

    class _FakeReviewer:
        def evaluate(self, _code: str, _context: str | None = None):
            return {"ok": True, "notes": [], "code": "x", "context": "y"}

    monkeypatch.setattr(main_mod, "run_bridge_v0", fake_bridge)
    monkeypatch.setattr(main_mod, "HermesReviewer", _FakeReviewer)
    rc = main_mod.main(["show me diff"])
    assert rc == 0
    intent = seen["intent"]
    assert len(intent.commands) == 1
    assert intent.commands[0].argv == ["git", "diff", "--name-only"]
    assert intent.scope.allow_write is False
    assert intent.scope.allow_network is False


def test_selector_falls_back_to_cwd_profile(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    seen: dict[str, object] = {}
    monkeypatch.setattr(main_mod, "assemble_ham_run", lambda prompt: _FakeAssembly(user_prompt=prompt))

    def fake_bridge(_assembly, intent):
        seen["intent"] = intent
        return _bridge_result()

    class _FakeReviewer:
        def evaluate(self, _code: str, _context: str | None = None):
            return {"ok": True, "notes": [], "code": "x", "context": "y"}

    monkeypatch.setattr(main_mod, "run_bridge_v0", fake_bridge)
    monkeypatch.setattr(main_mod, "HermesReviewer", _FakeReviewer)
    rc = main_mod.main(["hello runtime"])
    assert rc == 0
    intent = seen["intent"]
    assert len(intent.commands) == 1
    assert intent.commands[0].argv == ["python", "-c", "import os; print(os.getcwd())"]

