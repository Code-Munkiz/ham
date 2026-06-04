"""Tests for Native Hermes workspace typecheck operator diagnostics."""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

import pytest

from src.ham.builder_native_hermes import ham_native_builder_user_message, run_hermes_native_build
from src.ham.workspace_typecheck_diagnostics import (
    OPERATOR_METADATA_KEY,
    OPERATOR_STATS_KEY,
    build_typecheck_diagnostic_summary,
    capture_failed_workspace_artifact,
    should_skip_failed_artifact_path,
    strip_operator_fields_from_import_job_payload,
)
from src.integrations import nous_gateway_client
from src.persistence.builder_source_store import (
    BuilderSourceStore,
    set_builder_source_store_for_tests,
)


def _broken_ts_files(**_kwargs: object) -> dict[str, str]:
    return {
        "package.json": (
            '{"name":"broken","private":true,"type":"module",'
            '"scripts":{"dev":"vite"},"dependencies":{"react":"^18.3.1","react-dom":"^18.3.1"},'
            '"devDependencies":{"typescript":"^5.6.3","vite":"^5.4.11","@vitejs/plugin-react":"^4.3.4"}}'
        ),
        "index.html": '<!doctype html><html><body><div id="root"></div>'
        '<script type="module" src="/src/main.tsx"></script></body></html>\n',
        "vite.config.ts": 'import { defineConfig } from "vite";\nexport default defineConfig({});\n',
        "src/main.tsx": 'import App from "./App";\nconsole.log(TEAM);\n',
        "src/App.tsx": "export default function App() { return null; }\n",
    }


def _workspace_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_HERMES_NATIVE_WORKSPACE_ENABLED", "1")
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "disabled")


@pytest.mark.skipif(
    __import__("shutil").which("npx") is None,
    reason="npx required for typecheck failure integration test",
)
def test_broken_ts_workspace_persists_typecheck_diagnostic_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _workspace_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    caplog.set_level(logging.WARNING)
    try:
        run_hermes_native_build(
            workspace_id="ws_diag",
            project_id="proj_diag",
            session_id="sess_diag",
            user_prompt="build a dashboard",
            created_by="user_diag",
            workspace_files_provider=_broken_ts_files,
        )
    finally:
        set_builder_source_store_for_tests(None)

    jobs = store.list_import_jobs(workspace_id="ws_diag", project_id="proj_diag")
    assert jobs[0].status == "failed"
    assert jobs[0].error_code == "HAM_NATIVE_BUILDER_TYPECHECK_FAILED"
    stats = jobs[0].stats.get(OPERATOR_STATS_KEY) or {}
    assert stats.get("failure_kind") == "typecheck"
    assert stats.get("file_count", 0) >= 1
    assert "src/main.tsx" in (stats.get("file_paths") or [])
    assert stats.get("has_package_json") is True
    assert stats.get("has_index_html") is True
    assert stats.get("tsc_output_excerpt")
    operator = jobs[0].metadata.get(OPERATOR_METADATA_KEY) or {}
    assert operator.get("error_code") == "HAM_NATIVE_BUILDER_TYPECHECK_FAILED"
    assert "artifact_capture" in operator

    typecheck_logs = [r for r in caplog.records if "hermes_native_workspace_typecheck_failed" in r.message]
    assert typecheck_logs
    assert "console.log(TEAM)" not in caplog.text


def test_failed_workspace_artifact_excludes_node_modules_and_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    files = {
        "package.json": "{}\n",
        "src/App.tsx": "export default function App() { return null; }\n",
        "node_modules/pkg/index.js": "secret module\n",
        ".env": "API_KEY=supersecret\n",
        ".env.local": "TOKEN=abc\n",
    }
    result = capture_failed_workspace_artifact(
        files=files,
        workspace_id="ws_art",
        project_id="proj_art",
        import_job_id="ijob_test123",
    )
    assert result.get("capture_status") == "stored"
    artifact_root = tmp_path / "artifacts" / "ws_art" / "proj_art" / "failed-workspaces"
    zips = list(artifact_root.glob("*.zip"))
    assert len(zips) == 1
    with zipfile.ZipFile(zips[0]) as zf:
        names = set(zf.namelist())
    assert "package.json" in names
    assert "src/App.tsx" in names
    assert not any("node_modules" in n for n in names)
    assert ".env" not in names
    assert ".env.local" not in names


def test_should_skip_failed_artifact_path() -> None:
    assert should_skip_failed_artifact_path("node_modules/react/index.js")
    assert should_skip_failed_artifact_path(".env")
    assert should_skip_failed_artifact_path(".env.production")
    assert not should_skip_failed_artifact_path("src/App.tsx")


def test_user_facing_failure_does_not_expose_operator_internals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    artifact_calls: list[str] = []

    monkeypatch.setattr(
        nous_gateway_client,
        "complete_artifact_turn",
        lambda *_a, **_k: artifact_calls.append("called") or "{}",
    )

    if __import__("shutil").which("npx") is None:
        pytest.skip("npx required")

    try:
        result = run_hermes_native_build(
            workspace_id="ws_pub",
            project_id="proj_pub",
            session_id="sess_pub",
            user_prompt="build app",
            created_by="user_pub",
            workspace_files_provider=_broken_ts_files,
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert artifact_calls == []
    msg = ham_native_builder_user_message(result["ham_native_builder"])
    assert "builder-failed-artifact://" not in msg
    assert "tsc_output_excerpt" not in msg
    assert OPERATOR_METADATA_KEY not in str(result)

    jobs = store.list_import_jobs(workspace_id="ws_pub", project_id="proj_pub")
    assert "TypeScript" in (jobs[0].error_message or "")
    public = strip_operator_fields_from_import_job_payload(jobs[0].model_dump(mode="json"))
    assert OPERATOR_METADATA_KEY not in public.get("metadata", {})
    assert OPERATOR_STATS_KEY not in public.get("stats", {})
    assert jobs[0].error_message
    assert "builder-failed-artifact://" not in jobs[0].error_message


def test_warning_logs_include_counts_not_bodies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _workspace_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    caplog.set_level(logging.WARNING)

    if __import__("shutil").which("npx") is None:
        pytest.skip("npx required")

    try:
        run_hermes_native_build(
            workspace_id="ws_log",
            project_id="proj_log",
            session_id="sess_log",
            user_prompt="build app",
            created_by="user_log",
            workspace_files_provider=_broken_ts_files,
        )
    finally:
        set_builder_source_store_for_tests(None)

    joined = "\n".join(r.message for r in caplog.records)
    assert "hermes_native_workspace_start" in joined
    assert "hermes_native_workspace_files_collected" in joined
    assert "hermes_native_workspace_typecheck_failed" in joined
    assert "HAM_NATIVE_BUILDER_TYPECHECK_FAILED" in joined
    assert "console.log(TEAM)" not in joined
    assert "supersecret" not in joined


def test_build_typecheck_diagnostic_summary_shape() -> None:
    files = {"package.json": "{}", "src/App.tsx": "x"}
    stats, meta = build_typecheck_diagnostic_summary(
        files=files,
        error_code="HAM_NATIVE_BUILDER_TYPECHECK_FAILED",
        compiler_output="src/App.tsx(1,1): error TS2304: Cannot find name 'TEAM'.",
    )
    assert stats[OPERATOR_STATS_KEY]["failure_kind"] == "typecheck"
    assert meta[OPERATOR_METADATA_KEY]["has_package_json"] is True
    assert "TEAM" in stats[OPERATOR_STATS_KEY]["tsc_output_excerpt"]
