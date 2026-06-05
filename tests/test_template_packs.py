"""Template Pack Registry v1 — loader, selector, materializer, workspace integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ham.build_registry.user_copy_sanitize import contains_build_registry_v2_forbidden_token
from src.ham.hermes_workspace_builder import append_build_registry_context, execute_hermes_native_workspace_build
from src.ham.hermes_workspace_execution import seed_template_pack_workspace
from src.ham.template_packs.quality import contains_template_pack_leak
from src.ham.template_packs.registry import (
    default_template_packs_root,
    load_template_pack,
    load_template_pack_registry,
)
from src.ham.template_packs.renderer import materialize_pack_files, write_pack_to_workspace
from src.ham.template_packs.selector import select_template_pack
import src.ham.builder_native_hermes as native_hermes
from src.integrations import nous_gateway_client


def _agency_root() -> Path:
    return default_template_packs_root() / "landing" / "agency-modern"


def _pm_root() -> Path:
    return default_template_packs_root() / "dashboard" / "project-management"


def test_template_pack_registry_loads_packs() -> None:
    registry = load_template_pack_registry()
    assert "landing/agency-modern" in registry
    assert "dashboard/project-management" in registry
    pack = registry["landing/agency-modern"]
    assert pack.manifest.name == "Agency Modern Landing"
    assert "src/App.tsx" in pack.files
    assert pack.manifest.license is not None
    assert pack.manifest.license.id == "ham-authored-internal"


def test_selector_chooses_agency_modern_for_agency_landing() -> None:
    registry = load_template_pack_registry()
    pack = select_template_pack(
        "Build a marketing landing page for our AI automation agency with hero and testimonials",
        registry=registry,
    )
    assert pack.id == "landing/agency-modern"


def test_selector_chooses_project_management_for_dashboard() -> None:
    registry = load_template_pack_registry()
    pack = select_template_pack(
        "Create a project management dashboard with team workload and status table",
        registry=registry,
    )
    assert pack.id == "dashboard/project-management"


def test_selector_chooses_saas_clean_when_present() -> None:
    registry = load_template_pack_registry()
    pack = select_template_pack("SaaS startup landing page for our B2B product", registry=registry)
    assert pack.id == "landing/saas-clean"


def test_pack_materializer_writes_required_files(tmp_path: Path) -> None:
    pack = load_template_pack(_agency_root())
    files = materialize_pack_files(pack, project_title="Acme Agency")
    write_pack_to_workspace(tmp_path, files)
    assert (tmp_path / "src" / "App.tsx").is_file()
    assert (tmp_path / "src" / "main.tsx").is_file()
    assert (tmp_path / "src" / "index.css").is_file()
    assert (tmp_path / "package.json").is_file()
    pkg = (tmp_path / "package.json").read_text(encoding="utf-8")
    assert "acme-agency" in pkg


def test_hermes_workspace_starts_from_template_pack_files(tmp_path: Path) -> None:
    pack = load_template_pack(_agency_root())
    seed_template_pack_workspace(tmp_path, pack=pack, user_prompt="agency site")
    app = (tmp_path / "src" / "App.tsx").read_text(encoding="utf-8")
    assert 'data-ham-section="hero"' in app
    assert "tailwind" not in app.lower() or "rounded" in app


def test_build_registry_v2_guidance_still_passes_through() -> None:
    prompt = append_build_registry_context(
        "build a static landing page with hero and pricing",
        originated_from="test",
    )
    assert "landing page" in prompt.lower() or "Build Registry v2" in prompt


def test_native_module_does_not_expose_artifact_turn() -> None:
    assert not hasattr(native_hermes, "complete_artifact_turn")


def test_user_copy_sanitizer_blocks_template_pack_internals() -> None:
    assert contains_template_pack_leak("Used landing/agency-modern template pack")
    safe = "HAM couldn't finish this preview."
    assert not contains_template_pack_leak(safe)
    assert not contains_build_registry_v2_forbidden_token(safe)


def test_workspace_build_includes_registry_not_pack_id_in_provider_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.persistence.builder_source_store import (
        BuilderSourceStore,
        set_builder_source_store_for_tests,
    )

    monkeypatch.setenv("HAM_HERMES_NATIVE_WORKSPACE_ENABLED", "1")
    monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "1")
    monkeypatch.setenv("HAM_BUILDER_SOURCE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    seen: dict[str, str] = {}

    def _passthrough(files: dict[str, str]):
        from src.ham.builder_preview_typecheck import (
            PreviewTypecheckResult,
            ensure_preview_tsconfig,
            ensure_tailwind_config_for_preview,
        )

        prepared = ensure_tailwind_config_for_preview(ensure_preview_tsconfig(dict(files)))
        return PreviewTypecheckResult(ok=True, files=prepared, repair_summary=None, user_message="", compiler_output="", deterministic_repair_attempted=False)

    monkeypatch.setattr("src.ham.build_materialization.validate_preview_app_files", _passthrough)

    def _provider(**kwargs: object) -> dict[str, str]:
        seen["prompt"] = str(kwargs.get("user_prompt") or "")
        pack = load_template_pack(_agency_root())
        return dict(pack.files)

    try:
        result = execute_hermes_native_workspace_build(
            import_job_id="job_tpl",
            workspace_id="ws_tpl",
            project_id="proj_tpl",
            session_id="sess_tpl",
            user_prompt="agency landing page with hero",
            created_by="user_tpl",
            files_provider=_provider,
        )
    finally:
        set_builder_source_store_for_tests(None)

    prompt = seen.get("prompt", "")
    assert "landing/agency-modern" not in prompt
    assert result.status == "succeeded"
    assert result.source_snapshot_id


def test_artifact_turn_unreachable_on_native_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAM_HERMES_NATIVE_WORKSPACE_ENABLED", "1")
    calls: list[str] = []
    monkeypatch.setattr(
        nous_gateway_client,
        "complete_artifact_turn",
        lambda *_a, **_k: calls.append("called") or "{}",
    )
    from src.persistence.builder_source_store import (
        BuilderSourceStore,
        set_builder_source_store_for_tests,
    )

    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    pack = load_template_pack(_agency_root())

    def _provider(**_kw: object) -> dict[str, str]:
        return dict(pack.files)

    try:
        from src.ham.builder_native_hermes import run_hermes_native_build

        run_hermes_native_build(
            workspace_id="ws",
            project_id="proj",
            session_id="sess",
            user_prompt="agency landing",
            created_by="user",
            workspace_files_provider=_provider,
        )
    finally:
        set_builder_source_store_for_tests(None)
    assert calls == []
