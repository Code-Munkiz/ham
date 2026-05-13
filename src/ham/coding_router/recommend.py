"""Pure recommender for the HAM Coding Router (Phase 1).

Takes a classified :class:`CodingTask`, a :class:`WorkspaceReadiness`
snapshot, and a :class:`ProjectFlags` row and returns a ranked list of
:class:`Candidate` rows with reasons + blockers.

Properties locked by tests:

- The recommender NEVER reads env, NEVER opens sockets, NEVER imports
  provider clients. All inputs are pre-collated.
- The output NEVER references ``safe_edit_low``, ``--auto low``, argv,
  runner URLs, ``HAM_DROID_EXEC_TOKEN``, or any other env-name string.
- A candidate with ``blockers`` is still returned (so the future chat card
  can render "Recommended, but blocked because…"); the ranker just demotes
  it below approve-able candidates.
- ``unknown`` task kinds never produce a confident recommendation; they
  fall through to ``no_agent`` with low confidence and the calling layer is
  expected to ask the user to pick.
"""

from __future__ import annotations

from src.ham.coding_router.types import (
    Candidate,
    CodingTask,
    ProjectFlags,
    ProviderKind,
    ProviderReadiness,
    WorkspaceReadiness,
)

# Reasons (human-facing copy). These appear in candidate.reason and never
# leak provider internals.
_REASON: dict[ProviderKind, str] = {
    "no_agent": "Conversational; no repository work needed.",
    "factory_droid_audit": "Read-only audit; no risk to the repository.",
    "factory_droid_build": "Low-risk pull request with a minimal diff.",
    "cursor_cloud": "Repo-wide context; opens a pull request you review.",
    "claude_code": "Single-file local edit handled directly on this host.",
    "claude_agent": "Disabled provider (visible for transparency).",
}

# Static safety flags per provider (kept here, not in readiness, because
# they're policy, not infra). These are surfaced to the chat card.
_SAFETY: dict[ProviderKind, dict[str, bool]] = {
    "no_agent": {
        "requires_operator": False,
        "requires_confirmation": False,
        "will_open_pull_request": False,
    },
    "factory_droid_audit": {
        "requires_operator": False,
        "requires_confirmation": True,
        "will_open_pull_request": False,
    },
    "factory_droid_build": {
        "requires_operator": True,
        "requires_confirmation": True,
        "will_open_pull_request": True,
    },
    "cursor_cloud": {
        "requires_operator": False,
        "requires_confirmation": True,
        "will_open_pull_request": True,
    },
    "claude_code": {
        "requires_operator": False,
        "requires_confirmation": True,
        "will_open_pull_request": False,
    },
    "claude_agent": {
        "requires_operator": True,
        "requires_confirmation": True,
        "will_open_pull_request": False,
    },
}

# Default base confidence per (task_kind, provider) cell. Cells absent from
# this table are not eligible candidates for that task kind.
_BASE_CONFIDENCE: dict[str, dict[ProviderKind, float]] = {
    "explain": {
        "no_agent": 0.9,
        "claude_code": 0.55,
    },
    "audit": {
        "factory_droid_audit": 0.85,
    },
    "security_review": {
        "factory_droid_audit": 0.85,
    },
    "architecture_report": {
        "factory_droid_audit": 0.85,
    },
    "doc_fix": {
        "factory_droid_build": 0.8,
        "cursor_cloud": 0.55,
    },
    "comments_only": {
        "factory_droid_build": 0.8,
        "cursor_cloud": 0.55,
    },
    "format_only": {
        "factory_droid_build": 0.8,
    },
    "typo_only": {
        "factory_droid_build": 0.85,
    },
    "feature": {
        "cursor_cloud": 0.8,
    },
    "fix": {
        "cursor_cloud": 0.7,
        "claude_code": 0.5,
    },
    "refactor": {
        "cursor_cloud": 0.8,
    },
    "multi_file_edit": {
        "cursor_cloud": 0.85,
    },
    "single_file_edit": {
        "claude_code": 0.7,
        "cursor_cloud": 0.5,
    },
    "unknown": {
        "no_agent": 0.4,
    },
}


def _readiness_for(readiness: WorkspaceReadiness, provider: ProviderKind) -> ProviderReadiness:
    for p in readiness.providers:
        if p.provider == provider:
            return p
    return ProviderReadiness(provider=provider, available=False, blockers=())


def _candidate(
    *,
    provider: ProviderKind,
    base_confidence: float,
    readiness: ProviderReadiness,
    extra_blockers: tuple[str, ...] = (),
    project: ProjectFlags | None = None,
) -> Candidate:
    blockers: list[str] = []
    blockers.extend(readiness.blockers)
    blockers.extend(extra_blockers)
    safety = dict(_SAFETY[provider])
    # Managed-workspace Factory Droid Build never opens a GitHub PR and
    # never requires the global workspace-operator role — workspace
    # owners/admins approve their own builds from the chat plan card.
    if provider == "factory_droid_build" and project is not None:
        target = (project.output_target or "managed_workspace").strip()
        if target == "managed_workspace":
            safety["will_open_pull_request"] = False
            safety["requires_operator"] = False
    return Candidate(
        provider=provider,
        confidence=base_confidence,
        reason=_REASON[provider],
        blockers=tuple(blockers),
        requires_operator=safety["requires_operator"],
        requires_confirmation=safety["requires_confirmation"],
        will_open_pull_request=safety["will_open_pull_request"],
    )


def _project_blockers_for(provider: ProviderKind, project: ProjectFlags) -> tuple[str, ...]:
    """Return task-specific blockers for a provider given current project flags."""
    blockers: list[str] = []
    if provider in ("factory_droid_audit",) and not project.found:
        blockers.append("Pick a project before launching an audit.")
    if provider == "cursor_cloud":
        if not project.found:
            blockers.append("Pick a project before launching a Cursor mission.")
        elif not project.has_github_repo:
            blockers.append("This project has no GitHub repository configured.")
    if provider == "factory_droid_build":
        if not project.found:
            blockers.append("Pick a project before launching a build.")
        else:
            if not project.build_lane_enabled:
                blockers.append(
                    "Build lane is disabled for this project. A workspace owner or admin "
                    "must enable it in project settings."
                )
            target = (project.output_target or "managed_workspace").strip()
            if target == "github_pr":
                if not project.has_github_repo:
                    blockers.append("This project has no GitHub repository configured.")
            elif target == "managed_workspace":
                if not project.has_workspace_id:
                    blockers.append(
                        "This project has no managed workspace assigned yet. "
                        "Pick a workspace before building."
                    )
    return tuple(blockers)


def _approveable_first(c: Candidate) -> tuple[int, float]:
    """Sort key: approve-able candidates first, then by confidence (descending)."""
    blocked = 1 if c.blockers else 0
    return (blocked, -c.confidence)


def recommend(
    task: CodingTask,
    readiness: WorkspaceReadiness,
    project: ProjectFlags | None = None,
) -> list[Candidate]:
    """Return a ranked list of :class:`Candidate` rows for ``task``.

    The first element is the recommended provider for the chat card. Callers
    that want to display alternatives can show the rest. Candidates with
    non-empty ``blockers`` are demoted but still returned so the UI can
    render them with a "blocked because…" pill.
    """
    proj = project if project is not None else readiness.project
    table = _BASE_CONFIDENCE.get(task.kind, {})

    out: list[Candidate] = []
    for provider, base in table.items():
        pr = _readiness_for(readiness, provider)
        extra = _project_blockers_for(provider, proj)
        out.append(
            _candidate(
                provider=provider,
                base_confidence=base,
                readiness=pr,
                extra_blockers=extra,
                project=proj,
            )
        )

    # Always offer no_agent as a conversational fallback when nothing else
    # would be approve-able. This ensures the chat card always has something
    # to render even on a totally unconfigured host.
    if not any(c.provider == "no_agent" for c in out):
        out.append(
            _candidate(
                provider="no_agent",
                base_confidence=0.3,
                readiness=_readiness_for(readiness, "no_agent"),
                extra_blockers=(),
                project=proj,
            )
        )

    out.sort(key=_approveable_first)
    return out


__all__ = ["recommend"]
