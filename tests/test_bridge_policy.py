from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.bridge.contracts import CommandSpec, ExecutionIntent, LimitSpec, ScopeSpec
from src.bridge.policy import validate_intent


def _intent(tmp_path: Path) -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="intent-1",
        request_id="request-1",
        run_id="run-1",
        task_class="inspect",
        commands=[
            CommandSpec(
                command_id="cmd-1",
                argv=["python", "-c", "print('ok')"],
                working_dir=str(tmp_path),
            )
        ],
        scope=ScopeSpec(allowed_roots=[str(tmp_path)]),
        limits=LimitSpec(
            max_commands=1,
            timeout_sec_per_command=5,
            max_stdout_chars=2000,
            max_stderr_chars=2000,
            max_total_output_chars=4000,
        ),
        reason="policy test",
    )


def test_accept_valid_minimal_intent(tmp_path: Path):
    decision = validate_intent(_intent(tmp_path), repo_root=tmp_path)
    assert decision.accepted is True
    assert decision.reasons == []


def test_reject_disallowed_command(tmp_path: Path):
    intent = _intent(tmp_path)
    intent.commands[0].argv = ["curl", "https://example.com"]
    decision = validate_intent(intent, repo_root=tmp_path)
    assert decision.accepted is False
    assert any("denied executable" in r for r in decision.reasons)


def test_reject_path_traversal(tmp_path: Path):
    intent = _intent(tmp_path)
    intent.commands[0].working_dir = str(tmp_path / "..")
    decision = validate_intent(intent, repo_root=tmp_path)
    assert decision.accepted is False
    assert any("escapes allowed scope" in r for r in decision.reasons)


def test_reject_symlink_escape(tmp_path: Path):
    outside = tmp_path.parent / "outside-policy"
    outside.mkdir(exist_ok=True)
    escape_link = tmp_path / "escape"
    try:
        os.symlink(str(outside), str(escape_link), target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation not permitted on this platform")
    intent = _intent(tmp_path)
    intent.commands[0].working_dir = str(escape_link)
    decision = validate_intent(intent, repo_root=tmp_path)
    assert decision.accepted is False
    assert any("escapes allowed scope" in r for r in decision.reasons)


def test_reject_invalid_limits(tmp_path: Path):
    intent = _intent(tmp_path)
    intent.limits.max_commands = 99
    decision = validate_intent(intent, repo_root=tmp_path)
    assert decision.accepted is False
    assert any("max_commands exceeds" in r for r in decision.reasons)


def test_reject_missing_ids(tmp_path: Path):
    intent = _intent(tmp_path).model_copy(update={"request_id": ""})
    decision = validate_intent(intent, repo_root=tmp_path)
    assert decision.accepted is False
    assert any("Missing required correlation IDs" in r for r in decision.reasons)


def test_reject_write_or_network_requests(tmp_path: Path):
    intent = _intent(tmp_path)
    intent.scope.allow_write = True
    intent.scope.allow_network = True
    decision = validate_intent(intent, repo_root=tmp_path)
    assert decision.accepted is False
    assert any("Write access is not allowed" in r for r in decision.reasons)
    assert any("Network access is not allowed" in r for r in decision.reasons)


@pytest.mark.parametrize(
    "argv",
    [
        ["git", "commit", "-m", "x"],
        ["git", "push"],
        ["git", "reset", "--hard"],
        ["git", "clean", "-fd"],
    ],
)
def test_reject_dangerous_git_subcommands(tmp_path: Path, argv: list[str]):
    intent = _intent(tmp_path)
    intent.commands[0].argv = argv
    decision = validate_intent(intent, repo_root=tmp_path)
    assert decision.accepted is False
    assert any("git subcommand" in r.lower() or "allowlist" in r.lower() for r in decision.reasons)


@pytest.mark.parametrize(
    "snippet",
    [
        "open('x.txt','w').write('x')",
        "import socket; socket.socket()",
        "import requests; requests.get('https://example.com')",
    ],
)
def test_reject_suspicious_python_c_patterns(tmp_path: Path, snippet: str):
    intent = _intent(tmp_path)
    intent.commands[0].argv = ["python", "-c", snippet]
    decision = validate_intent(intent, repo_root=tmp_path)
    assert decision.accepted is False
    assert any("python -c" in r.lower() or "allowlist" in r.lower() for r in decision.reasons)


def test_reject_disallowed_env_override_key(tmp_path: Path):
    intent = _intent(tmp_path)
    intent.commands[0].env_overrides = {"AWS_SECRET_ACCESS_KEY": "x"}
    decision = validate_intent(intent, repo_root=tmp_path)
    assert decision.accepted is False
    assert any("env override key" in r.lower() for r in decision.reasons)


def test_reject_suspicious_env_override_payload(tmp_path: Path):
    intent = _intent(tmp_path)
    intent.commands[0].env_overrides = {"PYTHONUTF8": "1\nBAD=1"}
    decision = validate_intent(intent, repo_root=tmp_path)
    assert decision.accepted is False
    assert any("env override value" in r.lower() for r in decision.reasons)


def test_allow_empty_or_approved_env_overrides(tmp_path: Path):
    intent = _intent(tmp_path)
    intent.commands[0].env_overrides = {}
    decision = validate_intent(intent, repo_root=tmp_path)
    assert decision.accepted is True

    intent.commands[0].env_overrides = {"PYTHONUTF8": "1"}
    decision2 = validate_intent(intent, repo_root=tmp_path)
    assert decision2.accepted is True

