"""Native Hermes builder — workspace lane (JSON artifact mode is not used here)."""

from __future__ import annotations

import pytest

import src.ham.builder_native_hermes as native_hermes
from src.ham.builder_native_hermes import (
    ham_native_builder_user_message,
    hermes_native_builder_ready,
    run_hermes_native_build,
    start_native_build_job,
)
from src.integrations import nous_gateway_client
from src.persistence.builder_source_store import (
    BuilderSourceStore,
    set_builder_source_store_for_tests,
)

_VALID_FILES = {
    "src/App.tsx": "export default function App() { return <main>Native build</main>; }\n",
    "src/main.tsx": (
        "import React from 'react';\n"
        "import ReactDOM from 'react-dom/client';\n"
        "import App from './App';\n"
        "ReactDOM.createRoot(document.getElementById('root')!).render(<App />);\n"
    ),
    "src/styles.css": "body { margin: 0; }\n",
}


def _valid_files_provider(**_kwargs: object) -> dict[str, str]:
    return dict(_VALID_FILES)


def _workspace_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HAM_HERMES_NATIVE_WORKSPACE_ENABLED", "1")
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "disabled")


@pytest.fixture(autouse=True)
def _skip_npm_typecheck_unless_typecheck_test(request: pytest.FixtureRequest, monkeypatch) -> None:
    if "typecheck" in request.node.name:
        return

    def _passthrough(files: dict[str, str]):
        from src.ham.builder_preview_typecheck import (
            PreviewTypecheckResult,
            ensure_preview_tsconfig,
            ensure_tailwind_config_for_preview,
        )

        prepared = ensure_tailwind_config_for_preview(ensure_preview_tsconfig(dict(files)))
        return PreviewTypecheckResult(
            ok=True,
            files=prepared,
            repair_summary=None,
            user_message="",
            compiler_output="",
            deterministic_repair_attempted=False,
        )

    monkeypatch.setattr(
        "src.ham.build_materialization.validate_preview_app_files",
        _passthrough,
    )


def test_native_module_does_not_expose_artifact_turn() -> None:
    assert not hasattr(native_hermes, "complete_artifact_turn")
    assert not hasattr(native_hermes, "complete_chat_turn")


def test_hermes_native_builder_ready_requires_workspace_flag(monkeypatch) -> None:
    monkeypatch.delenv("HAM_HERMES_NATIVE_WORKSPACE_ENABLED", raising=False)
    assert hermes_native_builder_ready() is False
    monkeypatch.setenv("HAM_HERMES_NATIVE_WORKSPACE_ENABLED", "1")
    assert hermes_native_builder_ready() is True


def test_workspace_not_configured_fails_without_job(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("HAM_HERMES_NATIVE_WORKSPACE_ENABLED", raising=False)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    artifact_calls: list[str] = []

    def _must_not_run(*_a, **_k):
        artifact_calls.append("called")
        raise AssertionError("complete_artifact_turn must not run")

    monkeypatch.setattr(nous_gateway_client, "complete_artifact_turn", _must_not_run)
    try:
        result = run_hermes_native_build(
            workspace_id="ws_native",
            project_id="proj_native",
            session_id="sess_native",
            user_prompt="build a small native app",
            created_by="user_native",
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert artifact_calls == []
    assert result["ham_native_builder"] == {
        "status": "unavailable",
        "failure_reason": "workspace_not_configured",
    }
    msg = ham_native_builder_user_message(result["ham_native_builder"])
    assert msg.startswith("Native Hermes workspace execution is not configured yet.")
    assert store.list_import_jobs(workspace_id="ws_native", project_id="proj_native") == []


def test_start_native_build_job_unconfigured_returns_safe_copy(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("HAM_HERMES_NATIVE_WORKSPACE_ENABLED", raising=False)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    try:
        result = start_native_build_job(
            workspace_id="ws_native",
            project_id="proj_native",
            session_id="sess_native",
            user_prompt="build app",
            created_by="user_native",
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert result["ham_native_builder"]["status"] == "unavailable"
    assert ham_native_builder_user_message(result["ham_native_builder"]).startswith(
        "Native Hermes workspace execution is not configured yet."
    )


def test_workspace_build_materializes_snapshot(tmp_path, monkeypatch) -> None:
    _workspace_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    artifact_calls: list[str] = []

    monkeypatch.setattr(
        nous_gateway_client,
        "complete_artifact_turn",
        lambda *_a, **_k: artifact_calls.append("called") or "{}",
    )
    try:
        result = run_hermes_native_build(
            workspace_id="ws_native",
            project_id="proj_native",
            session_id="sess_native",
            user_prompt="build a small native app",
            created_by="user_native",
            workspace_files_provider=_valid_files_provider,
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert artifact_calls == []
    assert result["scaffolded"] is True
    assert result["ham_native_builder"]["status"] == "succeeded"
    snapshots = store.list_source_snapshots(workspace_id="ws_native", project_id="proj_native")
    assert snapshots[0].manifest["kind"] == "inline_text_bundle"
    assert "package.json" in snapshots[0].manifest["inline_files"]


def test_workspace_enabled_without_files_fails_safely(tmp_path, monkeypatch) -> None:
    _workspace_env(tmp_path, monkeypatch)
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    try:
        result = run_hermes_native_build(
            workspace_id="ws_native",
            project_id="proj_native",
            session_id="sess_native",
            user_prompt="build a small native app",
            created_by="user_native",
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert result["scaffolded"] is False
    assert result["ham_native_builder"]["status"] == "failed"
    jobs = store.list_import_jobs(workspace_id="ws_native", project_id="proj_native")
    assert jobs[0].status == "failed"


def test_build_registry_context_reaches_workspace_adapter(tmp_path, monkeypatch) -> None:
    _workspace_env(tmp_path, monkeypatch)
    seen: dict[str, str] = {}

    def _capture_provider(**kwargs: object) -> dict[str, str]:
        seen["prompt"] = str(kwargs.get("user_prompt") or "")
        return dict(_VALID_FILES)

    monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "1")
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    try:
        run_hermes_native_build(
            workspace_id="ws_native",
            project_id="proj_native",
            session_id="sess_native",
            user_prompt="build a static landing page with hero and pricing",
            created_by="user_native",
            workspace_files_provider=_capture_provider,
        )
    finally:
        set_builder_source_store_for_tests(None)

    prompt = seen.get("prompt", "")
    assert "Build Registry v2 playbook context:" in prompt or prompt.startswith(
        "build a static landing page"
    )
