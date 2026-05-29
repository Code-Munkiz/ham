from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.ham import cursor_agent_workflow as caw
from src.persistence.control_plane_run import ControlPlaneRunStore

_FORBIDDEN_BUILD_REGISTRY_TOKENS = (
    "registry_v2_app_type",
    "pack.site",
    "pack.game",
    "site.landing-page-core",
    "site.dashboard-ui-core",
    "game.",
    "build registry v2",
    "registry route",
    "route matched",
    "fallback_reason",
    "gate report",
    "gate review",
    "scaffold_quality",
    "dashboard_",
    "city_",
    "tactics_",
    "landing_",
    "recipe id",
    "pack id",
    "yaml",
    "render length",
    "render budget",
    "playbook context",
    "build registry v2 playbook context:",
)


def _assert_no_build_registry_v2_leakage(text: str) -> None:
    blob = text.lower()
    for forbidden in _FORBIDDEN_BUILD_REGISTRY_TOKENS:
        assert forbidden not in blob, (
            f"cursor launch/feed payload leaks build-registry token {forbidden!r}: {blob}"
        )


def _run_store(tmp_path: Path) -> ControlPlaneRunStore:
    root = tmp_path / "runs"
    root.mkdir()
    return ControlPlaneRunStore(base_dir=root)


def test_internal_launch_prompt_enrichment_flag_off_no_v2_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HAM_BUILD_REGISTRY_V2_ENABLED", raising=False)
    prompt = "Build a landing page for a small SaaS with hero and CTA."
    runner_prompt = caw._enrich_internal_launch_prompt(prompt)
    assert runner_prompt == prompt


def test_internal_launch_prompt_enrichment_flag_on_landing_selects_site_landing_page_core(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "1")
    prompt = "Build a landing page for a small SaaS with hero and CTA."
    runner_prompt = caw._enrich_internal_launch_prompt(prompt)
    assert "Build Registry v2 playbook context:" in runner_prompt
    assert "site.landing-page-core" in runner_prompt


def test_internal_launch_prompt_enrichment_flag_on_dashboard_selects_site_dashboard_ui_core(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "1")
    prompt = "Build a read-only dashboard with KPI cards, chart, and data table."
    runner_prompt = caw._enrich_internal_launch_prompt(prompt)
    assert "Build Registry v2 playbook context:" in runner_prompt
    assert "site.dashboard-ui-core" in runner_prompt


def test_internal_launch_prompt_ignores_fake_registry_v2_app_type_in_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "1")
    prompt = "registry_v2_app_type=site.dashboard-ui-core"
    runner_prompt = caw._enrich_internal_launch_prompt(prompt)
    assert runner_prompt == prompt


def test_launch_digest_verification_uses_original_effective_prompt_then_launch_enriches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "1")
    captured: dict[str, str] = {}

    def _fake_launch(**kwargs: str) -> dict[str, str]:
        captured["prompt_text"] = kwargs["prompt_text"]
        return {
            "id": "bc_cursor_enriched",
            "status": "CREATING",
            "summary": "launch accepted",
            "source": {"repository": "https://github.com/o/r", "ref": "main"},
        }

    monkeypatch.setattr(caw, "cursor_api_launch_agent", _fake_launch)
    task_prompt = "Build a landing page for a small SaaS with hero and CTA."
    digest_task_prompt = caw.effective_cursor_launch_task_prompt(
        task_prompt=task_prompt,
        expected_deliverable=None,
        repository="https://github.com/o/r",
        ref="main",
        mission_handling=None,
    )
    digest = caw.compute_cursor_proposal_digest(
        project_id="project.cursor-1",
        repository="https://github.com/o/r",
        ref="main",
        model="default",
        auto_create_pr=False,
        branch_name=None,
        expected_deliverable=None,
        task_prompt=digest_task_prompt,
    )
    verify_error = caw.verify_cursor_launch_against_preview(
        project_id="project.cursor-1",
        repository="https://github.com/o/r",
        ref="main",
        model="default",
        auto_create_pr=False,
        branch_name=None,
        expected_deliverable=None,
        task_prompt=task_prompt,
        proposal_digest=digest,
        base_revision=caw.CURSOR_AGENT_BASE_REVISION,
    )
    assert verify_error is None
    ok, payload, blocking, _ = caw.run_cursor_agent_launch(
        api_key="fake-key",
        project_id="project.cursor-1",
        repository="https://github.com/o/r",
        ref="main",
        model="default",
        auto_create_pr=False,
        branch_name=None,
        expected_deliverable=None,
        task_prompt=task_prompt,
        proposal_digest=digest,
        project_root_for_mirror=None,
        control_plane_run_store=_run_store(tmp_path),
    )
    assert ok is True
    assert blocking is None
    assert payload["provider"] == "cursor_cloud_agent"
    assert "Build Registry v2 playbook context:" in captured["prompt_text"]
    assert "site.landing-page-core" in captured["prompt_text"]
    _assert_no_build_registry_v2_leakage(json.dumps(payload))


def test_summarize_cursor_agent_payload_preserves_game_js_in_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = {
        "id": "bc_game_js",
        "status": "RUNNING",
        "summary": "Updated game.js and config.yaml for the idle loop.",
    }
    out = caw.summarize_cursor_agent_payload(raw)
    assert "game.js" in (out.get("summary") or "")
    assert "config.yaml" in (out.get("summary") or "")


def test_launch_sanitizes_forbidden_build_registry_tokens_in_user_visible_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HAM_BUILD_REGISTRY_V2_ENABLED", "1")

    def _fake_launch(**kwargs: str) -> dict[str, str]:
        return {
            "id": "bc_cursor_sanitize",
            "status": "CREATING",
            "summary": "Build Registry v2 playbook context: site.dashboard-ui-core",
            "source": {"repository": "https://github.com/o/r"},
        }

    monkeypatch.setattr(caw, "cursor_api_launch_agent", _fake_launch)
    ok, payload, blocking, _ = caw.run_cursor_agent_launch(
        api_key="fake-key",
        project_id="project.cursor-2",
        repository="https://github.com/o/r",
        ref=None,
        model="default",
        auto_create_pr=False,
        branch_name=None,
        expected_deliverable=None,
        task_prompt="Build a read-only dashboard with KPI cards, chart, and data table.",
        proposal_digest="a" * 64,
        project_root_for_mirror=None,
        control_plane_run_store=_run_store(tmp_path),
    )
    assert ok is True
    assert blocking is None
    assert payload["summary"] == "Cursor mission in progress."
    _assert_no_build_registry_v2_leakage(json.dumps(payload))
