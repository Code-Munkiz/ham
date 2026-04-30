"""Contracts for deterministic Cloud Agent launch prompt hygiene."""

from src.ham.cursor_agent_workflow import (
    CURSOR_AGENT_BASE_REVISION,
    append_cloud_agent_pr_hygiene,
    build_managed_cloud_agent_prompt_py,
    cloud_agent_pr_hygiene_block,
    compose_prompt_for_cursor,
)


def test_cursor_agent_base_revision_bumped_for_prompt_contract() -> None:
    assert CURSOR_AGENT_BASE_REVISION == "cursor-agent-v2"


def test_managed_launch_prompt_contains_pr_hygiene_phrases() -> None:
    p = build_managed_cloud_agent_prompt_py(
        user_prompt="fix typo",
        repository="https://github.com/org/ham",
        ref="main",
    )
    assert "Do not open a PR unless the user explicitly requests it." in p
    assert "OVERLAPPING_DOCS_PR_FOUND" in p
    assert "gh pr list --repo" in p
    assert "cursor-agent-v2" not in p  # base revision metadata is UI-side digest, not echo'd in prose


def test_hygiene_block_includes_overlap_token() -> None:
    blk = cloud_agent_pr_hygiene_block(repository="https://github.com/a/b", ref=None)
    assert "OVERLAPPING_DOCS_PR_FOUND" in blk
    assert "mission_registry_id" in blk


def test_direct_prompt_appended_hygiene() -> None:
    core = compose_prompt_for_cursor(task_prompt="hello", expected_deliverable=None)
    out = append_cloud_agent_pr_hygiene(core, repository="https://github.com/o/r", ref="develop")
    assert core.strip() in out
    assert "Do not open a PR unless the user explicitly requests it." in out
