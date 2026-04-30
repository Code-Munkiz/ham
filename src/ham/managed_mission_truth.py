"""
Screen-level operator truth for managed Cursor Cloud Agent missions (Phase A observability).

HAM persists bounded mission facts and feed synthesis; Cursor remains upstream for execution.
"""

from __future__ import annotations

from typing import Any

from src.persistence.managed_mission import ManagedMission


def managed_mission_truth_table(*, m: ManagedMission) -> dict[str, Any]:
    """
    Stable JSON for UI/docs: who owns what, without reading source.

    Not persisted — derived from the mission row at call time.
    """
    return {
        "kind": "managed_mission_truth_table",
        "mission_registry_id": m.mission_registry_id,
        "rows": [
            {
                "topic": "Agent execution",
                "cursor_owns": "Runs the Cloud Agent, tools, and repo work in Cursor's environment.",
                "ham_owns": "Does not execute the agent; proxies launch/follow-up/cancel when configured.",
            },
            {
                "topic": "Mission record & feed",
                "cursor_owns": "Status strings and conversation payloads returned by Cursor APIs.",
                "ham_owns": "Persists ManagedMission JSON, checkpoint history, and bounded feed events (HAM-side view).",
            },
            {
                "topic": "Deploy approval mode",
                "cursor_owns": "—",
                "ham_owns": (
                    "Snapshot at managed mission create from project default when project_id was set; "
                    "not live-synced after create."
                ),
            },
            {
                "topic": "Control plane run",
                "cursor_owns": "—",
                "ham_owns": (
                    "Optional link control_plane_ham_run_id when launch matched a committed ControlPlaneRun "
                    "(operator/chat path). Null means UI-only or unmatched launch."
                ),
            },
            {
                "topic": "Hermes advisory review",
                "cursor_owns": "—",
                "ham_owns": (
                    "Optional operator-triggered HermesReviewer output stored as advisory fields only; "
                    "does not overwrite provider status or lifecycle."
                ),
            },
        ],
        "footnotes": [
            "Feed merge uses SDK bridge when enabled, else REST projection; see provider_projection on GET …/feed.",
            "Mission lifecycle terminal states are sticky (open → succeeded/failed does not flip back on noise).",
        ],
    }


def managed_mission_correlation(*, m: ManagedMission) -> dict[str, Any]:
    """Short join hint for Phase B (control plane list vs managed mission list)."""
    hid = m.control_plane_ham_run_id
    linked = bool(hid and str(hid).strip())
    return {
        "control_plane_ham_run_id": hid,
        "control_plane_linked": linked,
        "hint": (
            "GET /api/control-plane-runs/{ham_run_id} for launch-time summary when linked."
            if linked
            else "No control-plane row was linked at create (UI-only launch or no matching run)."
        ),
    }
