"""Unit tests for ``src.ham.claude_agent_runner.runner``.

All ``claude_agent_sdk`` symbol access is mocked through the ``_import_*``
indirection seams. These tests never require the real SDK, never invoke
a subprocess, never reach Anthropic, and never reference a real secret.

Canary values used in env fixtures are obviously fake (``claude-agent-test-
canary-not-a-real-key``) so the secret scanner stays quiet on push.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.ham.claude_agent_runner import (
    ClaudeAgentPermissionPolicy,
    make_list_audit_sink,
    run_claude_agent_mission,
)
from src.ham.claude_agent_runner import runner as runner_module
from src.ham.claude_agent_runner.types import ClaudeAgentRunResult


# ---------------------------------------------------------------------------
# Fake SDK plumbing
# ---------------------------------------------------------------------------


class _FakeOptions:
    """Stand-in for ``ClaudeAgentOptions`` — stores kwargs as attributes."""

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeHookMatcher:
    def __init__(self, matcher: str = "", hooks: list[Any] | None = None) -> None:
        self.matcher = matcher
        self.hooks = hooks or []


class _FakePermissionAllow:
    def __init__(self, updated_input: Any = None) -> None:
        self.behavior = "allow"
        self.updated_input = updated_input


class _FakePermissionDeny:
    def __init__(self, *, message: str = "", interrupt: bool = False) -> None:
        self.behavior = "deny"
        self.message = message
        self.interrupt = interrupt


def _make_fake_client_cls(action: Any) -> type:
    """Return a class mimicking ``ClaudeSDKClient`` for the runner.

    ``action`` is an async callback ``async def action(options, messages, prompt)``
    that the fake session invokes inside ``session.query()`` to populate
    ``messages`` (consumed by ``session.receive_response()``) and to simulate
    the SDK calling hooks / ``can_use_tool``.
    """

    class _FakeClient:
        def __init__(self, options: Any = None) -> None:
            self.options = options
            self._messages: list[Any] = []

        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(self, *_exc: Any) -> None:
            return None

        async def query(self, prompt: str) -> None:
            if action is not None:
                await action(self.options, self._messages, prompt)

        async def receive_response(self):  # type: ignore[no-untyped-def]
            for m in self._messages:
                yield m

    return _FakeClient


def _patch_sdk_seams(action: Any) -> Any:
    """Context manager that patches every SDK import seam used by the runner."""

    return _SdkSeamPatchCtx(action)


class _SdkSeamPatchCtx:
    def __init__(self, action: Any) -> None:
        self._action = action
        self._patches: list[Any] = []
        self.client_spy: MagicMock | None = None

    def __enter__(self) -> "_SdkSeamPatchCtx":
        client_cls = _make_fake_client_cls(self._action)
        self.client_spy = MagicMock(return_value=client_cls)
        self._patches.append(patch.object(runner_module, "_import_client", self.client_spy))
        self._patches.append(patch.object(runner_module, "_import_options", lambda: _FakeOptions))
        self._patches.append(
            patch.object(runner_module, "_import_hook_matcher", lambda: _FakeHookMatcher)
        )
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        for p in reversed(self._patches):
            p.stop()


def _make_policy(project_root: Path) -> ClaudeAgentPermissionPolicy:
    return ClaudeAgentPermissionPolicy(project_root=project_root)


def _patch_permission_classes() -> Any:
    """Patch the permissions module to return fake Allow/Deny classes."""

    from src.ham.claude_agent_runner import permissions as permissions_module

    return patch.object(
        permissions_module,
        "_import_permission_results",
        lambda: (_FakePermissionAllow, _FakePermissionDeny),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_runner_returns_sdk_missing_when_sdk_not_installed(tmp_path: Path) -> None:
    policy = _make_policy(tmp_path)
    with patch.object(runner_module, "_import_client", side_effect=ImportError("not installed")):
        result = asyncio.run(
            run_claude_agent_mission(
                project_root=tmp_path,
                user_prompt="do something",
                policy=policy,
            )
        )
    assert isinstance(result, ClaudeAgentRunResult)
    assert result.status == "sdk_missing"
    assert result.error_kind == "ImportError"
    assert isinstance(result.error_summary, str) and result.error_summary
    assert "sk-ant" not in (result.error_summary or "")
    assert "ANTHROPIC_API_KEY" not in (result.error_summary or "")
    assert result.duration_seconds >= 0.0


def test_runner_returns_timeout_when_sdk_blocks(tmp_path: Path) -> None:
    async def _hang(_options: Any, _messages: list[Any], _prompt: str) -> None:
        # Never returns — will be cut off by patched asyncio.wait_for.
        await asyncio.sleep(3600)

    policy = _make_policy(tmp_path)
    with _patch_sdk_seams(_hang):
        with patch.object(
            runner_module.asyncio,
            "wait_for",
            side_effect=TimeoutError("forced timeout"),
        ):
            result = asyncio.run(
                run_claude_agent_mission(
                    project_root=tmp_path,
                    user_prompt="do something",
                    policy=policy,
                )
            )
    assert result.status == "timeout"
    assert result.error_kind == "TimeoutError"
    assert result.duration_seconds >= 0.0


def test_runner_returns_success_when_sdk_yields_messages(tmp_path: Path) -> None:
    async def _ok(_options: Any, messages: list[Any], _prompt: str) -> None:
        messages.append(SimpleNamespace(content=[SimpleNamespace(text="done.")]))
        messages.append(SimpleNamespace(stop_reason="end_turn", total_cost_usd=0.001))

    policy = _make_policy(tmp_path)
    with _patch_sdk_seams(_ok):
        result = asyncio.run(
            run_claude_agent_mission(
                project_root=tmp_path,
                user_prompt="do something",
                policy=policy,
            )
        )
    assert result.status == "success"
    assert "done." in (result.assistant_summary or "")
    assert result.cost_usd == pytest.approx(0.001)


def test_runner_tracks_changed_paths_from_post_tool_use_audit(tmp_path: Path) -> None:
    edited_path = tmp_path / "a.txt"
    edited_path.write_text("hello", encoding="utf-8")

    async def _edit(options: Any, messages: list[Any], _prompt: str) -> None:
        post = options.hooks["PostToolUse"][0].hooks[0]
        await post(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(edited_path)},
                "tool_result_status": "ok",
            },
            None,
            None,
        )
        messages.append(SimpleNamespace(content=[SimpleNamespace(text="edited.")]))

    policy = _make_policy(tmp_path)
    with _patch_sdk_seams(_edit), _patch_permission_classes():
        result = asyncio.run(
            run_claude_agent_mission(
                project_root=tmp_path,
                user_prompt="edit one file",
                policy=policy,
            )
        )
    assert result.status == "success"
    resolved = str(edited_path.resolve())
    assert resolved in result.changed_paths


def test_runner_blocks_path_outside_project_root_via_hook(tmp_path: Path) -> None:
    async def _attempt(options: Any, _messages: list[Any], _prompt: str) -> None:
        pre = options.hooks["PreToolUse"][0].hooks[0]
        await pre(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/etc/passwd"},
            },
            None,
            None,
        )

    sink, events = make_list_audit_sink()
    policy = _make_policy(tmp_path)
    with _patch_sdk_seams(_attempt), _patch_permission_classes():
        result = asyncio.run(
            run_claude_agent_mission(
                project_root=tmp_path,
                user_prompt="rm -rf",
                policy=policy,
                audit_sink=sink,
            )
        )
    assert result.denied_tool_calls_count >= 1
    kinds = [e.kind for e in events]
    assert "denied_path" in kinds


def test_runner_blocks_disallowed_tool_via_can_use_tool(tmp_path: Path) -> None:
    async def _attempt(options: Any, _messages: list[Any], _prompt: str) -> None:
        can_use = options.can_use_tool
        outcome = await can_use("Bash", {"command": "ls"}, None)
        assert isinstance(outcome, _FakePermissionDeny), outcome

    sink, events = make_list_audit_sink()
    policy = _make_policy(tmp_path)
    with _patch_sdk_seams(_attempt), _patch_permission_classes():
        result = asyncio.run(
            run_claude_agent_mission(
                project_root=tmp_path,
                user_prompt="run shell",
                policy=policy,
                audit_sink=sink,
            )
        )
    assert result.denied_tool_calls_count >= 1
    kinds = [e.kind for e in events]
    assert "denied_tool" in kinds


def test_runner_redacts_secret_shaped_assistant_text(tmp_path: Path) -> None:
    fake_secret = "ANTHROPIC_API_KEY=claude-agent-test-canary-not-a-real-key"

    async def _leak(_options: Any, messages: list[Any], _prompt: str) -> None:
        messages.append(
            SimpleNamespace(
                content=[
                    SimpleNamespace(text=f"here is a fake key: {fake_secret}"),
                ]
            )
        )

    policy = _make_policy(tmp_path)
    with _patch_sdk_seams(_leak):
        result = asyncio.run(
            run_claude_agent_mission(
                project_root=tmp_path,
                user_prompt="anything",
                policy=policy,
            )
        )
    assert fake_secret not in (result.assistant_summary or "")


def test_runner_records_sdk_version(tmp_path: Path) -> None:
    async def _ok(_options: Any, messages: list[Any], _prompt: str) -> None:
        messages.append(SimpleNamespace(content=[SimpleNamespace(text="ok")]))

    policy = _make_policy(tmp_path)
    with (
        _patch_sdk_seams(_ok),
        patch.object(runner_module, "_import_sdk_version", lambda: "0.1.99"),
    ):
        result = asyncio.run(
            run_claude_agent_mission(
                project_root=tmp_path,
                user_prompt="hi",
                policy=policy,
            )
        )
    assert result.sdk_version == "0.1.99"


def test_runner_never_raises_on_unexpected_error(tmp_path: Path) -> None:
    policy = _make_policy(tmp_path)
    with patch.object(runner_module, "_import_client", side_effect=RuntimeError("boom")):
        result = asyncio.run(
            run_claude_agent_mission(
                project_root=tmp_path,
                user_prompt="anything",
                policy=policy,
            )
        )
    assert result.status == "sdk_error"
    assert result.error_kind == "RuntimeError"
    assert isinstance(result.error_summary, str) and result.error_summary
    assert "sk-ant" not in (result.error_summary or "")
    assert "ANTHROPIC_API_KEY" not in (result.error_summary or "")


def test_runner_uses_claude_sdk_client_not_query(tmp_path: Path) -> None:
    async def _ok(_options: Any, messages: list[Any], _prompt: str) -> None:
        messages.append(SimpleNamespace(content=[SimpleNamespace(text="ok")]))

    policy = _make_policy(tmp_path)
    with _patch_sdk_seams(_ok) as ctx:
        asyncio.run(
            run_claude_agent_mission(
                project_root=tmp_path,
                user_prompt="hi",
                policy=policy,
            )
        )
    assert ctx.client_spy is not None
    assert ctx.client_spy.call_count >= 1


def test_runner_rejects_bypass_permissions_policy_at_construction(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError):
        ClaudeAgentPermissionPolicy(project_root=tmp_path, permission_mode="bypassPermissions")


def test_runner_audit_sink_failure_does_not_break_run(tmp_path: Path) -> None:
    async def _ok(_options: Any, messages: list[Any], _prompt: str) -> None:
        messages.append(SimpleNamespace(content=[SimpleNamespace(text="ok")]))

    async def _bad_sink(_event: Any) -> None:
        raise RuntimeError("audit sink broken")

    policy = _make_policy(tmp_path)
    with _patch_sdk_seams(_ok):
        result = asyncio.run(
            run_claude_agent_mission(
                project_root=tmp_path,
                user_prompt="hi",
                policy=policy,
                audit_sink=_bad_sink,
            )
        )
    assert result.status == "success"


def test_runner_changed_paths_capped(tmp_path: Path) -> None:
    async def _many_edits(options: Any, messages: list[Any], _prompt: str) -> None:
        post = options.hooks["PostToolUse"][0].hooks[0]
        for i in range(300):
            target = tmp_path / f"file_{i}.txt"
            await post(
                {
                    "tool_name": "Edit",
                    "tool_input": {"file_path": str(target)},
                    "tool_result_status": "ok",
                },
                None,
                None,
            )
        messages.append(SimpleNamespace(content=[SimpleNamespace(text="done")]))

    policy = _make_policy(tmp_path)
    with _patch_sdk_seams(_many_edits), _patch_permission_classes():
        result = asyncio.run(
            run_claude_agent_mission(
                project_root=tmp_path,
                user_prompt="edit lots",
                policy=policy,
            )
        )
    assert len(result.changed_paths) <= runner_module.MAX_CHANGED_PATHS
