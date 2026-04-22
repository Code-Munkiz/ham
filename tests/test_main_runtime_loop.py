from __future__ import annotations

import json
from dataclasses import dataclass

import main as main_mod
import src.ham.run_persist as run_persist_mod
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
    critic_backstory: str = "critic-context-initial"


def _parse_runtime_stdout(stdout: str) -> dict:
    """Parse RUNTIME_RESULT payload (compact one-line or pretty-printed multiline)."""
    marker = "RUNTIME_RESULT:"
    idx = stdout.find(marker)
    assert idx >= 0, stdout
    rest = stdout[idx + len(marker) :].strip()
    return json.loads(rest)


def _bridge_result(*, mutation_detected: bool | None = False) -> BridgeResult:
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
        mutation_detected=mutation_detected,
    )


def test_main_normal_path_builds_intent_and_invokes_bridge_and_review(monkeypatch, capsys):
    seen: dict[str, object] = {}
    counts = {"bridge": 0, "review": 0}

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-only-fake-key-000000000")
    monkeypatch.setattr(
        main_mod,
        "assemble_ham_run",
        lambda prompt, project_root=None: _FakeAssembly(user_prompt=prompt),
    )

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
    assert "RUNTIME_RESULT:" in out
    payload = _parse_runtime_stdout(out)
    assert set(payload.keys()) == {
        "bridge_result",
        "hermes_review",
        "intent_profile_id",
        "prompt_summary",
    }
    assert set(payload["bridge_result"].keys()) >= {"intent_id", "request_id", "run_id", "status", "commands"}
    assert set(payload["hermes_review"].keys()) == {"ok", "notes", "code", "context"}


def test_main_reviewer_failure_does_not_break_primary_artifact(monkeypatch, capsys):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-only-fake-key-000000000")
    monkeypatch.setattr(
        main_mod,
        "assemble_ham_run",
        lambda prompt, project_root=None: _FakeAssembly(user_prompt=prompt),
    )
    monkeypatch.setattr(main_mod, "run_bridge_v0", lambda _assembly, _intent: _bridge_result())

    class _BoomReviewer:
        def evaluate(self, _code: str, _context: str | None = None):
            raise RuntimeError("review crashed")

    monkeypatch.setattr(main_mod, "HermesReviewer", _BoomReviewer)

    rc = main_mod.main(["do thing"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = _parse_runtime_stdout(out)
    assert set(payload["bridge_result"].keys()) >= {"intent_id", "request_id", "run_id", "status", "commands"}
    assert payload["hermes_review"]["ok"] is False


def test_main_output_shape_is_deterministic(monkeypatch, capsys):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-only-fake-key-000000000")
    monkeypatch.setattr(
        main_mod,
        "assemble_ham_run",
        lambda prompt, project_root=None: _FakeAssembly(user_prompt=prompt),
    )
    monkeypatch.setattr(main_mod, "run_bridge_v0", lambda _assembly, _intent: _bridge_result())

    class _FakeReviewer:
        def evaluate(self, _code: str, _context: str | None = None):
            return {"ok": True, "notes": [], "code": "a", "context": "b"}

    monkeypatch.setattr(main_mod, "HermesReviewer", _FakeReviewer)

    rc = main_mod.main(["determinism"])
    out = capsys.readouterr().out
    assert rc == 0

    payload = _parse_runtime_stdout(out)
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


def test_main_no_mutation_signal_does_not_refresh_context(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-only-fake-key-000000000")
    calls = {"assemble": 0}

    def fake_assemble(prompt: str, project_root=None):
        calls["assemble"] += 1
        return _FakeAssembly(user_prompt=prompt, critic_backstory="critic-context-initial")

    class _FakeReviewer:
        def evaluate(self, _code: str, context: str | None = None):
            return {"ok": True, "notes": [], "code": "x", "context": context}

    monkeypatch.setattr(main_mod, "assemble_ham_run", fake_assemble)
    monkeypatch.setattr(
        main_mod,
        "run_bridge_v0",
        lambda _assembly, _intent: _bridge_result(mutation_detected=None),
    )
    monkeypatch.setattr(main_mod, "HermesReviewer", _FakeReviewer)

    rc = main_mod.main(["no refresh"])
    assert rc == 0
    assert calls["assemble"] == 1


def test_main_confident_mutation_refreshes_exactly_once_and_reviewer_uses_refreshed_context(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-only-fake-key-000000000")
    calls = {"assemble": 0}
    seen: dict[str, object] = {}

    def fake_assemble(prompt: str, project_root=None):
        calls["assemble"] += 1
        if calls["assemble"] == 1:
            return _FakeAssembly(user_prompt=prompt, critic_backstory="critic-context-initial")
        return _FakeAssembly(user_prompt=prompt, critic_backstory="critic-context-refreshed")

    class _FakeReviewer:
        def evaluate(self, _code: str, context: str | None = None):
            seen["context"] = context
            return {"ok": True, "notes": [], "code": "x", "context": "y"}

    monkeypatch.setattr(main_mod, "assemble_ham_run", fake_assemble)
    monkeypatch.setattr(
        main_mod,
        "run_bridge_v0",
        lambda _assembly, _intent: _bridge_result(mutation_detected=True),
    )
    monkeypatch.setattr(main_mod, "HermesReviewer", _FakeReviewer)

    rc = main_mod.main(["refresh once"])
    assert rc == 0
    assert calls["assemble"] == 2
    assert seen["context"] == "critic-context-refreshed"


def test_selector_chooses_git_status_profile(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-only-fake-key-000000000")
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        main_mod,
        "assemble_ham_run",
        lambda prompt, project_root=None: _FakeAssembly(user_prompt=prompt),
    )

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
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-only-fake-key-000000000")
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        main_mod,
        "assemble_ham_run",
        lambda prompt, project_root=None: _FakeAssembly(user_prompt=prompt),
    )

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
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-only-fake-key-000000000")
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        main_mod,
        "assemble_ham_run",
        lambda prompt, project_root=None: _FakeAssembly(user_prompt=prompt),
    )

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


def test_selector_does_not_match_diff_substring_in_different(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-only-fake-key-000000000")
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        main_mod,
        "assemble_ham_run",
        lambda prompt, project_root=None: _FakeAssembly(user_prompt=prompt),
    )

    def fake_bridge(_assembly, intent):
        seen["intent"] = intent
        return _bridge_result()

    class _FakeReviewer:
        def evaluate(self, _code: str, _context: str | None = None):
            return {"ok": True, "notes": [], "code": "x", "context": "y"}

    monkeypatch.setattr(main_mod, "run_bridge_v0", fake_bridge)
    monkeypatch.setattr(main_mod, "HermesReviewer", _FakeReviewer)
    rc = main_mod.main(["show me a different view"])
    assert rc == 0
    intent = seen["intent"]
    assert len(intent.commands) == 1
    assert intent.commands[0].argv == ["python", "-c", "import os; print(os.getcwd())"]
    assert intent.scope.allow_write is False
    assert intent.scope.allow_network is False


def test_selector_does_not_match_diff_substring_in_difficult(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-only-fake-key-000000000")
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        main_mod,
        "assemble_ham_run",
        lambda prompt, project_root=None: _FakeAssembly(user_prompt=prompt),
    )

    def fake_bridge(_assembly, intent):
        seen["intent"] = intent
        return _bridge_result()

    class _FakeReviewer:
        def evaluate(self, _code: str, _context: str | None = None):
            return {"ok": True, "notes": [], "code": "x", "context": "y"}

    monkeypatch.setattr(main_mod, "run_bridge_v0", fake_bridge)
    monkeypatch.setattr(main_mod, "HermesReviewer", _FakeReviewer)
    rc = main_mod.main(["this is a difficult task"])
    assert rc == 0
    intent = seen["intent"]
    assert len(intent.commands) == 1
    assert intent.commands[0].argv == ["python", "-c", "import os; print(os.getcwd())"]
    assert intent.scope.allow_write is False
    assert intent.scope.allow_network is False


def test_selector_precedence_status_wins_over_diff(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-only-fake-key-000000000")
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        main_mod,
        "assemble_ham_run",
        lambda prompt, project_root=None: _FakeAssembly(user_prompt=prompt),
    )

    def fake_bridge(_assembly, intent):
        seen["intent"] = intent
        return _bridge_result()

    class _FakeReviewer:
        def evaluate(self, _code: str, _context: str | None = None):
            return {"ok": True, "notes": [], "code": "x", "context": "y"}

    monkeypatch.setattr(main_mod, "run_bridge_v0", fake_bridge)
    monkeypatch.setattr(main_mod, "HermesReviewer", _FakeReviewer)
    rc = main_mod.main(["diff against status"])
    assert rc == 0
    intent = seen["intent"]
    assert len(intent.commands) == 1
    assert intent.commands[0].argv == ["git", "status", "--short"]
    assert intent.scope.allow_write is False
    assert intent.scope.allow_network is False


def test_persist_creates_file_in_ham_runs_with_expected_keys(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-only-fake-key-000000000")
    monkeypatch.setattr(
        main_mod,
        "assemble_ham_run",
        lambda prompt, project_root=None: _FakeAssembly(user_prompt=prompt),
    )
    monkeypatch.setattr(main_mod, "run_bridge_v0", lambda _assembly, _intent: _bridge_result())

    class _FakeReviewer:
        def evaluate(self, _code: str, _context: str | None = None):
            return {"ok": True, "notes": [], "code": "x", "context": "y"}

    monkeypatch.setattr(main_mod, "HermesReviewer", _FakeReviewer)

    rc = main_mod.main(["persist me"])
    assert rc == 0

    runs_dir = tmp_path / ".ham" / "runs"
    files = list(runs_dir.glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert {
        "run_id",
        "created_at",
        "profile_id",
        "profile_version",
        "backend_id",
        "backend_version",
        "prompt_summary",
        "bridge_result",
        "hermes_review",
    }.issubset(payload.keys())
    assert payload["created_at"].endswith("Z")
    assert payload["run_id"] == payload["bridge_result"]["run_id"]
    assert payload["backend_id"] == "local.droid"
    assert payload["backend_version"] == "1.0.0"


def test_persisted_record_contains_author_from_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-only-fake-key-000000000")
    monkeypatch.setenv("HAM_AUTHOR", "alice")
    monkeypatch.setattr(
        main_mod,
        "assemble_ham_run",
        lambda prompt, project_root=None: _FakeAssembly(user_prompt=prompt),
    )
    monkeypatch.setattr(main_mod, "run_bridge_v0", lambda _assembly, _intent: _bridge_result())

    class _FakeReviewer:
        def evaluate(self, _code: str, _context: str | None = None):
            return {"ok": True, "notes": [], "code": "x", "context": "y"}

    monkeypatch.setattr(main_mod, "HermesReviewer", _FakeReviewer)

    rc = main_mod.main(["show cwd"])
    assert rc == 0

    runs_dir = tmp_path / ".ham" / "runs"
    files = list(runs_dir.glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["author"] == "alice"


def test_persist_failure_does_not_break_runtime(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-only-fake-key-000000000")
    monkeypatch.setattr(
        main_mod,
        "assemble_ham_run",
        lambda prompt, project_root=None: _FakeAssembly(user_prompt=prompt),
    )
    monkeypatch.setattr(main_mod, "run_bridge_v0", lambda _assembly, _intent: _bridge_result())

    class _FakeReviewer:
        def evaluate(self, _code: str, _context: str | None = None):
            return {"ok": True, "notes": [], "code": "x", "context": "y"}

    def boom_replace(_src, _dst):
        raise OSError("disk full")

    monkeypatch.setattr(main_mod, "HermesReviewer", _FakeReviewer)
    monkeypatch.setattr(run_persist_mod.os, "replace", boom_replace)

    rc = main_mod.main(["persist failure"])
    captured = capsys.readouterr()
    assert rc == 0
    envelope = _parse_runtime_stdout(captured.out)
    assert set(envelope.keys()) == {
        "bridge_result",
        "hermes_review",
        "intent_profile_id",
        "prompt_summary",
    }
    assert "run persistence failed" in captured.err.lower()


def test_envelope_shape_unchanged_after_persistence_slice(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-hamtests-only-fake-key-000000000")
    monkeypatch.setattr(
        main_mod,
        "assemble_ham_run",
        lambda prompt, project_root=None: _FakeAssembly(user_prompt=prompt),
    )
    monkeypatch.setattr(main_mod, "run_bridge_v0", lambda _assembly, _intent: _bridge_result())

    class _FakeReviewer:
        def evaluate(self, _code: str, _context: str | None = None):
            return {"ok": True, "notes": [], "code": "a", "context": "b"}

    monkeypatch.setattr(main_mod, "HermesReviewer", _FakeReviewer)

    rc = main_mod.main(["shape freeze"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = _parse_runtime_stdout(out)
    assert set(payload.keys()) == {
        "bridge_result",
        "hermes_review",
        "intent_profile_id",
        "prompt_summary",
    }

