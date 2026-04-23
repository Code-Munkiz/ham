"""
Per-repo (owner/repo) → Vercel project id, optional team, optional deploy hook env var name.

Server-side only. Raw hook URLs must not be stored in the YAML map — only env var names.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

_LOG = logging.getLogger(__name__)

MappingTier = Literal["mapped", "global", "unavailable"]


def normalize_repo_key(raw: str | None) -> str | None:
    """GitHub `owner/repo` (lowercase, no scheme/host, no trailing slash)."""
    if not raw or not isinstance(raw, str):
        return None
    t = raw.strip().lower()
    t = re.sub(r"^https?://(www\.)?github\.com/", "", t, flags=re.IGNORECASE)
    t = t.rstrip("/")
    if not t or "/" not in t:
        return None
    parts = t.split("/")
    if len(parts) < 2:
        return None
    return f"{parts[0]}/{parts[1]}"


@dataclass
class VercelProjectMapRow:
    repo: str
    project_id: str
    team_id: str | None = None
    deploy_hook_env: str | None = None  # name of env var, not the URL


@dataclass
class VercelListResolution:
    """Resolves Vercel project/team for GET /v6/deployments (deploy truth)."""

    project_id: str | None
    team_id: str | None
    repo_key: str | None
    mapping_tier: MappingTier
    use_global_project_fallback: bool
    message: str
    map_load_error: str | None = None


@dataclass
class VercelHookResolution:
    """Resolves deploy hook URL for POST deploy-hook."""

    hook_url: str | None
    hook_configured: bool
    deploy_hook_env_name: str | None  # which env was used (name only, never the secret)
    repo_key: str | None
    mapping_tier: MappingTier
    used_global_hook_fallback: bool
    fail_closed: bool
    message: str
    map_load_error: str | None = None


_MAP_ROWS: list[VercelProjectMapRow] = []
_MAP_BY_REPO: dict[str, VercelProjectMapRow] = {}
_MAP_LOAD_ERROR: str | None = None
_MAP_LOADED = False


def _default_map_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "config" / "vercel_project_map.yaml"


def _parse_mapping_payload(data: Any, *, source: str) -> list[VercelProjectMapRow]:
    if not isinstance(data, dict):
        raise ValueError(f"{source}: root must be a mapping (got {type(data).__name__})")
    raw_list = data.get("mappings")
    if raw_list is None:
        return []
    if not isinstance(raw_list, list):
        raise ValueError(f"{source}: 'mappings' must be a list")
    out: list[VercelProjectMapRow] = []
    seen: set[str] = set()
    for i, item in enumerate(raw_list):
        if not isinstance(item, dict):
            raise ValueError(f"{source}: mappings[{i}] must be an object")
        raw_repo = item.get("repo")
        repo = normalize_repo_key(str(raw_repo)) if raw_repo is not None else None
        if not repo:
            raise ValueError(f"{source}: mappings[{i}].repo is required (owner/repo)")
        if repo in seen:
            raise ValueError(f"{source}: duplicate repo key: {repo!r}")
        seen.add(repo)
        pid = (item.get("project_id") or "").strip() if isinstance(item.get("project_id"), str) else str(item.get("project_id") or "")
        if not pid:
            raise ValueError(f"{source}: mappings[{i}].project_id is required for repo {repo!r}")
        tid = (item.get("team_id") or "").strip() or None if isinstance(item.get("team_id"), str) or item.get("team_id") is None else str(item.get("team_id") or "")
        if tid == "":
            tid = None
        hook_env = (item.get("deploy_hook_env") or "").strip() or None if isinstance(item.get("deploy_hook_env"), str) or item.get("deploy_hook_env") is None else str(item.get("deploy_hook_env") or "")
        if hook_env == "":
            hook_env = None
        if hook_env and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", hook_env):
            raise ValueError(f"{source}: mappings[{i}].deploy_hook_env must be a valid env var name, got {hook_env!r}")
        out.append(VercelProjectMapRow(repo=repo, project_id=pid, team_id=tid, deploy_hook_env=hook_env))
    return out


def _load_map_from_file(path: Path) -> list[VercelProjectMapRow]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text) if text.strip() else {"mappings": []}
    return _parse_mapping_payload(data, source=str(path))


def _load_map_from_json_env() -> list[VercelProjectMapRow] | None:
    raw = (os.environ.get("HAM_VERCEL_PROJECT_MAP_JSON") or "").strip()
    if not raw:
        return None
    data = json.loads(raw)
    return _parse_mapping_payload(data, source="HAM_VERCEL_PROJECT_MAP_JSON")


def load_vercel_project_map(*, _reset: bool = False) -> None:
    """Load map from HAM_VERCEL_PROJECT_MAP_JSON or YAML file. Idempotent; set _reset=True in tests to reload."""
    global _MAP_ROWS, _MAP_BY_REPO, _MAP_LOAD_ERROR, _MAP_LOADED
    if _MAP_LOADED and not _reset:
        return
    _MAP_LOADED = True
    _MAP_LOAD_ERROR = None
    _MAP_BY_REPO = {}
    _MAP_ROWS = []
    try:
        from_env = _load_map_from_json_env()
        if from_env is not None:
            _MAP_ROWS = from_env
        else:
            p = (os.environ.get("HAM_VERCEL_PROJECT_MAP_PATH") or "").strip()
            path = Path(p) if p else _default_map_path()
            _MAP_ROWS = _load_map_from_file(path) if path.is_file() else []
        for row in _MAP_ROWS:
            _MAP_BY_REPO[row.repo] = row
        if _MAP_ROWS:
            _LOG.info("vercel.project_map.loaded", extra={"count": len(_MAP_ROWS)})
    except (OSError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
        _MAP_LOAD_ERROR = f"{type(exc).__name__}: {exc}"
        _LOG.error("vercel.project_map.load_failed", extra={"err": _MAP_LOAD_ERROR})
        _MAP_ROWS = []
        _MAP_BY_REPO = {}


def reset_vercel_project_map_for_tests() -> None:
    """Allow reloading with new env / files."""
    global _MAP_LOADED
    _MAP_LOADED = False
    load_vercel_project_map(_reset=True)


def _global_vercel_token() -> str | None:
    return (os.environ.get("HAM_VERCEL_API_TOKEN") or os.environ.get("VERCEL_API_TOKEN") or "").strip() or None


def _global_project_id() -> str | None:
    return (os.environ.get("HAM_VERCEL_PROJECT_ID") or os.environ.get("VERCEL_PROJECT_ID") or "").strip() or None


def _global_team_id() -> str | None:
    return (os.environ.get("HAM_VERCEL_TEAM_ID") or os.environ.get("VERCEL_TEAM_ID") or "").strip() or None


def _global_hook_url() -> str | None:
    return (os.environ.get("HAM_VERCEL_DEPLOY_HOOK_URL") or os.environ.get("VERCEL_DEPLOY_HOOK_URL") or "").strip() or None


def allow_global_hook_fallback() -> bool:
    v = (os.environ.get("HAM_VERCEL_ALLOW_GLOBAL_HOOK_FALLBACK") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def vercel_token_configured() -> bool:
    return _global_vercel_token() is not None


def resolve_vercel_list_for_agent(agent: dict[str, Any] | None) -> VercelListResolution:
    """
    Vercel Deployments list: per-repo project_id when map matches; else global project id.
    """
    load_vercel_project_map()
    merr = _MAP_LOAD_ERROR
    if not vercel_token_configured():
        return VercelListResolution(
            project_id=None,
            team_id=None,
            repo_key=None,
            mapping_tier="unavailable",
            use_global_project_fallback=False,
            message="Vercel API token is not configured on the server.",
            map_load_error=merr,
        )

    from src.ham.vercel_deploy_status import extract_agent_repo_branch_sha

    hints = extract_agent_repo_branch_sha(agent) if isinstance(agent, dict) else None
    raw_repo = hints.get("repo") if isinstance(hints, dict) else None
    repo_key = normalize_repo_key(raw_repo) if raw_repo else None

    gproj = _global_project_id()
    gteam = _global_team_id()

    if merr and not gproj:
        return VercelListResolution(
            project_id=None,
            team_id=gteam,
            repo_key=repo_key,
            mapping_tier="unavailable",
            use_global_project_fallback=False,
            message="Vercel project map failed to load and no global project id is set.",
            map_load_error=merr,
        )

    if repo_key and repo_key in _MAP_BY_REPO:
        row = _MAP_BY_REPO[repo_key]
        tid = row.team_id if row.team_id else gteam
        return VercelListResolution(
            project_id=row.project_id,
            team_id=tid,
            repo_key=repo_key,
            mapping_tier="mapped",
            use_global_project_fallback=False,
            message=f"Using per-repo Vercel mapping for {repo_key} (project_id from map).",
            map_load_error=merr,
        )

    if gproj:
        return VercelListResolution(
            project_id=gproj,
            team_id=gteam,
            repo_key=repo_key,
            mapping_tier="global",
            use_global_project_fallback=True,
            message="No per-repo Vercel mapping for this repository; using global HAM_VERCEL_PROJECT_ID (or VERCEL_PROJECT_ID)."
            if repo_key
            else "Repository could not be determined from the agent payload; using global HAM_VERCEL_PROJECT_ID (or VERCEL_PROJECT_ID).",
            map_load_error=merr,
        )

    return VercelListResolution(
        project_id=None,
        team_id=None,
        repo_key=repo_key,
        mapping_tier="unavailable",
        use_global_project_fallback=False,
        message="No Vercel project id: configure per-repo config or HAM_VERCEL_PROJECT_ID (or VERCEL_PROJECT_ID).",
        map_load_error=merr,
    )


def _hook_url_from_env_name(name: str) -> str | None:
    u = (os.environ.get(name) or "").strip()
    return u or None


def resolve_vercel_hook_for_agent(agent: dict[str, Any] | None) -> VercelHookResolution:
    """
    Deploy hook URL: from map row's deploy_hook_env, else global — with fail-closed rules.
    """
    load_vercel_project_map()
    merr = _MAP_LOAD_ERROR
    ghook = _global_hook_url()
    allow_fb = allow_global_hook_fallback()

    from src.ham.vercel_deploy_status import extract_agent_repo_branch_sha

    hints = extract_agent_repo_branch_sha(agent) if isinstance(agent, dict) else None
    raw_repo = hints.get("repo") if isinstance(hints, dict) else None
    repo_key = normalize_repo_key(raw_repo) if raw_repo else None

    if not repo_key:
        if ghook:
            return VercelHookResolution(
                hook_url=ghook,
                hook_configured=True,
                deploy_hook_env_name=None,
                repo_key=None,
                mapping_tier="global",
                used_global_hook_fallback=True,
                fail_closed=False,
                message="Repository could not be determined from agent payload; using global deploy hook URL.",
                map_load_error=merr,
            )
        return VercelHookResolution(
            hook_url=None,
            hook_configured=False,
            deploy_hook_env_name=None,
            repo_key=None,
            mapping_tier="unavailable",
            used_global_hook_fallback=False,
            fail_closed=True,
            message="Repository unknown and no global deploy hook URL configured.",
            map_load_error=merr,
        )

    if repo_key in _MAP_BY_REPO:
        row = _MAP_BY_REPO[repo_key]
        if row.deploy_hook_env:
            u = _hook_url_from_env_name(row.deploy_hook_env)
            if u:
                return VercelHookResolution(
                    hook_url=u,
                    hook_configured=True,
                    deploy_hook_env_name=row.deploy_hook_env,
                    repo_key=repo_key,
                    mapping_tier="mapped",
                    used_global_hook_fallback=False,
                    fail_closed=False,
                    message=f"Using per-repo deploy hook from env var {row.deploy_hook_env!r} for {repo_key}.",
                    map_load_error=merr,
                )
            if allow_fb and ghook:
                return VercelHookResolution(
                    hook_url=ghook,
                    hook_configured=True,
                    deploy_hook_env_name=None,
                    repo_key=repo_key,
                    mapping_tier="global",
                    used_global_hook_fallback=True,
                    fail_closed=False,
                    message=f"Mapped hook env {row.deploy_hook_env!r} is unset; global hook used (HAM_VERCEL_ALLOW_GLOBAL_HOOK_FALLBACK enabled).",
                    map_load_error=merr,
                )
            return VercelHookResolution(
                hook_url=None,
                hook_configured=False,
                deploy_hook_env_name=row.deploy_hook_env,
                repo_key=repo_key,
                mapping_tier="unavailable",
                used_global_hook_fallback=False,
                fail_closed=True,
                message=f"Per-repo map requires hook env {row.deploy_hook_env!r} but it is not set, and global hook fallback is disabled.",
                map_load_error=merr,
            )
        if ghook:
            return VercelHookResolution(
                hook_url=ghook,
                hook_configured=True,
                deploy_hook_env_name=None,
                repo_key=repo_key,
                mapping_tier="global",
                used_global_hook_fallback=True,
                fail_closed=False,
                message=f"Per-repo map for {repo_key} has no deploy_hook_env; using global deploy hook URL.",
                map_load_error=merr,
            )
        return VercelHookResolution(
            hook_url=None,
            hook_configured=False,
            deploy_hook_env_name=None,
            repo_key=repo_key,
            mapping_tier="unavailable",
            used_global_hook_fallback=False,
            fail_closed=True,
            message=f"Per-repo map for {repo_key} has no deploy_hook_env and no global HAM_VERCEL_DEPLOY_HOOK_URL (or VERCEL_DEPLOY_HOOK_URL).",
            map_load_error=merr,
        )

    if ghook:
        return VercelHookResolution(
            hook_url=ghook,
            hook_configured=True,
            deploy_hook_env_name=None,
            repo_key=repo_key,
            mapping_tier="global",
            used_global_hook_fallback=True,
            fail_closed=False,
            message="No per-repo deploy hook entry; using global deploy hook URL.",
            map_load_error=merr,
        )
    return VercelHookResolution(
        hook_url=None,
        hook_configured=False,
        deploy_hook_env_name=None,
        repo_key=repo_key,
        mapping_tier="unavailable",
        used_global_hook_fallback=False,
        fail_closed=True,
        message="No deploy hook URL for this repository and no global HAM_VERCEL_DEPLOY_HOOK_URL (or VERCEL_DEPLOY_HOOK_URL).",
        map_load_error=merr,
    )


def vercel_list_resolution_to_dict(r: VercelListResolution) -> dict[str, Any]:
    return {
        "repo_key": r.repo_key,
        "mapping_tier": r.mapping_tier,
        "project_id_used": r.project_id,
        "team_id_used": r.team_id,
        "use_global_project_fallback": r.use_global_project_fallback,
        "message": r.message,
        "map_load_error": r.map_load_error,
    }


def vercel_hook_resolution_to_dict(r: VercelHookResolution) -> dict[str, Any]:
    return {
        "repo_key": r.repo_key,
        "mapping_tier": r.mapping_tier,
        "hook_configured": r.hook_configured,
        "deploy_hook_env_name": r.deploy_hook_env_name,
        "used_global_hook_fallback": r.used_global_hook_fallback,
        "fail_closed": r.fail_closed,
        "message": r.message,
        "map_load_error": r.map_load_error,
    }
