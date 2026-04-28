from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.bridge.contracts import BrowserIntent, BrowserPolicySpec, BrowserRunStatus, BrowserStepSpec
from src.bridge.browser_runtime import run_browser_v0


@dataclass
class _FakeAssembly:
    browser_executor: Any


def _intent() -> BrowserIntent:
    return BrowserIntent(
        intent_id="intent-browser-1",
        request_id="request-browser-1",
        run_id="run-browser-1",
        steps=[
            BrowserStepSpec(step_id="s1", action="navigate", args={"url": "https://example.com"}),
            BrowserStepSpec(step_id="s2", action="extract_text", args={"selector": "main"}),
        ],
        policy=BrowserPolicySpec(
            max_steps=5,
            step_timeout_ms=8_000,
            max_dom_chars=256,
            max_console_chars=128,
            max_network_events=5,
            allowed_domains=[],
            allow_file_download=False,
            allow_form_submit=False,
        ),
        reason="browser runtime test",
    )


def test_browser_runtime_blocked_when_disabled():
    assembly = _FakeAssembly(browser_executor=lambda *_a, **_k: {"status": "executed"})
    result = run_browser_v0(assembly, _intent(), enabled_override=False)
    assert result.status == BrowserRunStatus.BLOCKED
    assert result.policy_decision.accepted is False
    assert result.steps == []


def test_browser_runtime_rejected_by_policy():
    assembly = _FakeAssembly(browser_executor=lambda *_a, **_k: {"status": "executed"})
    intent = _intent()
    intent.steps[0].args["url"] = "file:///etc/passwd"
    result = run_browser_v0(assembly, intent, enabled_override=True)
    assert result.status == BrowserRunStatus.REJECTED
    assert result.policy_decision.accepted is False
    assert result.steps == []


def test_browser_runtime_executes_and_caps_evidence(monkeypatch):
    def fake_exec(step: BrowserStepSpec, *, timeout_ms: int) -> dict[str, Any]:
        _ = timeout_ms
        return {
            "status": "executed",
            "url_before": "https://example.com",
            "url_after": "https://example.com/next",
            "dom_excerpt": "D" * 100,
            "console_errors": ["E" * 100, "ignored"],
            "network_summary": {"ok": 10, "fail": 10},
            "screenshot_path": "artifacts/s1.png",
        }

    assembly = _FakeAssembly(browser_executor=fake_exec)
    monkeypatch.setattr("src.bridge.browser_runtime.git_status", lambda _cwd: "clean")
    result = run_browser_v0(assembly, _intent(), enabled_override=True)
    assert result.status == BrowserRunStatus.EXECUTED
    assert len(result.steps) == 2
    first = result.steps[0]
    assert len(first.dom_excerpt) <= 259  # 256 + possible "..."
    assert sum(len(x) for x in first.console_errors) <= 131  # 128 + possible "..."
    assert sum(first.network_summary.values()) <= 5
    assert result.mutation_detected is False


def test_browser_runtime_partial_when_failure_present(monkeypatch):
    states = ["executed", "failed"]

    def fake_exec(_step: BrowserStepSpec, *, timeout_ms: int) -> dict[str, Any]:
        _ = timeout_ms
        return {"status": states.pop(0), "error": "boom" if states == [] else None}

    assembly = _FakeAssembly(browser_executor=fake_exec)
    monkeypatch.setattr("src.bridge.browser_runtime.git_status", lambda _cwd: "clean")
    result = run_browser_v0(assembly, _intent(), enabled_override=True)
    assert result.status == BrowserRunStatus.PARTIAL


def test_browser_runtime_mutation_signal_true_when_git_changes(monkeypatch):
    calls = {"n": 0}

    def fake_git(_cwd):
        calls["n"] += 1
        return "clean" if calls["n"] == 1 else "changed"

    assembly = _FakeAssembly(browser_executor=lambda *_a, **_k: {"status": "executed"})
    monkeypatch.setattr("src.bridge.browser_runtime.git_status", fake_git)
    result = run_browser_v0(assembly, _intent(), enabled_override=True)
    assert result.status == BrowserRunStatus.EXECUTED
    assert result.mutation_detected is True
