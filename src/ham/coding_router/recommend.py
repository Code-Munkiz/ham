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

import os
from typing import TYPE_CHECKING

from src.ham.coding_router.types import (
    Candidate,
    CodingTask,
    PreferenceMode,
    ProjectFlags,
    ProviderKind,
    ProviderReadiness,
    WorkspaceAgentPolicy,
    WorkspaceReadiness,
)

if TYPE_CHECKING:
    from src.ham.custom_builder.profile import CustomBuilderProfile


def _truthy_env(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


# Reasons (human-facing copy). These appear in candidate.reason and never
# leak provider internals.
_REASON: dict[ProviderKind, str] = {
    "no_agent": "Conversational; no repository work needed.",
    "factory_droid_audit": "Read-only audit; no risk to the repository.",
    "factory_droid_build": "Low-risk pull request with a minimal diff.",
    "cursor_cloud": "Repo-wide context; opens a pull request you review.",
    "claude_code": "Single-file local edit handled directly on this host.",
    "claude_agent": "Managed workspace edit handled by Claude Agent using premium reasoning.",
    "opencode_cli": "OpenCode managed-workspace edit using your own model.",
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
        "requires_operator": False,
        "requires_confirmation": True,
        "will_open_pull_request": False,
    },
    "opencode_cli": {
        "requires_operator": False,
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
        "opencode_cli": 0.45,
    },
    "comments_only": {
        "factory_droid_build": 0.8,
        "cursor_cloud": 0.55,
        "opencode_cli": 0.45,
    },
    "format_only": {
        "factory_droid_build": 0.8,
        "opencode_cli": 0.45,
    },
    "typo_only": {
        "factory_droid_build": 0.85,
        "opencode_cli": 0.45,
    },
    # Build / code-mutation tasks.
    # Cursor leads for connected-repo (github_pr) projects where a repo is
    # configured.  OpenCode is the default open builder for managed_workspace
    # projects when platform readiness + model access + workspace policy allow
    # it.  Claude Agent is a meaningful alternative when prefer_premium_reasoning
    # is active; its preference boost then lifts it above OpenCode.
    "feature": {
        "cursor_cloud": 0.8,
        "opencode_cli": 0.65,  # default open managed-workspace builder
        "claude_agent": 0.6,  # meaningful for prefer_premium_reasoning
    },
    "fix": {
        "cursor_cloud": 0.7,
        "opencode_cli": 0.6,  # default open managed-workspace fixer
        "claude_agent": 0.55,  # meaningful for prefer_premium_reasoning
        "claude_code": 0.5,
    },
    "refactor": {
        "cursor_cloud": 0.8,
        "opencode_cli": 0.65,  # default open managed-workspace refactorer
        "claude_agent": 0.55,  # meaningful for prefer_premium_reasoning
    },
    "multi_file_edit": {
        "cursor_cloud": 0.85,
        "opencode_cli": 0.65,  # default open managed-workspace multi-file editor
        "claude_agent": 0.5,  # meaningful for prefer_premium_reasoning
    },
    "single_file_edit": {
        "claude_code": 0.7,
        "claude_agent": 0.6,
        "cursor_cloud": 0.5,
        "opencode_cli": 0.5,  # slightly raised; competitive for managed-workspace
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
    if provider == "opencode_cli":
        blockers.extend(_opencode_project_blockers(project))
    return tuple(blockers)


def _opencode_project_blockers(project: ProjectFlags) -> list[str]:
    """OpenCode-specific project blockers; mirrors Factory Droid Build."""
    blockers: list[str] = []
    if not project.found:
        blockers.append("Pick a project before launching an OpenCode build.")
        return blockers
    target = (project.output_target or "managed_workspace").strip()
    if target != "managed_workspace":
        blockers.append(
            "OpenCode requires a managed workspace project; this project "
            "opens GitHub pull requests instead."
        )
    elif not project.has_workspace_id:
        blockers.append(
            "This project has no managed workspace assigned yet. Pick a workspace before building."
        )
    if not project.build_lane_enabled:
        blockers.append(
            "Build lane is disabled for this project. A workspace owner or admin "
            "must enable it in project settings."
        )
    return blockers


def _approveable_first(c: Candidate) -> tuple[int, float]:
    """Sort key: approve-able candidates first, then by confidence (descending)."""
    blocked = 1 if c.blockers else 0
    return (blocked, -c.confidence)


# Confidence boost applied to the preferred provider kind per preference_mode.
# Applied only to approve-able (unblocked) candidates; never bypasses blockers.
_PREFERENCE_BOOST: dict[PreferenceMode, tuple[ProviderKind, float]] = {
    "prefer_open_custom": ("opencode_cli", 0.15),
    "prefer_premium_reasoning": ("claude_agent", 0.15),
    "prefer_connected_repo": ("cursor_cloud", 0.15),
}


def _apply_preference_boosts(
    candidates: list[Candidate],
    workspace_policy: WorkspaceAgentPolicy | None,
) -> list[Candidate]:
    """Adjust confidence of the preferred provider kind without bypassing blockers.

    ``recommended`` mode (and absent policy) applies no boost — let platform
    readiness and task-fit confidence decide. Other modes add a small boost to
    the nominated provider kind so it surfaces first among approve-able options.

    For ``prefer_open_custom``: in addition to boosting the bare ``opencode_cli``
    candidate, the single best-matching unblocked custom-builder candidate
    (highest current confidence) receives an extra ``+0.05`` so a strong tag
    match can promote a builder above its bare lane.
    """
    if workspace_policy is None or workspace_policy.preference_mode == "recommended":
        return candidates

    boost_spec = _PREFERENCE_BOOST.get(workspace_policy.preference_mode)
    if boost_spec is None:
        return candidates

    target_provider, boost = boost_spec
    result: list[Candidate] = []
    for c in candidates:
        if c.provider == target_provider and not c.blockers and c.builder_id is None:
            result.append(_with_confidence(c, min(1.0, c.confidence + boost)))
        else:
            result.append(c)

    if workspace_policy.preference_mode == "prefer_open_custom":
        result = _apply_prefer_open_custom_builder_boost(result)
    return result


def _apply_prefer_open_custom_builder_boost(
    candidates: list[Candidate],
) -> list[Candidate]:
    """Give the single best unblocked builder candidate an extra +0.05."""
    best_index = -1
    best_confidence = -1.0
    for i, c in enumerate(candidates):
        if c.builder_id is None or c.blockers:
            continue
        if c.confidence > best_confidence:
            best_confidence = c.confidence
            best_index = i
    if best_index < 0:
        return candidates
    boosted = list(candidates)
    target = boosted[best_index]
    boosted[best_index] = _with_confidence(target, min(1.0, target.confidence + 0.05))
    return boosted


def _with_confidence(c: Candidate, new_confidence: float) -> Candidate:
    return Candidate(
        provider=c.provider,
        confidence=new_confidence,
        reason=c.reason,
        blockers=c.blockers,
        requires_operator=c.requires_operator,
        requires_confirmation=c.requires_confirmation,
        will_open_pull_request=c.will_open_pull_request,
        builder_id=c.builder_id,
        builder_name=c.builder_name,
    )


def recommend(
    task: CodingTask,
    readiness: WorkspaceReadiness,
    project: ProjectFlags | None = None,
    workspace_policy: WorkspaceAgentPolicy | None = None,
    *,
    custom_builders: list[CustomBuilderProfile] | None = None,
) -> list[Candidate]:
    """Return a ranked list of :class:`Candidate` rows for ``task``.

    The first element is the recommended provider for the chat card. Callers
    that want to display alternatives can show the rest. Candidates with
    non-empty ``blockers`` are demoted but still returned so the UI can
    render them with a "blocked because…" pill.

    ``workspace_policy`` carries the workspace's allow/deny flags and
    preference mode. When ``None``, no policy boosts are applied and all
    platform-ready providers are considered (pre-settings behavior).

    ``custom_builders`` are enabled workspace custom-builder profiles (PR 4).
    When ``None`` or empty, behaviour is unchanged. Otherwise each matching
    enabled profile may emit an additional ``opencode_cli``-backed candidate
    that inherits the bare lane's blockers, with a tag-driven confidence boost
    capped at ``+0.15``.
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

    out = _demote_opencode_when_ineligible(out, readiness, proj)
    out = _emit_custom_builder_candidates(out, task, workspace_policy, custom_builders)
    out = _apply_preference_boosts(out, workspace_policy)
    out.sort(key=_approveable_first)
    return out


_MAX_BUILDER_CANDIDATES = 3
_BUILDER_TAG_BOOST_STEP = 0.05
_BUILDER_TAG_BOOST_CAP = 0.15
_BUILDER_POLICY_DISABLED_BLOCKER = "OpenCode is disabled by workspace policy."


def _match_intent_tags(profile: CustomBuilderProfile, prompt: str) -> list[str]:
    """Return profile intent_tags that appear (case-insensitive substring) in ``prompt``."""
    lowered = prompt.lower()
    matches: list[str] = []
    for tag in profile.intent_tags:
        if not tag:
            continue
        if tag.lower() in lowered:
            matches.append(tag)
    return matches


def _builder_qualifies(
    profile: CustomBuilderProfile, task: CodingTask, tag_matches: list[str]
) -> bool:
    if not profile.enabled:
        return False
    if profile.preferred_harness != "opencode_cli":
        return False
    if "opencode_cli" not in profile.allowed_harnesses:
        return False
    if profile.task_kinds:
        return task.kind in profile.task_kinds
    return len(tag_matches) > 0


def _emit_custom_builder_candidates(
    out: list[Candidate],
    task: CodingTask,
    workspace_policy: WorkspaceAgentPolicy | None,
    custom_builders: list[CustomBuilderProfile] | None,
) -> list[Candidate]:
    """Append at most three custom-builder candidates that piggy-back on opencode_cli."""
    if not custom_builders:
        return out
    base = _BASE_CONFIDENCE.get(task.kind, {}).get("opencode_cli")
    if base is None:
        return out

    bare = next((c for c in out if c.provider == "opencode_cli" and c.builder_id is None), None)
    if bare is None:
        return out

    safety = _SAFETY["opencode_cli"]
    bare_blockers = list(bare.blockers)
    policy_blocker_needed = (
        workspace_policy is not None and workspace_policy.allow_opencode is False
    )

    scored: list[tuple[float, str, Candidate]] = []
    for profile in custom_builders:
        tag_matches = _match_intent_tags(profile, task.user_prompt)
        if not _builder_qualifies(profile, task, tag_matches):
            continue

        blockers: list[str] = list(bare_blockers)
        if policy_blocker_needed and _BUILDER_POLICY_DISABLED_BLOCKER not in blockers:
            blockers.append(_BUILDER_POLICY_DISABLED_BLOCKER)

        if blockers:
            confidence = base
        else:
            boost = min(_BUILDER_TAG_BOOST_CAP, len(tag_matches) * _BUILDER_TAG_BOOST_STEP)
            confidence = min(1.0, base + boost)

        reason = f"{profile.name} — custom builder running on managed OpenCode."
        candidate = Candidate(
            provider="opencode_cli",
            confidence=confidence,
            reason=reason,
            blockers=tuple(blockers),
            requires_operator=safety["requires_operator"],
            requires_confirmation=safety["requires_confirmation"],
            will_open_pull_request=safety["will_open_pull_request"],
            builder_id=profile.builder_id,
            builder_name=profile.name,
        )
        scored.append((confidence, profile.builder_id, candidate))

    if not scored:
        return out

    scored.sort(key=lambda row: (-row[0], row[1]))
    return out + [row[2] for row in scored[:_MAX_BUILDER_CANDIDATES]]


def _demote_opencode_when_ineligible(
    candidates: list[Candidate],
    readiness: WorkspaceReadiness,
    project: ProjectFlags,
) -> list[Candidate]:
    """Ensure ``opencode_cli`` has blockers when ineligible; keep it in the list.

    OpenCode is fully eligible only when **all** of the following are true:

    - ``HAM_OPENCODE_ENABLED`` is truthy
    - ``HAM_OPENCODE_EXECUTION_ENABLED`` is truthy
    - the opencode_cli readiness row reports ``available=True``
    - the project's ``output_target`` is ``managed_workspace``

    When ineligible, the candidate stays in the list with at least one
    eligibility blocker so the chat card can render "blocked because…" copy
    rather than silently hiding OpenCode. In production the readiness row
    and project-blocker helpers already supply the right blockers, so this
    function only needs to add a fallback gate-level blocker when no other
    blocker is present (defence-in-depth for manually constructed snapshots).
    """
    gate_enabled = _truthy_env("HAM_OPENCODE_ENABLED")
    execution_enabled = _truthy_env("HAM_OPENCODE_EXECUTION_ENABLED")
    oc_row = _readiness_for(readiness, "opencode_cli")
    target = (project.output_target or "").strip()

    if gate_enabled and execution_enabled and oc_row.available and target == "managed_workspace":
        return candidates

    result: list[Candidate] = []
    for c in candidates:
        if c.provider != "opencode_cli":
            result.append(c)
            continue
        if c.blockers:
            # Blockers already supplied by readiness or project helpers; keep as-is.
            result.append(c)
            continue
        # Defence-in-depth: add a gate-level blocker when none is present.
        blocker = (
            "OpenCode is not enabled for this host yet."
            if not (gate_enabled and execution_enabled)
            else "OpenCode is not ready for this project yet."
        )
        result.append(
            Candidate(
                provider=c.provider,
                confidence=c.confidence,
                reason=c.reason,
                blockers=(blocker,),
                requires_operator=c.requires_operator,
                requires_confirmation=c.requires_confirmation,
                will_open_pull_request=c.will_open_pull_request,
            )
        )
    return result


__all__ = ["recommend"]
