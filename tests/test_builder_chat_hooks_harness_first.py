"""User-selected builder model: a normal build prompt routes to the selected
builder (or asks the user to choose) and never silently runs the internal
scaffold. The internal scaffold runs only on an explicit Quick Preview request.
See docs/build-kit-registry-v2/HARNESS_FIRST_ARCHITECTURE_PLAN.md.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.ham.builder_chat_hooks import (
    premium_harness_available_for_build,
    run_builder_happy_path_hook,
)
from src.ham.clerk_auth import HamActor
from src.ham.coding_router.types import (
    ProjectFlags,
    ProviderReadiness,
    WorkspaceReadiness,
)
from src.persistence.builder_source_store import (
    BuilderSourceStore,
    set_builder_source_store_for_tests,
)

# Provider-internal / secret tokens that must never leak into user-facing copy
# or response metadata. Product-facing builder display labels (e.g. "OpenCode",
# "Factory Droid") are intentionally NOT in this list.
_FORBIDDEN_TOKENS = (
    "opencode_cli",
    "factory_droid_build",
    "cursor_cloud",
    "claude_agent",
    "claude_code",
    "ham_droid_exec_token",
    "ham_opencode_exec_token",
    "ham_claude_agent_exec_token",
    "cursor_api_key",
    "anthropic_api_key",
    "safe_edit_low",
    "registry_v2",
    "scaffold_quality",
    "playbook context",
    "recipe id",
)

_HOOKS = "src.ham.builder_chat_hooks"


def _byo_actor(uid: str = "user_sel") -> HamActor:
    return HamActor(
        user_id=uid,
        org_id=None,
        session_id=None,
        email=f"{uid}@example.com",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


def _raise_if_called(**_kw: object) -> object:
    raise AssertionError("internal scaffold must not run for a normal build prompt")


@pytest.fixture
def _empty_store(tmp_path):
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    try:
        yield store
    finally:
        set_builder_source_store_for_tests(None)


def _run(prompt: str):
    return run_builder_happy_path_hook(
        workspace_id="ws_sel",
        project_id="proj_sel",
        session_id="sess_sel",
        last_user_plain=prompt,
        ham_actor=_byo_actor(),
    )


# ---------------------------------------------------------------------------
# Normal build prompt routing (never scaffolds)
# ---------------------------------------------------------------------------


def test_selected_builder_ready_hands_off_and_blocks_scaffold(_empty_store) -> None:
    with (
        patch(f"{_HOOKS}._selected_builder_for_workspace", return_value="opencode"),
        patch(f"{_HOOKS}._selected_builder_ready", return_value=True),
        patch(
            "src.ham.builder_chat_scaffold.maybe_chat_scaffold_for_turn",
            side_effect=_raise_if_called,
        ) as scaffold_mock,
    ):
        prefix, meta = _run("build me a tetris game")
    scaffold_mock.assert_not_called()
    assert meta.get("selected_builder_state") == "ready"
    assert meta.get("selected_builder_label") == "OpenCode"
    assert meta.get("builder_harness_first") is True
    assert meta.get("scaffolded") is False
    assert "OpenCode" in prefix and "build panel" in prefix


def test_selected_builder_not_ready_returns_setup_copy_and_blocks_scaffold(_empty_store) -> None:
    with (
        patch(f"{_HOOKS}._selected_builder_for_workspace", return_value="cursor"),
        patch(f"{_HOOKS}._selected_builder_ready", return_value=False),
        patch(
            "src.ham.builder_chat_scaffold.maybe_chat_scaffold_for_turn",
            side_effect=_raise_if_called,
        ) as scaffold_mock,
    ):
        prefix, meta = _run("build me a tetris game")
    scaffold_mock.assert_not_called()
    assert meta.get("selected_builder_state") == "setup_required"
    assert meta.get("selected_builder_label") == "Cursor"
    assert "isn't set up" in prefix


def test_no_selection_no_default_asks_user_to_choose_and_blocks_scaffold(_empty_store) -> None:
    with (
        patch(f"{_HOOKS}._selected_builder_for_workspace", return_value=None),
        patch(f"{_HOOKS}.configured_default_builder", return_value=None),
        patch(
            "src.ham.builder_chat_scaffold.maybe_chat_scaffold_for_turn",
            side_effect=_raise_if_called,
        ) as scaffold_mock,
    ):
        prefix, meta = _run("build me a tetris game")
    scaffold_mock.assert_not_called()
    assert meta.get("selected_builder_state") == "choose"
    assert "Which builder" in prefix
    assert "quick preview" in prefix.lower()


def test_no_selection_with_configured_opencode_default_hands_off(_empty_store) -> None:
    with (
        patch(f"{_HOOKS}._selected_builder_for_workspace", return_value=None),
        patch(f"{_HOOKS}.configured_default_builder", return_value="opencode"),
        patch(f"{_HOOKS}._selected_builder_ready", return_value=True),
        patch(
            "src.ham.builder_chat_scaffold.maybe_chat_scaffold_for_turn",
            side_effect=_raise_if_called,
        ) as scaffold_mock,
    ):
        prefix, meta = _run("build me a tetris game")
    scaffold_mock.assert_not_called()
    assert meta.get("selected_builder_state") == "ready"
    assert meta.get("selected_builder_label") == "OpenCode"
    assert meta.get("selected_builder_source") == "default"


def test_selected_hermes_agent_is_honestly_unavailable_for_new_builds(_empty_store) -> None:
    with (
        patch(f"{_HOOKS}._selected_builder_for_workspace", return_value="hermes_agent"),
        patch(
            "src.ham.builder_chat_scaffold.maybe_chat_scaffold_for_turn",
            side_effect=_raise_if_called,
        ) as scaffold_mock,
    ):
        prefix, meta = _run("build me a tetris game")
    scaffold_mock.assert_not_called()
    assert meta.get("selected_builder_state") == "unavailable"
    assert prefix.strip().startswith("Hermes Agent is not available for new builds yet")


def test_explicit_quick_preview_allows_internal_scaffold_as_preview(_empty_store) -> None:
    sentinel = {
        "builder_intent": "build_or_create",
        "builder_operation": "build_or_create",
        "scaffolded": False,
        "deduplicated": False,
    }
    with (
        patch(f"{_HOOKS}._selected_builder_for_workspace", return_value="opencode"),
        patch(
            "src.ham.builder_chat_scaffold.maybe_chat_scaffold_for_turn",
            return_value=sentinel,
        ) as scaffold_mock,
    ):
        _prefix, meta = _run("build me a tetris game, just a quick preview")
    scaffold_mock.assert_called_once()
    assert meta.get("builder_quick_preview") is True
    assert meta.get("selected_builder_state") is None


def test_selected_builder_responses_expose_no_internals(_empty_store) -> None:
    scenarios = [
        ("opencode", True, None),
        ("cursor", False, None),
        ("hermes_agent", False, None),
        (None, False, None),
    ]
    for selected, ready, default in scenarios:
        with (
            patch(f"{_HOOKS}._selected_builder_for_workspace", return_value=selected),
            patch(f"{_HOOKS}.configured_default_builder", return_value=default),
            patch(f"{_HOOKS}._selected_builder_ready", return_value=ready),
            patch(
                "src.ham.builder_chat_scaffold.maybe_chat_scaffold_for_turn",
                side_effect=_raise_if_called,
            ),
        ):
            prefix, meta = _run("build me a tetris game")
        haystack = f"{prefix}\n{json.dumps(meta, default=str)}".lower()
        for token in _FORBIDDEN_TOKENS:
            assert token not in haystack, f"selected-builder reply leaked {token!r}"


# ---------------------------------------------------------------------------
# Readiness helper (premium_harness_available_for_build) — unchanged utility
# ---------------------------------------------------------------------------


def test_premium_harness_available_true_when_a_premium_provider_is_ready() -> None:
    readiness = WorkspaceReadiness(
        is_operator=False,
        providers=(
            ProviderReadiness(provider="no_agent", available=True, blockers=()),
            ProviderReadiness(provider="opencode_cli", available=True, blockers=()),
        ),
        project=ProjectFlags(found=True, project_id="proj_sel", output_target="managed_workspace"),
    )
    with (
        patch("src.api.coding_agent_access_settings.load_workspace_agent_policy", return_value=None),
        patch("src.ham.coding_router.collate_readiness", return_value=readiness),
    ):
        assert (
            premium_harness_available_for_build(
                workspace_id="ws_sel", project_id="proj_sel", ham_actor=_byo_actor()
            )
            is True
        )


def test_premium_harness_available_false_when_premium_blocked_or_unavailable() -> None:
    readiness = WorkspaceReadiness(
        is_operator=False,
        providers=(
            ProviderReadiness(provider="no_agent", available=True, blockers=()),
            ProviderReadiness(
                provider="cursor_cloud", available=False, blockers=("Cursor key missing.",)
            ),
            ProviderReadiness(
                provider="opencode_cli", available=True, blockers=("Build lane disabled.",)
            ),
        ),
        project=ProjectFlags(found=True, project_id="proj_sel", output_target="managed_workspace"),
    )
    with (
        patch("src.api.coding_agent_access_settings.load_workspace_agent_policy", return_value=None),
        patch("src.ham.coding_router.collate_readiness", return_value=readiness),
    ):
        assert (
            premium_harness_available_for_build(
                workspace_id="ws_sel", project_id="proj_sel", ham_actor=_byo_actor()
            )
            is False
        )
