"""
Normalize Vercel deployment list + Cursor agent JSON into a small truthful deploy-status DTO for managed missions.

v1: commit SHA > branch+repo > time window (low). No GitHub API; no webhooks.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlparse

MatchConfidence = Literal["high", "medium", "low"]
DeployUiState = Literal[
    "not_configured",
    "not_observed",
    "pending",
    "building",
    "ready",
    "error",
    "canceled",
    "unknown",
]


def _as_str(x: Any) -> str | None:
    if isinstance(x, str) and x.strip():
        return x.strip()
    return None


def _norm_repo(s: str) -> str:
    t = s.strip().lower()
    t = re.sub(r"^https?://(www\.)?github\.com/", "", t, flags=re.I)
    t = t.rstrip("/")
    return t


def extract_agent_repo_branch_sha(agent: dict[str, Any]) -> dict[str, str | None]:
    """Best-effort hints from proxied Cursor agent JSON (no invention)."""
    out: dict[str, str | None] = {"repo": None, "ref": None, "sha": None, "agent_updated": None}
    top_sha = _as_str(agent.get("commit")) or _as_str(agent.get("headSha"))
    if top_sha:
        out["sha"] = top_sha
    src = agent.get("source")
    if isinstance(src, dict):
        r = _as_str(src.get("repository") or src.get("url"))
        if r:
            out["repo"] = r
        ref = _as_str(src.get("ref") or src.get("branch"))
        if ref:
            out["ref"] = ref
    tgt = agent.get("target")
    if isinstance(tgt, dict):
        bn = _as_str(tgt.get("branchName") or tgt.get("branch") or tgt.get("ref"))
        if bn:
            out["ref"] = bn
        tsha = _as_str(tgt.get("commit") or tgt.get("sha") or tgt.get("headSha"))
        if tsha and not out["sha"]:
            out["sha"] = tsha
    # timing hint for low-confidence window
    for k in ("updatedAt", "updated_at", "finishedAt", "finished_at", "endedAt", "ended_at"):
        t = _as_str(agent.get(k))
        if t:
            out["agent_updated"] = t
            break
    if not out["agent_updated"]:
        t0 = _as_str(agent.get("createdAt") or agent.get("created_at"))
        if t0:
            out["agent_updated"] = t0
    return out


def _parse_iso(ts: str) -> datetime | None:
    try:
        t = ts.replace("Z", "+00:00")
        d = datetime.fromisoformat(t)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except (TypeError, ValueError):
        return None


def _deployment_state_fields(dep: dict[str, Any]) -> tuple[DeployUiState, str | None]:
    """
    Vercel deployment: prefer `readyState` then `state` (shapes differ).
    """
    rs = _as_str(dep.get("readyState")) or _as_str(dep.get("ready_state"))
    st = _as_str(dep.get("state"))
    raw = (rs or st or "").upper()
    if raw in ("QUEUED", "INITIALIZING", "PENDING"):
        return "pending", raw
    if raw in ("BUILDING", "ANALYZING"):
        return "building", raw
    if raw == "READY":
        return "ready", raw
    if raw in ("ERROR", "FAILED"):
        return "error", raw
    if raw in ("CANCELED", "CANCELLED"):
        return "canceled", raw
    if not raw:
        return "unknown", None
    return "unknown", raw


def _meta(d: dict[str, Any]) -> dict[str, Any]:
    m = d.get("meta")
    return m if isinstance(m, dict) else {}


def _dep_repo_from_meta(m: dict[str, Any]) -> str | None:
    org = _as_str(m.get("githubCommitOrg") or m.get("githubCommitOwner"))
    repo = _as_str(m.get("githubCommitRepo") or m.get("githubRepo") or m.get("repo"))
    if org and repo:
        return f"{org}/{repo}"
    r = _as_str(m.get("githubCommitRef"))
    if r and "/" in r:
        return None
    return None


def _best_deployment(
    *,
    agent: dict[str, Any],
    deployments: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, MatchConfidence | None, str | None]:
    if not deployments:
        return None, None, None
    hints = extract_agent_repo_branch_sha(agent)
    want_sha = (hints.get("sha") or "").lower() or None
    want_ref = (hints.get("ref") or "").lower() or None
    want_repo = hints.get("repo")
    want_repo_n = _norm_repo(want_repo) if want_repo else None
    t_agent = _parse_iso(hints["agent_updated"] or "") if hints.get("agent_updated") else None

    for dep in deployments:
        m = _meta(dep)
        msha = _as_str(m.get("githubCommitSha"))
        if msha and want_sha and msha.lower() == want_sha:
            return dep, "high", "githubCommitSha"

    for dep in deployments:
        m = _meta(dep)
        dref = _as_str(m.get("githubCommitRef") or m.get("githubRef"))
        dr = _dep_repo_from_meta(m) or ""
        if want_ref and dref and dref.lower() == want_ref:
            if want_repo_n and dr:
                if _norm_repo(dr) == want_repo_n:
                    return dep, "medium", "branch+repo"
            if want_ref and not want_repo_n:
                return dep, "medium", "githubCommitRef"
        if want_ref and dref and want_repo_n and dr and _norm_repo(dr) == want_repo_n:
            if dref.split("/")[-1].lower() == want_ref.split("/")[-1]:
                return dep, "medium", "ref+path"

    # time window: deployments after agent last update
    if t_agent:
        for dep in deployments:
            ca = _as_str(dep.get("createdAt") or dep.get("created"))
            tdep = _parse_iso(ca) if ca else None
            if tdep and tdep >= t_agent:
                return dep, "low", "time_window_after_agent"

    if deployments:
        return deployments[0], "low", "newest_in_list"
    return None, None, None


def _resolve_deployment_url(dep: dict[str, Any], ui: DeployUiState) -> str | None:
    m = _meta(dep)
    durl = _as_str(dep.get("url")) or _as_str(m.get("githubCommitUrl")) or _as_str(dep.get("alias")) or None
    if ui == "ready" and not durl:
        alias = dep.get("alias")
        if isinstance(alias, list) and alias and isinstance(alias[0], str):
            a0 = alias[0]
            durl = a0 if a0.startswith("http") else f"https://{a0}"
    return durl


def compute_matched_deployment_view(
    *, agent: dict[str, Any], deployments_list_json: dict[str, Any]
) -> dict[str, Any] | None:
    """
    Internal view for a matched Vercel deployment (same match + URL rules as build_deploy_status_payload).
    Returns None if no usable deployment list or no match.
    """
    if not isinstance(deployments_list_json, dict):
        return None
    raw_list = deployments_list_json.get("deployments")
    deployments = [d for d in raw_list if isinstance(d, dict)] if isinstance(raw_list, list) else []

    def _dep_created_key(dep: dict[str, Any]) -> float:
        ca = _as_str(dep.get("createdAt") or dep.get("created")) or ""
        d = _parse_iso(ca) if ca else None
        return d.timestamp() if d else 0.0

    deployments.sort(key=_dep_created_key, reverse=True)
    if not deployments:
        return None
    dep, conf, reason = _best_deployment(agent=agent, deployments=deployments)
    if dep is None:
        return None
    ui, raw = _deployment_state_fields(dep)
    durl = _resolve_deployment_url(dep, ui)
    return {
        "dep": dep,
        "match_confidence": conf,
        "match_reason": reason,
        "state": ui,
        "vercel_state": raw,
        "url": durl,
    }


def allowed_hosts_for_deployment(dep: dict[str, Any], primary_url: str) -> frozenset[str]:
    """
    Hostnames (lowercase) allowed as redirect targets when probing primary_url, derived from the
    same Vercel deployment object only. Used for post-deploy validation SSRF protection.
    """
    hosts: set[str] = set()
    p0 = urlparse(primary_url) if primary_url else None
    if p0 and p0.netloc:
        hosts.add(p0.netloc.split(":")[0].lower())
    m = _meta(dep)
    u = _as_str(dep.get("url"))
    if u and (u.startswith("http://") or u.startswith("https://")):
        p = urlparse(u)
        if p.netloc:
            hosts.add(p.netloc.split(":")[0].lower())
    u = _as_str(m.get("githubCommitUrl"))
    if u and (u.startswith("http://") or u.startswith("https://")):
        p = urlparse(u)
        if p.netloc:
            hosts.add(p.netloc.split(":")[0].lower())
    al = dep.get("alias")
    if isinstance(al, list):
        for a in al:
            if not isinstance(a, str) or not a.strip():
                continue
            a = a.strip()
            if a.startswith("http://") or a.startswith("https://"):
                p = urlparse(a)
                if p.netloc:
                    hosts.add(p.netloc.split(":")[0].lower())
            else:
                hosts.add(a.split("/")[0].lower().split(":")[0])
    if not hosts and p0 and p0.netloc:
        hosts.add(p0.netloc.split(":")[0].lower())
    return frozenset(hosts)


def build_deploy_status_payload(
    *,
    agent: dict[str, Any] | None,
    deployments_list_json: dict[str, Any] | None,
    api_error: str | None = None,
    not_configured: bool = False,
) -> dict[str, Any]:
    """
    Public JSON shape for GET /api/cursor/managed/vercel/deploy-status.
    """
    checked = datetime.now(timezone.utc).isoformat()
    if not_configured or agent is None:
        return {
            "checked_at": checked,
            "vercel": {"configured": not not_configured and agent is not None},
            "state": "not_configured" if not_configured else "not_observed",
            "match_confidence": None,
            "match_reason": None,
            "message": "Vercel API token and project id are not both configured on the HAM server."
            if not_configured
            else "No agent payload.",
            "deployment": None,
            "api_error": None,
        }

    if api_error:
        return {
            "checked_at": checked,
            "vercel": {"configured": True},
            "state": "unknown",
            "match_confidence": None,
            "match_reason": None,
            "message": f"Could not list Vercel deployments: {api_error}",
            "deployment": None,
            "api_error": api_error,
        }

    if not isinstance(deployments_list_json, dict):
        return {
            "checked_at": checked,
            "vercel": {"configured": True},
            "state": "not_observed",
            "match_confidence": None,
            "match_reason": None,
            "message": "No deployment list returned from Vercel.",
            "deployment": None,
            "api_error": None,
        }

    raw_list = deployments_list_json.get("deployments")
    deployments = [d for d in raw_list if isinstance(d, dict)] if isinstance(raw_list, list) else []

    def _dep_created_key(dep: dict[str, Any]) -> float:
        ca = _as_str(dep.get("createdAt") or dep.get("created")) or ""
        d = _parse_iso(ca) if ca else None
        return d.timestamp() if d else 0.0

    deployments.sort(key=_dep_created_key, reverse=True)
    if not deployments:
        return {
            "checked_at": checked,
            "vercel": {"configured": True},
            "state": "not_observed",
            "match_confidence": None,
            "match_reason": None,
            "message": "No deployments returned for the configured Vercel project (empty list).",
            "deployment": None,
            "api_error": None,
        }

    dep, conf, reason = _best_deployment(agent=agent, deployments=deployments)
    if dep is None:
        return {
            "checked_at": checked,
            "vercel": {"configured": True},
            "state": "not_observed",
            "match_confidence": None,
            "match_reason": None,
            "message": "No deployment could be matched to this mission with current signals.",
            "deployment": None,
            "api_error": None,
        }

    ui, raw = _deployment_state_fields(dep)
    durl = _resolve_deployment_url(dep, ui)

    msg: str
    if conf == "high":
        msg = f"Vercel deployment matched (commit). State: {raw or 'unknown'}."
    elif conf == "medium":
        msg = f"Vercel deployment matched (branch/repo metadata). May not be unique — verify in Vercel. State: {raw or 'unknown'}."
    else:
        msg = f"Vercel deployment match is uncertain (heuristic: {reason or 'heuristic'}). Treat as a hint, not proof. State: {raw or 'unknown'}."

    return {
        "checked_at": checked,
        "vercel": {"configured": True},
        "state": ui,
        "match_confidence": conf,
        "match_reason": reason,
        "message": msg,
        "deployment": {
            "id": _as_str(dep.get("uid") or dep.get("id")),
            "url": durl,
            "vercel_state": raw,
            "created_at": _as_str(dep.get("createdAt") or dep.get("created")),
        },
        "api_error": None,
    }
