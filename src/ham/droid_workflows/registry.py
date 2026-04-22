"""Versioned allowlisted Droid workflow definitions — source of truth for policy."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

REGISTRY_REVISION = "2026-02-11-v1"


class DroidWorkflowDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    workflow_id: str = Field(min_length=1, max_length=64)
    description: str = Field(max_length=2000)
    tier: Literal["readonly", "low_edit"]
    mutates: bool
    requires_confirmation: bool = True
    requires_launch_token: bool
    cwd_rule: Literal["project_root"] = "project_root"
    output_format: Literal["json"] = "json"
    timeout_seconds: int = Field(default=300, ge=30, le=3600)
    prompt_template: str = Field(
        min_length=10,
        max_length=20_000,
        description="Must include {user_focus} placeholder.",
    )
    auto_level: Literal["low"] | None = None
    disabled_tools: tuple[str, ...] = ()
    custom_droid_name: str | None = Field(default=None, max_length=128)


_WORKFLOWS: dict[str, DroidWorkflowDefinition] = {
    "readonly_repo_audit": DroidWorkflowDefinition(
        workflow_id="readonly_repo_audit",
        description=(
            "Read-only repository audit: structure, risks, and recommendations without "
            "mutations. Uses droid exec without --auto."
        ),
        tier="readonly",
        mutates=False,
        requires_launch_token=False,
        cwd_rule="project_root",
        output_format="json",
        timeout_seconds=420,
        prompt_template=(
            "Perform a read-only audit of this repository.\n\n"
            "Focus:\n{user_focus}\n\n"
            "Use only read operations. Summarize architecture, key modules, and any "
            "correctness or security observations. Do not modify files or run mutating commands."
        ),
        auto_level=None,
        disabled_tools=(),
        custom_droid_name=None,
    ),
    "safe_edit_low": DroidWorkflowDefinition(
        workflow_id="safe_edit_low",
        description=(
            "Low-risk local edits (documentation, comments, formatting) with "
            "droid exec --auto low. Requires preview, confirmation, and HAM_DROID_EXEC_TOKEN."
        ),
        tier="low_edit",
        mutates=True,
        requires_confirmation=True,
        requires_launch_token=True,
        cwd_rule="project_root",
        output_format="json",
        timeout_seconds=600,
        prompt_template=(
            "Make small, low-risk improvements only (documentation, comments, typos, "
            "non-behavioral formatting). Do not change business logic, dependencies, or "
            "CI configuration unless explicitly required by the focus below.\n\n"
            "Focus:\n{user_focus}\n\n"
            "Prefer minimal diffs. Report what you changed."
        ),
        auto_level="low",
        disabled_tools=(),
        custom_droid_name=None,
    ),
}


def get_workflow(workflow_id: str) -> DroidWorkflowDefinition | None:
    return _WORKFLOWS.get(workflow_id.strip())


def list_workflow_ids() -> list[str]:
    return sorted(_WORKFLOWS.keys())
