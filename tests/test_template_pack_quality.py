"""Template pack private visual quality gates."""

from __future__ import annotations

import pytest

from src.ham.build_materialization import materialize_files_to_snapshot
from src.ham.builder_native_hermes import ham_native_builder_user_message
from src.ham.hermes_workspace_builder import execute_hermes_native_workspace_build
from src.ham.template_packs.quality import (
    evaluate_workspace_visual_quality,
    user_message_for_quality_failure,
)
from src.ham.template_packs.registry import default_template_packs_root, load_template_pack
from src.persistence.builder_source_store import (
    BuilderSourceStore,
    set_builder_source_store_for_tests,
)


def _agency_files() -> dict[str, str]:
    return dict(load_template_pack(default_template_packs_root() / "landing" / "agency-modern").files)


def test_quality_gate_passes_polished_tailwind_starter() -> None:
    pack = load_template_pack(default_template_packs_root() / "landing" / "agency-modern")
    result = evaluate_workspace_visual_quality(_agency_files(), pack=pack)
    assert result.ok is True
    assert result.issues == ()


def test_quality_gate_rejects_sparse_unstyled_app() -> None:
    pack = load_template_pack(default_template_packs_root() / "landing" / "agency-modern")
    files = {
        "src/main.tsx": "import App from './App';\n",
        "src/App.tsx": "export default function App() { return <main><h1>Hi</h1></main>; }\n",
    }
    result = evaluate_workspace_visual_quality(files, pack=pack)
    assert result.ok is False
    codes = {issue.code for issue in result.issues}
    assert "sparse_app" in codes or "insufficient_tailwind" in codes


def test_quality_gate_rejects_missing_css_import() -> None:
    pack = load_template_pack(default_template_packs_root() / "landing" / "agency-modern")
    files = _agency_files()
    files["src/main.tsx"] = (
        "import React from 'react';\n"
        "import ReactDOM from 'react-dom/client';\n"
        "import App from './App';\n"
        "ReactDOM.createRoot(document.getElementById('root')!).render(<App />);\n"
    )
    result = evaluate_workspace_visual_quality(files, pack=pack)
    assert result.ok is False
    assert any(issue.code == "css_not_imported" for issue in result.issues)


def test_failed_quality_gate_blocks_preview_ready_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_HERMES_NATIVE_WORKSPACE_ENABLED", "1")
    monkeypatch.setenv("HAM_TEMPLATE_PACK_QUALITY_REPAIR_ENABLED", "0")

    def _sparse_provider(**_kw: object) -> dict[str, str]:
        return {
            "package.json": '{"name":"x","private":true,"version":"0.0.1","type":"module","scripts":{"dev":"vite"},"dependencies":{"react":"^18.3.1","react-dom":"^18.3.1"},"devDependencies":{"vite":"^5.4.11","typescript":"^5.6.3","@vitejs/plugin-react":"^4.3.4","@types/react":"^18.3.12","@types/react-dom":"^18.3.1"}}\n',
            "index.html": "<!doctype html><html><body><div id=\"root\"></div></body></html>\n",
            "vite.config.ts": "import { defineConfig } from 'vite';\nexport default defineConfig({});\n",
            "src/main.tsx": "import App from './App';\n",
            "src/App.tsx": "export default function App(){return <main>ok</main>}\n",
        }

    result = execute_hermes_native_workspace_build(
        import_job_id="job_q",
        workspace_id="ws_q",
        project_id="proj_q",
        session_id="sess_q",
        user_prompt="agency landing",
        created_by="user_q",
        files_provider=_sparse_provider,
    )
    assert result.status == "failed"
    assert result.failure_reason == "visual_quality"
    assert result.source_snapshot_id is None
    assert user_message_for_quality_failure() in (result.user_message or "")


def test_user_facing_copy_simple_on_quality_failure() -> None:
    msg = ham_native_builder_user_message(
        {"status": "failed", "failure_reason": "visual_quality"}
    )
    assert "HAM couldn't finish this preview." in msg
    assert "template pack" not in msg.lower()
    assert "tailwind" not in msg.lower()


def test_operator_metadata_has_quality_codes_not_in_user_message() -> None:
    pack = load_template_pack(default_template_packs_root() / "landing" / "agency-modern")
    result = evaluate_workspace_visual_quality({"src/App.tsx": "<main></main>"}, pack=pack)
    meta = result.to_operator_metadata()
    assert meta["template_pack_quality_ok"] is False
    assert meta["issues"]
    user_msg = user_message_for_quality_failure()
    assert "insufficient_tailwind" not in user_msg


def test_materialize_not_called_when_quality_fails_before_snapshot(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAM_HERMES_NATIVE_WORKSPACE_ENABLED", "1")
    monkeypatch.setenv("HAM_TEMPLATE_PACK_QUALITY_REPAIR_ENABLED", "0")
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)

    def _sparse(**_kw: object) -> dict[str, str]:
        return {"src/App.tsx": "export default function App(){return <main/>}\n"}

    try:
        result = execute_hermes_native_workspace_build(
            import_job_id="job_block",
            workspace_id="ws",
            project_id="proj",
            session_id="sess",
            user_prompt="landing",
            created_by="user",
            files_provider=_sparse,
        )
    finally:
        set_builder_source_store_for_tests(None)
    assert result.status == "failed"
    assert result.source_snapshot_id is None
