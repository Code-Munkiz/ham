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
