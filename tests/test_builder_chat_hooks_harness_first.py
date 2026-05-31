"""Harness-first guard: normal build prompts must not silently use the internal
scaffold when a premium harness (Cursor / Claude / OpenCode / Factory Droid) is
eligible. See docs/build-kit-registry-v2/HARNESS_FIRST_ARCHITECTURE_PLAN.md.
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

# Internals that must never leak into the harness-first reply or its metadata.
_FORBIDDEN_TOKENS = (
    "opencode_cli",
    "factory_droid",
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


def _byo_actor(uid: str = "user_harness") -> HamActor:
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
    raise AssertionError("maybe_chat_scaffold_for_turn must not run when a harness is eligible")


@pytest.fixture
def _empty_store(tmp_path):
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    try:
        yield store
    finally:
        set_builder_source_store_for_tests(None)


def test_build_prompt_with_eligible_harness_does_not_invoke_scaffold(
    _empty_store: BuilderSourceStore,
) -> None:
    with (
        patch(
            "src.ham.builder_chat_hooks.premium_harness_available_for_build",
            return_value=True,
        ),
        patch(
            "src.ham.builder_chat_scaffold.maybe_chat_scaffold_for_turn",
            side_effect=_raise_if_called,
        ) as scaffold_mock,
    ):
        prefix, meta = run_builder_happy_path_hook(
            workspace_id="ws_h",
            project_id="proj_h",
            session_id="sess_h",
            last_user_plain="build me a tetris game",
            ham_actor=_byo_actor(),
        )
    scaffold_mock.assert_not_called()
    assert meta.get("builder_harness_first") is True
    assert meta.get("harness_build_available") is True
    assert meta.get("scaffolded") is False
    assert meta.get("builder_intent") == "answer_question"
    assert isinstance(prefix, str) and prefix.strip()


def test_no_eligible_harness_falls_back_to_internal_scaffold(
    _empty_store: BuilderSourceStore,
) -> None:
    sentinel = {
        "builder_intent": "build_or_create",
        "builder_operation": "build_or_create",
        "scaffolded": False,
        "deduplicated": False,
    }
    with (
        patch(
            "src.ham.builder_chat_hooks.premium_harness_available_for_build",
            return_value=False,
        ),
        patch(
            "src.ham.builder_chat_scaffold.maybe_chat_scaffold_for_turn",
            return_value=sentinel,
        ) as scaffold_mock,
    ):
        _prefix, meta = run_builder_happy_path_hook(
            workspace_id="ws_h",
            project_id="proj_h",
            session_id="sess_h",
            last_user_plain="build me a tetris game",
            ham_actor=_byo_actor(),
        )
    scaffold_mock.assert_called_once()
    assert meta.get("builder_harness_first") is None


def test_explicit_quick_preview_allows_internal_scaffold(
    _empty_store: BuilderSourceStore,
) -> None:
    sentinel = {
        "builder_intent": "build_or_create",
        "builder_operation": "build_or_create",
        "scaffolded": False,
        "deduplicated": False,
    }
    with (
        patch(
            "src.ham.builder_chat_hooks.premium_harness_available_for_build",
            return_value=True,
        ),
        patch(
            "src.ham.builder_chat_scaffold.maybe_chat_scaffold_for_turn",
            return_value=sentinel,
        ) as scaffold_mock,
    ):
        _prefix, meta = run_builder_happy_path_hook(
            workspace_id="ws_h",
            project_id="proj_h",
            session_id="sess_h",
            last_user_plain="build me a tetris game, just a quick preview",
            ham_actor=_byo_actor(),
        )
    scaffold_mock.assert_called_once()
    assert meta.get("builder_harness_first") is None


def test_harness_first_reply_exposes_no_internals(
    _empty_store: BuilderSourceStore,
) -> None:
    with (
        patch(
            "src.ham.builder_chat_hooks.premium_harness_available_for_build",
            return_value=True,
        ),
        patch(
            "src.ham.builder_chat_scaffold.maybe_chat_scaffold_for_turn",
            side_effect=_raise_if_called,
        ),
    ):
        prefix, meta = run_builder_happy_path_hook(
            workspace_id="ws_h",
            project_id="proj_h",
            session_id="sess_h",
            last_user_plain="build me a tetris game",
            ham_actor=_byo_actor(),
        )
    haystack = f"{prefix}\n{json.dumps(meta, default=str)}".lower()
    for token in _FORBIDDEN_TOKENS:
        assert token not in haystack, f"harness-first reply leaked internal token {token!r}"


def test_premium_harness_available_true_when_a_premium_provider_is_ready() -> None:
    readiness = WorkspaceReadiness(
        is_operator=False,
        providers=(
            ProviderReadiness(provider="no_agent", available=True, blockers=()),
            ProviderReadiness(provider="opencode_cli", available=True, blockers=()),
        ),
        project=ProjectFlags(found=True, project_id="proj_h", output_target="managed_workspace"),
    )
    with (
        patch(
            "src.api.coding_agent_access_settings.load_workspace_agent_policy",
            return_value=None,
        ),
        patch("src.ham.coding_router.collate_readiness", return_value=readiness),
    ):
        assert (
            premium_harness_available_for_build(
                workspace_id="ws_h", project_id="proj_h", ham_actor=_byo_actor()
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
            # claude_code is a premium product name but never an eligible build harness.
            ProviderReadiness(provider="claude_code", available=False, blockers=("Planned.",)),
        ),
        project=ProjectFlags(found=True, project_id="proj_h", output_target="managed_workspace"),
    )
    with (
        patch(
            "src.api.coding_agent_access_settings.load_workspace_agent_policy",
            return_value=None,
        ),
        patch("src.ham.coding_router.collate_readiness", return_value=readiness),
    ):
        assert (
            premium_harness_available_for_build(
                workspace_id="ws_h", project_id="proj_h", ham_actor=_byo_actor()
            )
            is False
        )
