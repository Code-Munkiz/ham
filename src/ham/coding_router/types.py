"""Shared types for the HAM Coding Router (Phase 1).

These dataclasses are deliberately minimal and frozen. They never carry secret
values; readiness collation always reduces a secret presence check to a
``bool`` before reaching this module.

Provider kinds are stable strings used in API responses; renaming is a
breaking change. Task kinds drive the recommender table and may grow over
time without breaking older clients (they're internal to HAM, but appear in
the public readiness/preview responses as enum-shaped strings).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ProviderKind = Literal[
    "no_agent",
    "factory_droid_audit",
    "factory_droid_build",
    "cursor_cloud",
    "claude_code",
]

TaskKind = Literal[
    "explain",
    "audit",
    "security_review",
    "architecture_report",
    "doc_fix",
    "comments_only",
    "format_only",
    "typo_only",
    "single_file_edit",
    "feature",
    "fix",
    "refactor",
    "multi_file_edit",
    "unknown",
]


@dataclass(frozen=True)
class CodingTask:
    """Classified user request.

    ``confidence`` is a coarse 0.0-1.0 signal; callers that need a hard
    threshold should compare against ``CONFIDENCE_LOW`` and treat anything
    below it as ``unknown``.
    """

    user_prompt: str
    project_id: str | None
    kind: TaskKind
    confidence: float
    matched_pattern: str | None = None


@dataclass(frozen=True)
class ProjectFlags:
    """Presence-only project signals used by the recommender.

    None of these fields carry secret values. ``has_github_repo`` is a bool
    derived from ``ProjectRecord.github_repo`` and never echoes the repo name.
    ``output_target`` is the project's configured Build Lane output target
    ("managed_workspace" or "github_pr") and lets the recommender pick the
    right blocker copy (managed projects do not need a GitHub repo).
    """

    found: bool
    project_id: str | None
    build_lane_enabled: bool = False
    has_github_repo: bool = False
    output_target: str | None = None
    has_workspace_id: bool = False


@dataclass(frozen=True)
class ProviderReadiness:
    """Readiness of a single provider on this API host + workspace.

    ``blockers`` are normie-safe human strings — they never include env names,
    secret values, internal workflow ids, runner URLs, or argv. ``operator_signals``
    are populated only when the readiness collator is invoked with
    ``include_operator_details=True`` and are stripped from non-operator API
    responses by ``WorkspaceReadiness.public_dict``.
    """

    provider: ProviderKind
    available: bool
    blockers: tuple[str, ...] = ()
    operator_signals: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkspaceReadiness:
    """Aggregated readiness for the conductor / readiness endpoint."""

    is_operator: bool
    providers: tuple[ProviderReadiness, ...]
    project: ProjectFlags

    def public_dict(self) -> dict[str, Any]:
        return {
            "is_operator": self.is_operator,
            "providers": [
                {
                    "provider": p.provider,
                    "available": p.available,
                    "blockers": list(p.blockers),
                    **({"operator_signals": list(p.operator_signals)} if self.is_operator else {}),
                }
                for p in self.providers
            ],
            "project": {
                "found": self.project.found,
                "project_id": self.project.project_id,
                "build_lane_enabled": self.project.build_lane_enabled,
                "has_github_repo": self.project.has_github_repo,
                "output_target": self.project.output_target,
                "has_workspace_id": self.project.has_workspace_id,
            },
        }


@dataclass(frozen=True)
class Candidate:
    """Recommender output row.

    ``blockers`` mirrors :class:`ProviderReadiness.blockers` and is also
    extended with task-specific blockers (e.g. project missing GitHub repo).
    A candidate with non-empty ``blockers`` is **not approve-able**; the
    future chat card renders it as "Recommended, but blocked because…".
    """

    provider: ProviderKind
    confidence: float
    reason: str
    blockers: tuple[str, ...] = field(default_factory=tuple)
    requires_operator: bool = False
    requires_confirmation: bool = False
    will_open_pull_request: bool = False


__all__ = [
    "Candidate",
    "CodingTask",
    "ProjectFlags",
    "ProviderKind",
    "ProviderReadiness",
    "TaskKind",
    "WorkspaceReadiness",
]
