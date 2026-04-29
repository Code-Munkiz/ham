"""
Wire managed mission registry create/update to server-observed flows (no client-only truth).
"""

from __future__ import annotations

from typing import Any, Literal, Mapping

from src.ham.cursor_agent_workflow import summarize_cursor_agent_payload
from src.ham.managed_deploy_approval_policy import (
    ManagedDeployApprovalMode,
    mission_deploy_approval_mode_from_project_metadata,
)
from src.persistence.control_plane_run import ControlPlaneRunStore, utc_now_iso
from src.persistence.managed_mission import (
    ManagedMission,
    ManagedMissionStore,
    append_mission_checkpoint_event,
    derive_mission_checkpoint,
    map_cursor_to_mission_lifecycle,
    new_mission_registry_id,
)
from src.persistence.project_store import get_project_store

MissionHandling = Literal["direct", "managed"] | None

_store_singleton: ManagedMissionStore | None = None


def get_managed_mission_store() -> ManagedMissionStore:
    global _store_singleton
    if _store_singleton is None:
        _store_singleton = ManagedMissionStore()
    return _store_singleton


def set_managed_mission_store_for_tests(store: ManagedMissionStore | None) -> None:
    """Test hook to replace the process-global store instance."""
    global _store_singleton
    _store_singleton = store


def _repo_key_for_launch(repository: str) -> str | None:
    s = str(repository or "").strip()
    if not s:
        return None
    return s[:500]


def _checkpoint_reason_context(
    *,
    status_reason_last_observed: str | None,
    last_post_deploy_reason_code: str | None,
    last_post_deploy_state: str | None,
    last_hook_outcome: str | None,
    last_review_severity: str | None,
) -> str | None:
    parts = [
        str(status_reason_last_observed or "").strip(),
        str(last_post_deploy_reason_code or "").strip(),
        str(last_post_deploy_state or "").strip(),
        str(last_hook_outcome or "").strip(),
        str(last_review_severity or "").strip(),
    ]
    flat = " | ".join([p for p in parts if p])
    return flat or None


def _with_derived_checkpoint(m: ManagedMission, *, observed_at: str) -> ManagedMission:
    cp_next, cp_reason = derive_mission_checkpoint(
        mission_lifecycle=m.mission_lifecycle,
        cursor_status_raw=m.cursor_status_last_observed,
        status_reason=_checkpoint_reason_context(
            status_reason_last_observed=m.status_reason_last_observed,
            last_post_deploy_reason_code=m.last_post_deploy_reason_code,
            last_post_deploy_state=m.last_post_deploy_state,
            last_hook_outcome=m.last_hook_outcome,
            last_review_severity=m.last_review_severity,
        ),
        pr_url=m.pr_url_last_observed,
        previous_checkpoint=m.mission_checkpoint_latest,
    )
    if cp_next != m.mission_checkpoint_latest:
        events = append_mission_checkpoint_event(
            existing=m.mission_checkpoint_events,
            checkpoint=cp_next,
            observed_at=observed_at,
            reason=cp_reason,
        )
        return m.model_copy(
            update={
                "mission_checkpoint_latest": cp_next,
                "mission_checkpoint_reason_last": cp_reason,
                "mission_checkpoint_updated_at": observed_at,
                "mission_checkpoint_events": events,
            }
        )
    return m


def resolve_mission_deploy_approval_mode_at_managed_create(
    project_id: str | None,
) -> ManagedDeployApprovalMode:
    """
    Mission-level deploy approval mode at managed create: project default if resolvable and valid, else ``off``.
    Never raises.
    """
    pid = str(project_id).strip() if project_id else ""
    if not pid:
        return "off"
    try:
        rec = get_project_store().get_project(pid)
    except (OSError, ValueError, TypeError):
        return "off"
    if rec is None:
        return "off"
    return mission_deploy_approval_mode_from_project_metadata(rec.metadata)


def try_control_plane_ham_run_id(*, agent_id: str) -> str | None:
    if not agent_id.strip():
        return None
    try:
        run = ControlPlaneRunStore().find_by_provider_and_external(
            provider="cursor_cloud_agent",
            external_id=agent_id,
        )
    except (OSError, ValueError):
        return None
    if run is None:
        return None
    return run.ham_run_id


def create_mission_after_managed_launch(
    *,
    mission_handling: MissionHandling,
    launch_response: Mapping[str, Any],
    body_repository: str,
    body_ref: str | None,
    body_branch_name: str | None,
    uplink_id: str | None = None,
    project_id: str | None = None,
) -> None:
    if mission_handling != "managed":
        return
    if not isinstance(launch_response, dict):
        return
    raw_id = launch_response.get("id") or launch_response.get("agentId")
    agent_id = str(raw_id).strip() if raw_id not in (None, "") else None
    if not agent_id:
        return
    existing = get_managed_mission_store().find_by_cursor_agent_id(agent_id)
    if existing is not None:
        return
    n = utc_now_iso()
    cp_link = try_control_plane_ham_run_id(agent_id=agent_id)
    ulink = str(uplink_id).strip() if uplink_id else None
    approval_mode = resolve_mission_deploy_approval_mode_at_managed_create(project_id)
    m = ManagedMission(
        mission_registry_id=new_mission_registry_id(),
        cursor_agent_id=agent_id,
        control_plane_ham_run_id=cp_link,
        mission_handling="managed",
        mission_deploy_approval_mode=approval_mode,
        uplink_id=ulink,
        repo_key=_repo_key_for_launch(body_repository),
        repository_observed=body_repository.strip()[:500] if body_repository else None,
        ref_observed=body_ref.strip()[:500] if body_ref else None,
        branch_name_launch=body_branch_name.strip()[:500] if body_branch_name else None,
        mission_lifecycle="open",
        cursor_status_last_observed=None,
        status_reason_last_observed="managed_launch:created",
        mission_checkpoint_latest="launched",
        mission_checkpoint_updated_at=n,
        mission_checkpoint_reason_last="managed_launch_created",
        mission_checkpoint_events=append_mission_checkpoint_event(
            existing=[],
            checkpoint="launched",
            observed_at=n,
            reason="managed_launch_created",
        ),
        created_at=n,
        updated_at=n,
        last_server_observed_at=n,
    )
    get_managed_mission_store().save(m)


def observe_mission_from_cursor_payload(*, raw: Mapping[str, Any] | None) -> None:
    """
    After a server-side Cursor agent GET, refresh registry row if it exists
    (managed missions only; no row => no-op).
    """
    if not raw or not isinstance(raw, dict):
        return
    summ = summarize_cursor_agent_payload(raw)
    agent_id = summ.get("agent_id")
    aid = str(agent_id).strip() if agent_id not in (None, "") else None
    if not aid:
        return
    st = get_managed_mission_store()
    m = st.find_by_cursor_agent_id(aid)
    if m is None:
        return
    n = utc_now_iso()
    st_raw = summ.get("status")
    cursor_tok = str(st_raw) if st_raw is not None else None
    new_lc, s_reason = map_cursor_to_mission_lifecycle(
        current=m.mission_lifecycle,
        cursor_status_raw=cursor_tok,
        previous_reason=m.status_reason_last_observed,
    )
    m2: ManagedMission = m.model_copy(
        update={
            "repository_observed": (summ.get("repository") or m.repository_observed),
            "ref_observed": (summ.get("ref") or m.ref_observed),
            "cursor_status_last_observed": cursor_tok,
            "status_reason_last_observed": s_reason,
            "pr_url_last_observed": (summ.get("pr_url") or m.pr_url_last_observed),
            "mission_lifecycle": new_lc,
            "updated_at": n,
            "last_server_observed_at": n,
        }
    )
    m2 = _with_derived_checkpoint(m2, observed_at=n)
    st.save(m2)


def maybe_patch_mission_from_vercel_managed_response(
    *,
    agent_id: str,
    vercel_mapping: Mapping[str, Any] | None,
    deploy_status: Mapping[str, Any] | None,
) -> None:
    """
    Patch last-seen deploy + mapping from ``build_deploy_status_payload`` + ``vercel_mapping``.

    ``deploy_status`` is the dict returned by :func:`build_deploy_status_payload` (``state``, ``deployment``, …).
    """
    aid = agent_id.strip()
    if not aid:
        return
    m = get_managed_mission_store().find_by_cursor_agent_id(aid)
    if m is None:
        return
    n = utc_now_iso()
    tier: str | None = None
    if isinstance(vercel_mapping, dict):
        t = vercel_mapping.get("mapping_tier")
        tier = str(t)[:64] if t is not None else None
    ui_state: str | None = None
    v_raw: str | None = None
    if isinstance(deploy_status, dict):
        s = deploy_status.get("state")
        ui_state = str(s)[:_MAX_LEN_DEP] if s is not None else None
        dep = deploy_status.get("deployment")
        if isinstance(dep, dict) and dep.get("vercel_state") is not None:
            v_raw = str(dep.get("vercel_state"))[:_MAX_LEN_DEP]
    m2 = m.model_copy(
        update={
            "last_vercel_mapping_tier": tier or m.last_vercel_mapping_tier,
            "last_deploy_state_observed": ui_state or m.last_deploy_state_observed,
            "last_hook_outcome": v_raw or m.last_hook_outcome,
            "updated_at": n,
            "last_server_observed_at": n,
        }
    )
    m2 = _with_derived_checkpoint(m2, observed_at=n)
    get_managed_mission_store().save(m2)


_MAX_LEN_DEP = 256


def maybe_patch_mission_from_post_deploy_response(
    *,
    agent_id: str,
    post_deploy: Mapping[str, Any] | None,
) -> None:
    aid = agent_id.strip()
    if not aid:
        return
    m = get_managed_mission_store().find_by_cursor_agent_id(aid)
    if m is None:
        return
    n = utc_now_iso()
    state: str | None = None
    rcode: str | None = None
    if isinstance(post_deploy, dict):
        s = post_deploy.get("state")
        state = str(s)[:128] if s is not None else None
        r = post_deploy.get("reason_code")
        rcode = str(r)[:_MAX_LEN_DEP] if r is not None else None
    m2 = m.model_copy(
        update={
            "last_post_deploy_state": state,
            "last_post_deploy_reason_code": rcode,
            "updated_at": n,
            "last_server_observed_at": n,
        }
    )
    m2 = _with_derived_checkpoint(m2, observed_at=n)
    get_managed_mission_store().save(m2)
