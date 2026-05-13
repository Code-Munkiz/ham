"""
Read-only harness capability registry (vocabulary only).

This module mirrors ``docs/HARNESS_PROVIDER_CONTRACT.md`` — no dispatch, no provider
runtime imports, and no Claude Code / OpenCode (or other) launch implementation.

The ``claude_code`` and ``opencode_cli`` rows stay ``planned_candidate`` until a
provider adapter PR lands. ``opencode_cli`` further depends on real-host verification
(``docs/OPENCODE_VERIFICATION.md``) and a go/conditional-go decision; do not treat
either as implemented in HAM before that.

Planned / candidate rows use ``registry_status=planned_candidate`` and ``implemented=False``;
``ControlPlaneRun`` / ``ControlPlaneProvider`` may not include such providers until wired.
See ``docs/CODING_AGENTS_CONTROL_PLANE.md`` for the cockpit-level vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, Mapping, TypeAlias

RegistryStatus: TypeAlias = Literal["implemented", "planned_candidate"]
HarnessFamily: TypeAlias = Literal[
    "remote_http_agent",
    "local_subprocess",
    "local_cli_planned",
]
AuditSinkLiteral: TypeAlias = Literal["cursor_jsonl", "droid_jsonl", "claude_agent_jsonl"]


@dataclass(frozen=True, slots=True)
class HarnessCapabilityRow:
    """Immutable registry row. Strings reference docs / module function names, not callables."""

    provider: str
    display_name: str
    harness_family: HarnessFamily
    registry_status: RegistryStatus
    # True: live HAM paths exist for this provider key (matches ControlPlaneProvider when applicable).
    implemented: bool
    requires_local_root: bool
    requires_remote_repo: bool
    supports_operator_preview: bool
    supports_operator_launch: bool
    supports_status_poll: bool
    # Cursor: true on REST follow-up / conversation *proxy* routes; not digest-gated in operator.
    supports_follow_up: bool
    returns_stable_external_id: bool
    # Cursor: Cursor API key. Droid: not required for readonly workflows. OpenCode: planned (CLI / LLM auth on host).
    requires_provider_side_auth: bool
    # Matches ``ControlPlaneProviderAuditRef.sink`` when present; None if not in CP yet.
    audit_sink: AuditSinkLiteral | None
    digest_family: str
    base_revision_source: str
    status_mapping: str
    topology_note: str


def _rows() -> dict[str, HarnessCapabilityRow]:
    return {
        "cursor_cloud_agent": HarnessCapabilityRow(
            provider="cursor_cloud_agent",
            display_name="Cursor Cloud Agent",
            harness_family="remote_http_agent",
            registry_status="implemented",
            implemented=True,
            requires_local_root=False,
            requires_remote_repo=True,
            supports_operator_preview=True,
            supports_operator_launch=True,
            supports_status_poll=True,
            # Follow-up and conversation: ``src/api/cursor_settings.py`` — not operator digest path.
            supports_follow_up=True,
            returns_stable_external_id=True,
            requires_provider_side_auth=True,
            audit_sink="cursor_jsonl",
            digest_family="compute_cursor_proposal_digest / CURSOR_AGENT_BASE_REVISION",
            base_revision_source="CURSOR_AGENT_BASE_REVISION in cursor_agent_workflow",
            status_mapping="map_cursor_raw_status (control_plane_run.py)",
            topology_note="Remote agent against GitHub URL; project_root on CP is optional mirror only.",
        ),
        "factory_droid": HarnessCapabilityRow(
            provider="factory_droid",
            display_name="Factory Droid (droid exec)",
            harness_family="local_subprocess",
            registry_status="implemented",
            implemented=True,
            requires_local_root=True,
            requires_remote_repo=False,
            supports_operator_preview=True,
            supports_operator_launch=True,
            # v1: launch-centric; not Cursor-style HTTP poll
            supports_status_poll=False,
            supports_follow_up=False,
            # session_id in runner JSON when present — not always
            returns_stable_external_id=True,
            # Local exec; not a cloud API key on the Droid "provider". Mutating flows use HAM_DROID_EXEC_TOKEN.
            requires_provider_side_auth=False,
            audit_sink="droid_jsonl",
            digest_family="compute_proposal_digest (preview_launch.py) + REGISTRY_REVISION",
            base_revision_source="REGISTRY_REVISION (droid_workflows/registry.py)",
            status_mapping="droid_outcome_to_ham_status (control_plane_run.py)",
            topology_note="Local droid exec on registered project root; allowlisted workflows.",
        ),
        "claude_code": HarnessCapabilityRow(
            provider="claude_code",
            display_name="Claude Code (planned)",
            harness_family="local_cli_planned",
            registry_status="planned_candidate",
            implemented=False,
            requires_local_root=True,
            requires_remote_repo=False,
            # Intended v1 per cockpit vocabulary — not launchable in HAM until implemented.
            # The existing claude_agent_sdk readiness path under src/api/workspace_tools.py
            # and src/ham/worker_adapters/claude_agent_adapter.py is workspace-tool readiness,
            # not a coding-agent control-plane provider.
            supports_operator_preview=False,
            supports_operator_launch=False,
            supports_status_poll=False,
            supports_follow_up=False,
            returns_stable_external_id=False,
            requires_provider_side_auth=True,
            audit_sink=None,
            digest_family="TBD (not wired)",
            base_revision_source="TBD (not wired)",
            status_mapping="TBD exit- or event-based; not map_cursor_raw_status",
            topology_note="Planned: local Claude Code CLI subprocess on a registered project root. "
            "Not in ControlPlaneProvider enum; no HAM runtime; not launchable.",
        ),
        "claude_agent": HarnessCapabilityRow(
            provider="claude_agent",
            display_name="Claude Agent",
            harness_family="local_subprocess",
            registry_status="implemented",
            implemented=True,
            requires_local_root=True,
            requires_remote_repo=False,
            supports_operator_preview=True,
            supports_operator_launch=True,
            supports_status_poll=False,
            supports_follow_up=False,
            returns_stable_external_id=True,
            requires_provider_side_auth=True,
            audit_sink="claude_agent_jsonl",
            digest_family="claude_agent_v1",
            base_revision_source="CLAUDE_AGENT_REGISTRY_REVISION",
            status_mapping="claude_agent_run_status_to_ham_status",
            topology_note=(
                "Implemented in-process via claude_agent_sdk Python; emits "
                "managed_workspace snapshots; gated by HAM_CLAUDE_AGENT_EXEC_TOKEN."
            ),
        ),
        "opencode_cli": HarnessCapabilityRow(
            provider="opencode_cli",
            display_name="OpenCode CLI (planned)",
            harness_family="local_cli_planned",
            registry_status="planned_candidate",
            implemented=False,
            requires_local_root=True,
            requires_remote_repo=False,
            # Intended v1 per architecture planning — not available in HAM until implemented;
            # operator preview / launch flags reflect the v1 intent only and stay gated by
            # ``implemented=False`` until a real adapter lands.
            supports_operator_preview=True,
            supports_operator_launch=True,
            supports_status_poll=False,
            supports_follow_up=False,
            returns_stable_external_id=False,
            requires_provider_side_auth=True,
            audit_sink=None,
            digest_family="TBD (not wired)",
            base_revision_source="TBD (not wired)",
            status_mapping="TBD exit- or event-based; not map_cursor_raw_status",
            topology_note="Planned: bounded subprocess (e.g. opencode run). No TUI/serve orchestration. "
            "Not in ControlPlaneProvider enum; no HAM runtime yet.",
        ),
    }


HARNESS_CAPABILITIES: Final[Mapping[str, HarnessCapabilityRow]] = MappingProxyType(_rows())
IMPLEMENTED_PROVIDERS: Final[frozenset[str]] = frozenset(
    k for k, v in HARNESS_CAPABILITIES.items() if v.implemented
)
PLANNED_CANDIDATE_PROVIDERS: Final[frozenset[str]] = frozenset(
    k for k, v in HARNESS_CAPABILITIES.items() if v.registry_status == "planned_candidate"
)


def get_harness_capability(provider: str) -> HarnessCapabilityRow | None:
    """Read-only lookup by ``provider`` string (e.g. same value as ``ControlPlaneRun.provider`` for implemented)."""
    return HARNESS_CAPABILITIES.get(provider.strip())


def all_harness_capability_providers() -> tuple[str, ...]:
    """Stable-sorted provider keys in the registry."""
    return tuple(sorted(HARNESS_CAPABILITIES.keys()))


def is_provider_launchable(provider: str) -> bool:
    """
    True only when an ``implemented`` row advertises operator launch.

    Planned candidates (``claude_code``, ``opencode_cli``) always return False,
    independent of any forward-looking flags inside the row, because no adapter
    or ``ControlPlaneProvider`` enum value backs them yet.
    """
    row = get_harness_capability(provider)
    if row is None:
        return False
    if not row.implemented:
        return False
    return bool(row.supports_operator_launch)


__all__ = [
    "AuditSinkLiteral",
    "HarnessCapabilityRow",
    "HarnessFamily",
    "RegistryStatus",
    "HARNESS_CAPABILITIES",
    "IMPLEMENTED_PROVIDERS",
    "PLANNED_CANDIDATE_PROVIDERS",
    "get_harness_capability",
    "all_harness_capability_providers",
    "is_provider_launchable",
]
