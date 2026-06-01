"""Defense-in-depth: ``run_builder_happy_path_hook`` must not scaffold for explicit no-build prompts."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.ham.builder_chat_hooks import run_builder_happy_path_hook
from src.ham.clerk_auth import HamActor
from src.persistence.builder_source_store import (
    BuilderSourceStore,
    set_builder_source_store_for_tests,
)


def _byo_actor(uid: str = "user_no_build") -> HamActor:
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
    raise AssertionError("maybe_chat_scaffold_for_turn must not run for plan-only prompts")


@pytest.fixture
def _empty_store(tmp_path):
    store = BuilderSourceStore(store_path=tmp_path / "sources.json")
    set_builder_source_store_for_tests(store)
    try:
        yield store
    finally:
        set_builder_source_store_for_tests(None)


@pytest.mark.parametrize(
    "phrase",
    [
        "build me a landing page but don't build it yet",
        "just plan it for now",
        "talk through it before building",
    ],
)
def test_explicit_no_build_phrase_does_not_invoke_scaffold(
    _empty_store: BuilderSourceStore,
    phrase: str,
) -> None:
    with patch(
        "src.ham.builder_chat_scaffold.maybe_chat_scaffold_for_turn",
        side_effect=_raise_if_called,
    ) as scaffold_mock:
        prefix, meta = run_builder_happy_path_hook(
            workspace_id="ws_no_build",
            project_id="proj_no_build",
            session_id="sess_no_build",
            last_user_plain=phrase,
            ham_actor=_byo_actor(),
        )
    assert prefix is None
    assert meta.get("builder_intent") == "plan_only"
    scaffold_mock.assert_not_called()


def test_positive_control_build_phrase_routes_to_selection_not_scaffold(
    _empty_store: BuilderSourceStore,
) -> None:
    """A normal build phrase is recognized as a build and routed to HAM Native
    when there is no external selection/default; it does NOT silently run the
    internal scaffold."""
    with (
        patch(
            "src.ham.builder_chat_hooks._selected_builder_for_workspace",
            return_value=None,
        ),
        patch(
            "src.ham.builder_chat_hooks.configured_default_builder",
            return_value=None,
        ),
        patch(
            "src.ham.builder_native_hermes.start_native_build_job",
            return_value={
                "builder_intent": "build_or_create",
                "builder_operation": "build_or_create",
                "scaffolded": False,
                "ham_native_builder": {"status": "unavailable"},
            },
        ),
        patch(
            "src.ham.builder_chat_scaffold.maybe_chat_scaffold_for_turn",
            side_effect=_raise_if_called,
        ) as scaffold_mock,
    ):
        prefix, meta = run_builder_happy_path_hook(
            workspace_id="ws_positive",
            project_id="proj_positive",
            session_id="sess_positive",
            last_user_plain="build me a landing page",
            ham_actor=_byo_actor(),
        )
    scaffold_mock.assert_not_called()
    assert meta.get("selected_builder_state") == "native"
    assert meta.get("ham_native_builder", {}).get("status") == "unavailable"
    assert isinstance(prefix, str) and prefix.strip()
