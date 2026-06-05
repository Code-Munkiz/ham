"""Hermes CLI Docker packaging + discovery guards (Native Builder workspace lane)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ham import hermes_runtime_inventory as inv

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DOCKERFILE = _REPO_ROOT / "Dockerfile"


def test_dockerfile_installs_hermes_agent_on_path() -> None:
    text = _DOCKERFILE.read_text(encoding="utf-8")
    assert "HERMES_AGENT_VERSION" in text
    assert "hermes-agent==" in text or 'hermes-agent==${HERMES_AGENT_VERSION}' in text
    assert "command -v hermes" in text
    assert "hermes --version" in text


def test_verify_hermes_cli_image_script_exists() -> None:
    script = _REPO_ROOT / "scripts" / "verify_hermes_cli_image.sh"
    assert script.is_file()
    content = script.read_text(encoding="utf-8")
    assert "resolve_hermes_cli_binary" in content
    assert "hermes --version" in content


def test_resolve_hermes_cli_binary_honors_ham_hermes_cli_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = tmp_path / "hermes"
    fake.write_text("#!/bin/sh\necho fake\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("HAM_HERMES_CLI_PATH", str(fake))
    assert inv.resolve_hermes_cli_binary() == str(fake)


def test_builder_native_hermes_does_not_import_deprecated_artifact_module() -> None:
    import ast

    import src.ham.builder_native_hermes as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any("json_artifact_deprecated" in name for name in imported)


def test_build_hermes_cli_chat_argv_includes_provider_and_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.ham.hermes_workspace_execution import build_hermes_cli_chat_argv

    monkeypatch.setenv("HERMES_NATIVE_WORKSPACE_PROVIDER", "openrouter")
    monkeypatch.setenv("HERMES_NATIVE_WORKSPACE_MODEL", "anthropic/claude-3.5-haiku")
    monkeypatch.delenv("HERMES_NATIVE_WORKSPACE_MAX_TURNS", raising=False)
    argv = build_hermes_cli_chat_argv(binary="/usr/local/bin/hermes", instruction="build app")
    assert argv[:3] == ["/usr/local/bin/hermes", "chat", "-q"]
    assert "--provider" in argv
    assert argv[argv.index("--provider") + 1] == "openrouter"
    assert "-m" in argv
    assert argv[argv.index("-m") + 1] == "anthropic/claude-3.5-haiku"


def test_build_hermes_cli_chat_argv_omits_provider_and_model_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.ham.hermes_workspace_execution import build_hermes_cli_chat_argv

    monkeypatch.delenv("HERMES_NATIVE_WORKSPACE_PROVIDER", raising=False)
    monkeypatch.delenv("HERMES_NATIVE_WORKSPACE_MODEL", raising=False)
    argv = build_hermes_cli_chat_argv(binary="/usr/local/bin/hermes", instruction="build app")
    assert "--provider" not in argv
    assert "-m" not in argv


def test_cli_nonzero_exit_empty_workspace_fails_safely(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from unittest.mock import MagicMock

    import src.ham.hermes_workspace_execution as ws_exec

    monkeypatch.setattr(ws_exec, "resolve_hermes_cli_binary", lambda: "/usr/local/bin/hermes")
    monkeypatch.setattr(
        ws_exec,
        "seed_template_pack_workspace",
        lambda *_a, **_k: None,
    )

    def _failed_run(*_args, **_kwargs):
        m = MagicMock()
        m.returncode = 1
        m.stdout = "Error: provider auth failed\n"
        m.stderr = ""
        return m

    monkeypatch.setattr(ws_exec.subprocess, "run", _failed_run)
    outcome = ws_exec.HermesCliWorkspaceProvider().execute(
        workspace_dir=tmp_path,
        user_prompt="build app",
        import_job_id="ijob_cli_fail",
    )
    assert outcome.ok is False
    assert outcome.error_code == "HERMES_CLI_EMPTY_WORKSPACE"
