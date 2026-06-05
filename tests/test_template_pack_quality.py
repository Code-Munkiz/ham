"""Template pack private visual quality gates."""

from __future__ import annotations

import pytest

from src.ham.build_materialization import materialize_files_to_snapshot
from src.ham.builder_native_hermes import ham_native_builder_user_message
from src.ham.hermes_workspace_builder import execute_hermes_native_workspace_build
from src.ham.template_packs.quality import (
    TemplatePackQualityIssue,
    evaluate_workspace_visual_quality,
    user_message_for_quality_failure,
    visual_quality_repair_instruction,
)
from src.ham.template_packs.renderer import template_pack_hermes_instruction
from src.ham.template_packs.restore import restore_missing_pack_sections
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


def test_agency_modern_has_all_required_section_markers() -> None:
    app = _agency_files()["src/App.tsx"]
    for section in ("hero", "services", "process", "testimonial", "cta"):
        assert f'data-ham-section="{section}"' in app


def test_agency_modern_passes_enhanced_landing_gates() -> None:
    pack = load_template_pack(default_template_packs_root() / "landing" / "agency-modern")
    gates = pack.manifest.quality_gates
    assert gates is not None
    assert gates.min_service_cards == 3
    assert gates.require_hero_richness is True
    assert gates.require_cta_action is True
    result = evaluate_workspace_visual_quality(_agency_files(), pack=pack)
    assert result.ok is True


def test_agency_modern_rejects_sparse_services_section() -> None:
    pack = load_template_pack(default_template_packs_root() / "landing" / "agency-modern")
    files = _agency_files()
    app = files["src/App.tsx"]
    files["src/App.tsx"] = app.replace(
        "  },\n  {\n    title: \"Custom Agents\",",
        "  },",
        1,
    ).replace(
        "  },\n  {\n    title: \"Integration Layer\",",
        "  },",
        1,
    )
    result = evaluate_workspace_visual_quality(files, pack=pack)
    assert result.ok is False
    assert any(issue.code == "insufficient_service_cards" for issue in result.issues)


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


def test_repair_instruction_lists_exact_missing_sections() -> None:
    issues = (
        TemplatePackQualityIssue("missing_section", "Required section not found: cta"),
        TemplatePackQualityIssue("low_contrast", "Possible low-contrast class combination"),
    )
    instruction = visual_quality_repair_instruction(issues=issues)
    assert "Restore these required sections" in instruction
    assert "cta" in instruction
    assert "data-ham-section" in instruction
    assert "low_contrast" in instruction


def test_restore_missing_cta_section_from_pack_template() -> None:
    pack = load_template_pack(default_template_packs_root() / "landing" / "agency-modern")
    files = _agency_files()
    app = files["src/App.tsx"]
    cta_start = app.index('<section\n          data-ham-section="cta"')
    main_close = app.rfind("</main>")
    files["src/App.tsx"] = app[:cta_start] + app[main_close:]

    before = evaluate_workspace_visual_quality(files, pack=pack)
    assert before.ok is False
    assert any(i.code == "missing_section" and "cta" in i.detail for i in before.issues)

    restored = restore_missing_pack_sections(files, pack=pack, issues=before.issues)
    assert restored is not None
    updated_files, restored_ids = restored
    assert "cta" in restored_ids
    assert 'data-ham-section="cta"' in updated_files["src/App.tsx"]

    after = evaluate_workspace_visual_quality(updated_files, pack=pack)
    assert not any(i.code == "missing_section" and "cta" in i.detail for i in after.issues)


def test_agency_pack_uses_preserve_structure_directive() -> None:
    pack = load_template_pack(default_template_packs_root() / "landing" / "agency-modern")
    assert pack.manifest.ai_directive == "preserve_structure"
    instruction = template_pack_hermes_instruction(pack)
    assert "preserve structure" in instruction.lower()
    assert "data-ham-section" in instruction


def test_saas_pack_uses_remix_moderately_directive() -> None:
    pack = load_template_pack(default_template_packs_root() / "landing" / "saas-clean")
    assert pack.manifest.ai_directive == "remix_moderately"
    instruction = template_pack_hermes_instruction(pack)
    assert "remix moderately" in instruction.lower()
