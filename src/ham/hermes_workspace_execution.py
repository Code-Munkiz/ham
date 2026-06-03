"""Hermes Native Builder workspace execution providers (filesystem-oriented, not JSON artifacts).

Natural mode: ``hermes chat -q … -Q --yolo`` with ``cwd`` set to an isolated workspace
directory. Hermes uses its file tools iteratively; HAM collects the resulting tree and
materializes via :mod:`src.ham.build_materialization`.

Required operator configuration (host / worker):

- ``HAM_HERMES_NATIVE_WORKSPACE_ENABLED=1`` — enable the native workspace lane.
- ``HAM_HERMES_CLI_PATH`` (optional) — path to ``hermes`` binary; otherwise ``PATH``.
- ``HERMES_NATIVE_WORKSPACE_MAX_TURNS`` (optional) — ``--max-turns`` cap (default 40).
- ``HERMES_NATIVE_WORKSPACE_TIMEOUT_SEC`` (optional) — subprocess budget (default 600).
- ``HAM_HERMES_NATIVE_WORKSPACE_ROOT`` (optional) — parent dir for isolated workspaces.

Hermes must be installed and authenticated (``hermes login`` / provider env) on the
build host. This module never calls :func:`complete_artifact_turn`.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from src.ham.builder_preview_bootstrap import build_vite_bootstrap_files, safe_npm_package_name
from src.ham.hermes_runtime_inventory import redact_paths, redact_secrets, resolve_hermes_cli_binary

_LOG = logging.getLogger(__name__)

_MAX_TURNS_ENV = "HERMES_NATIVE_WORKSPACE_MAX_TURNS"
_TIMEOUT_ENV = "HERMES_NATIVE_WORKSPACE_TIMEOUT_SEC"
_SOURCE_TAG = "ham_native_builder"

_DEFAULT_MAX_TURNS = 40
_DEFAULT_TIMEOUT_SEC = 600.0
_MAX_FILE_BYTES = 200_000
_MAX_TOTAL_BYTES = 400_000
_MAX_FILES = 48

_SKIP_DIR_NAMES = frozenset(
    {
        "node_modules",
        ".git",
        ".hermes",
        "dist",
        "build",
        ".vite",
        "__pycache__",
        ".turbo",
        ".next",
    }
)
_SKIP_FILE_NAMES = frozenset({".env", ".env.local", ".env.production"})


@dataclass(frozen=True)
class WorkspaceExecutionOutcome:
    """Result of a workspace harness run before materialization."""

    ok: bool
    files: dict[str, str] | None = None
    error_code: str | None = None
    error_summary: str | None = None
    session_id: str | None = None
    exit_code: int | None = None


@runtime_checkable
class HermesWorkspaceExecutionProvider(Protocol):
    """Pluggable workspace execution (CLI today; future: HTTP runs with cwd)."""

    def execute(
        self,
        *,
        workspace_dir: Path,
        user_prompt: str,
        import_job_id: str,
    ) -> WorkspaceExecutionOutcome: ...


def _truthy_env(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _max_turns() -> int:
    raw = (os.environ.get(_MAX_TURNS_ENV) or "").strip()
    if not raw:
        return _DEFAULT_MAX_TURNS
    try:
        return max(1, min(120, int(raw)))
    except ValueError:
        return _DEFAULT_MAX_TURNS


def _timeout_sec() -> float:
    raw = (os.environ.get(_TIMEOUT_ENV) or "").strip()
    if not raw:
        return _DEFAULT_TIMEOUT_SEC
    try:
        return max(30.0, min(3600.0, float(raw)))
    except ValueError:
        return _DEFAULT_TIMEOUT_SEC


def _build_instruction_prompt(enriched_user_prompt: str) -> str:
    return (
        "You are HAM Native Builder. Build a small runnable Vite + React + TypeScript web app "
        "in the CURRENT WORKING DIRECTORY only.\n\n"
        "User goal:\n"
        f"{enriched_user_prompt.strip()}\n\n"
        "Requirements:\n"
        "- Use your file and shell tools to create and edit files here (not JSON file bundles).\n"
        "- Include package.json, index.html, vite.config.ts, src/main.tsx, and at least one app component.\n"
        "- Keep the first version compact (about 6–12 source files).\n"
        "- Do not print secrets, env values, registry ids, proposal digests, or base revisions.\n"
        "- When finished, ensure the project can pass TypeScript check (consistent identifiers).\n"
    )


def seed_minimal_vite_workspace(workspace_dir: Path, *, user_prompt: str) -> None:
    """Write bootstrap Vite/React files so Hermes can iterate instead of starting empty."""
    title = (user_prompt or "HAM Builder App")[:80]
    safe_pkg = safe_npm_package_name(title)
    files = build_vite_bootstrap_files(title=title or "HAM Builder App", safe_pkg=safe_pkg)
    files["src/main.tsx"] = (
        "import React from 'react';\n"
        "import ReactDOM from 'react-dom/client';\n"
        "import App from './App';\n"
        "import './styles.css';\n"
        "ReactDOM.createRoot(document.getElementById('root')!).render(\n"
        "  <React.StrictMode>\n"
        "    <App />\n"
        "  </React.StrictMode>,\n"
        ");\n"
    )
    files["src/App.tsx"] = (
        "export default function App() {\n"
        "  return (\n"
        "    <main style={{ fontFamily: 'system-ui, sans-serif', padding: '2rem' }}>\n"
        "      HAM preview scaffold — enhance this app to match the user goal.\n"
        "    </main>\n"
        "  );\n"
        "}\n"
    )
    files["src/styles.css"] = "body { margin: 0; }\n"
    for rel, content in files.items():
        target = workspace_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _should_skip_path(rel: str) -> bool:
    parts = rel.split("/")
    if any(part in _SKIP_DIR_NAMES for part in parts):
        return True
    base = parts[-1] if parts else rel
    if base in _SKIP_FILE_NAMES:
        return True
    if base.startswith(".env."):
        return True
    return False


def collect_workspace_files(workspace_dir: Path) -> dict[str, str]:
    """Collect text files from workspace tree with size caps (no secrets in logs)."""
    if not workspace_dir.is_dir():
        return {}
    out: dict[str, str] = {}
    total = 0
    for file_path in sorted(workspace_dir.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(workspace_dir).as_posix()
        if not rel or ".." in rel.split("/") or _should_skip_path(rel):
            continue
        try:
            size = file_path.stat().st_size
        except OSError:
            continue
        if size > _MAX_FILE_BYTES:
            continue
        try:
            text = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        total += len(text.encode("utf-8"))
        if total > _MAX_TOTAL_BYTES:
            break
        out[rel] = text
        if len(out) >= _MAX_FILES:
            break
    return out


def _parse_session_id_from_output(text: str) -> str | None:
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped.lower().startswith("session_id:"):
            return stripped.split(":", 1)[1].strip() or None
    return None


class HermesCliWorkspaceProvider:
    """Run ``hermes chat`` non-interactively inside the isolated workspace directory."""

    def execute(
        self,
        *,
        workspace_dir: Path,
        user_prompt: str,
        import_job_id: str,
    ) -> WorkspaceExecutionOutcome:
        binary = resolve_hermes_cli_binary()
        if not binary:
            return WorkspaceExecutionOutcome(
                ok=False,
                error_code="HERMES_CLI_UNAVAILABLE",
                error_summary="Hermes CLI binary not found on PATH.",
            )

        seed_minimal_vite_workspace(workspace_dir, user_prompt=user_prompt)
        instruction = _build_instruction_prompt(user_prompt)
        argv = [
            binary,
            "chat",
            "-q",
            instruction,
            "-Q",
            "--yolo",
            "--max-turns",
            str(_max_turns()),
            "--source",
            _SOURCE_TAG,
        ]
        env = os.environ.copy()
        # Hermes inherits provider credentials from the operator home; never log env.
        try:
            proc = subprocess.run(
                argv,
                cwd=workspace_dir,
                capture_output=True,
                text=True,
                timeout=_timeout_sec(),
                env=env,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            _LOG.warning(
                "ham_native_workspace_cli_timeout import_job_id=%s timeout_sec=%s",
                import_job_id,
                _timeout_sec(),
            )
            return WorkspaceExecutionOutcome(
                ok=False,
                error_code="HERMES_CLI_TIMEOUT",
                error_summary="Hermes CLI workspace build timed out.",
            )
        except OSError as exc:
            _LOG.warning(
                "ham_native_workspace_cli_os_error import_job_id=%s err=%s",
                import_job_id,
                type(exc).__name__,
            )
            return WorkspaceExecutionOutcome(
                ok=False,
                error_code="HERMES_CLI_UNAVAILABLE",
                error_summary="Hermes CLI could not be started.",
            )

        combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        safe_tail = redact_paths(redact_secrets(combined), str(Path.home()))
        if len(safe_tail) > 2000:
            safe_tail = safe_tail[-2000:]
        session_id = _parse_session_id_from_output(combined)
        _LOG.info(
            "ham_native_workspace_cli_finished import_job_id=%s exit_code=%s "
            "session_id_present=%s output_tail_chars=%d",
            import_job_id,
            proc.returncode,
            bool(session_id),
            len(safe_tail),
        )

        files = collect_workspace_files(workspace_dir)
        if not files:
            return WorkspaceExecutionOutcome(
                ok=False,
                error_code="HERMES_CLI_EMPTY_WORKSPACE",
                error_summary="Hermes CLI finished but the workspace has no usable files.",
                session_id=session_id,
                exit_code=proc.returncode,
            )

        if proc.returncode != 0:
            # Non-zero exit but files exist — still attempt materialization (Hermes may warn on exit).
            _LOG.warning(
                "ham_native_workspace_cli_nonzero_exit import_job_id=%s exit_code=%s file_count=%d",
                import_job_id,
                proc.returncode,
                len(files),
            )

        return WorkspaceExecutionOutcome(
            ok=True,
            files=files,
            session_id=session_id,
            exit_code=proc.returncode,
        )


_default_cli_provider = HermesCliWorkspaceProvider()


def get_default_workspace_execution_provider() -> HermesWorkspaceExecutionProvider:
    return _default_cli_provider


def run_hermes_cli_workspace_build(
    *,
    workspace_dir: Path,
    user_prompt: str,
    import_job_id: str,
    provider: HermesWorkspaceExecutionProvider | None = None,
) -> WorkspaceExecutionOutcome:
    """Execute the default Hermes CLI workspace provider."""
    impl = provider or get_default_workspace_execution_provider()
    return impl.execute(
        workspace_dir=workspace_dir,
        user_prompt=user_prompt,
        import_job_id=import_job_id,
    )


__all__ = [
    "HermesCliWorkspaceProvider",
    "HermesWorkspaceExecutionProvider",
    "WorkspaceExecutionOutcome",
    "collect_workspace_files",
    "get_default_workspace_execution_provider",
    "run_hermes_cli_workspace_build",
    "seed_minimal_vite_workspace",
]
