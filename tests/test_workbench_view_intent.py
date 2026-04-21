"""Server-side workbench header mode inference for UI action augmentation."""

from __future__ import annotations

from src.ham.workbench_view_intent import (
    augment_workbench_view_actions,
    infer_workbench_view_mode,
)


def test_infer_split_phrases() -> None:
    assert infer_workbench_view_mode("show me the split view") == "split"
    assert infer_workbench_view_mode("Switch to split please") == "split"


def test_infer_preview_and_war_room() -> None:
    assert infer_workbench_view_mode("open preview mode") == "preview"
    assert infer_workbench_view_mode("show me the preview screen") == "preview"
    assert infer_workbench_view_mode("go to war room") == "war_room"


def test_no_match_for_ui_description_only() -> None:
    """Listing toolbar labels must not imply a mode switch."""
    text = (
        "the workbench header toolbar with War Room, Preview, and Split buttons — "
        "that one's on you to click"
    )
    assert infer_workbench_view_mode(text) is None


def test_negation_skips() -> None:
    assert infer_workbench_view_mode("don't switch to split view") is None


def test_augment_prepends_when_model_omitted() -> None:
    actions = augment_workbench_view_actions(
        "show me split view",
        [{"type": "toast", "level": "info", "message": "x"}],
        enable_ui_actions=True,
    )
    assert actions[0] == {"type": "set_workbench_view", "mode": "split"}
    assert len(actions) == 2


def test_augment_idempotent_if_model_emitted() -> None:
    existing = [{"type": "set_workbench_view", "mode": "preview"}]
    actions = augment_workbench_view_actions(
        "show split view",
        existing,
        enable_ui_actions=True,
    )
    assert actions == existing


def test_augment_respects_enable_flag() -> None:
    actions = augment_workbench_view_actions(
        "show split view",
        [],
        enable_ui_actions=False,
    )
    assert actions == []
