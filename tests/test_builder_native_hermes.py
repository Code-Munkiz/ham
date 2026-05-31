from __future__ import annotations

import json

from src.ham.builder_native_hermes import run_hermes_native_build
from src.persistence.builder_source_store import BuilderSourceStore, set_builder_source_store_for_tests


def test_hermes_native_build_creates_source_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("HAM_BUILDER_CLOUD_RUNTIME_PROVIDER", "disabled")
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    try:
        payload = {
            "status": "success",
            "summary": "Built.",
            "files": {
                "src/App.tsx": "export default function App() { return <main>Native build</main>; }\n",
                "src/main.tsx": "import React from 'react';\nimport ReactDOM from 'react-dom/client';\nimport App from './App';\nReactDOM.createRoot(document.getElementById('root')!).render(<App />);\n",
                "src/styles.css": "body { margin: 0; }\n",
            },
            "checks": ["renders"],
        }

        result = run_hermes_native_build(
            workspace_id="ws_native",
            project_id="proj_native",
            session_id="sess_native",
            user_prompt="build a small native app",
            created_by="user_native",
            complete_turn=lambda _messages: json.dumps(payload),
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert result["scaffolded"] is True
    assert result["ham_native_builder"]["status"] == "succeeded"
    source_rows = store.list_project_sources(workspace_id="ws_native", project_id="proj_native")
    assert source_rows[0].kind == "ham_native_builder"
    snapshots = store.list_source_snapshots(workspace_id="ws_native", project_id="proj_native")
    assert snapshots[0].manifest["kind"] == "inline_text_bundle"
    assert "src/App.tsx" in snapshots[0].manifest["inline_files"]
    assert "package.json" in snapshots[0].manifest["inline_files"]


def test_hermes_native_build_rejects_internal_tokens(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    try:
        payload = {
            "status": "success",
            "files": {
                "src/App.tsx": "export const x = 'proposal_digest';\n",
            },
        }
        result = run_hermes_native_build(
            workspace_id="ws_native",
            project_id="proj_native",
            session_id="sess_native",
            user_prompt="build a small native app",
            created_by="user_native",
            complete_turn=lambda _messages: json.dumps(payload),
        )
    finally:
        set_builder_source_store_for_tests(None)

    assert result["scaffolded"] is False
    assert result["ham_native_builder"]["status"] == "failed"
