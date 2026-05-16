from __future__ import annotations

import copy
import os
import time
from datetime import datetime, timezone
from typing import Any

from src.ham.hermes_gateway.adapters.cli_inventory import fetch_hermes_cli_version_line
from src.ham.hermes_gateway.adapters.external_runners import build_external_runner_cards
from src.ham.hermes_gateway.adapters.http_gateway import probe_hermes_http_gateway
from src.ham.hermes_gateway.adapters.rpc_stub import (
    hermes_rpc_placeholder,
    websocket_control_placeholder,
)
from src.ham.hermes_gateway.cache import TtlCache
from src.ham.hermes_gateway.dto import DEFAULT_CACHE_TTL_S, GATEWAY_SNAPSHOT_SCHEMA_VERSION
from src.ham.hermes_runtime_inventory import build_runtime_inventory
from src.ham.hermes_skills_live import build_skills_installed_overlay
from src.persistence.control_plane_run import get_control_plane_run_store
from src.persistence.project_store import get_project_store
from src.persistence.run_store import RunStore
from src.registry.droids import DEFAULT_DROID_REGISTRY


def _cache_ttl_s() -> float:
    raw = (os.environ.get("HAM_HERMES_GATEWAY_CACHE_TTL_S") or "").strip()
    if not raw:
        return DEFAULT_CACHE_TTL_S
    try:
        return max(5.0, min(600.0, float(raw)))
    except ValueError:
        return DEFAULT_CACHE_TTL_S


def _omit_inventory_raw_blobs(inv: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy inventory and replace raw CLI captures with safe placeholders."""
    data = copy.deepcopy(inv)

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for k in list(obj.keys()):
                if k == "raw_redacted":
                    obj[k] = "[omitted in gateway snapshot — use /api/hermes-runtime/inventory for allowlisted operator views]"
                else:
                    walk(obj[k])
        elif isinstance(obj, list):
            for it in obj:
                walk(it)

    walk(data)
    # Never expose resolved binary path as primary navigation; keep boolean hints only upstream.
    src = data.get("source")
    if isinstance(src, dict) and "hermes_binary" in src:
        hb = src.get("hermes_binary")
        src["hermes_cli_resolved"] = bool(hb)
        if hb:
            src["hermes_binary"] = "[configured]"
    return data


def _commands_menu_surface() -> dict[str, Any]:
    return {
        "hermes_slash_and_menus": {
            "availability": "cli_tty_only",
            "summary": (
                "Hermes v0.8.0 exposes interactive menus via curses/TTY, not a reusable REST menu API. "
                "Use the terminal for slash/command discovery."
            ),
        },
        "ham_cli_guidance": [
            {
                "id": "hermes_tools_summary",
                "title": "Tools summary (terminal)",
                "template": "hermes tools --summary",
                "requires_tty": True,
            },
            {
                "id": "hermes_plugins_list",
                "title": "Plugins list (terminal)",
                "template": "hermes plugins list",
                "requires_tty": False,
            },
            {
                "id": "hermes_mcp_list",
                "title": "MCP list (terminal)",
                "template": "hermes mcp list",
                "requires_tty": False,
            },
        ],
    }


def _operator_connection(
    *,
    captured_at: str,
    ttl: float,
    degraded: list[str],
    ver: dict[str, Any],
    http: dict[str, Any],
    hub: dict[str, Any],
) -> dict[str, Any]:
    """
    Single place for the dashboard to show CLI probe + HTTP probe + HAM chat mode + snapshot age.

    Additive only; no new ``hermes`` argv (still only allowlisted calls elsewhere).
    """
    cli_st = str(ver.get("status") or "unknown")
    vline = str(ver.get("version_line") or "")[:500]
    http_st = str(http.get("status") or "unknown")
    gw_mode = hub.get("gateway_mode") if isinstance(hub, dict) else None
    return {
        "summary": {
            "cli_probe": cli_st,
            "cli_version_line": vline,
            "http_gateway_status": http_st,
            "ham_chat_gateway_mode": str(gw_mode) if gw_mode is not None else None,
        },
        "snapshot_meta": {
            "captured_at": captured_at,
            "ttl_seconds": float(ttl),
            "degraded_capabilities_count": len(degraded),
            "has_degraded": bool(degraded),
        },
        "guidance": (
            "Local Hermes CLI (on the host that runs the Ham API) is separate from HERMES_GATEWAY_*: "
            "the CLI covers tools, skills, and TTY; the HTTP base URL is for /api/chat when HERMES_GATEWAY_MODE=http."
        ),
    }


def _future_placeholders() -> list[dict[str, Any]]:
    return [
        {
            "id": "hermes_rest_health_detailed",
            "label": "GET /health/detailed (upstream docs)",
            "status": "unverified_on_v0_8_0",
            "note": "Published docs mention detailed health; audited v0.8.0 code may not register this route. Verify after Hermes upgrade.",
        },
        {
            "id": "hermes_live_menu_rest",
            "label": "Live menu / autocomplete REST",
            "status": "not_available",
            "note": "No official REST surface for TUI menus in v0.8.0.",
        },
        hermes_rpc_placeholder(),
        websocket_control_placeholder(),
    ]


class HermesGatewayBroker:
    def __init__(self) -> None:
        self._cache = TtlCache()
        self._cp_store = get_control_plane_run_store()

    def build_snapshot(
        self,
        *,
        project_id: str | None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        ttl = _cache_ttl_s()
        t0 = time.perf_counter()

        def inv_factory() -> dict[str, Any]:
            return build_runtime_inventory()

        def skills_factory() -> dict[str, Any]:
            return build_skills_installed_overlay()

        def http_factory() -> dict[str, Any]:
            return probe_hermes_http_gateway()

        def ver_factory() -> dict[str, Any]:
            return fetch_hermes_cli_version_line()

        if force_refresh:
            inv = inv_factory()
            inv_hit = False
            sk = skills_factory()
            sk_hit = False
            http = http_factory()
            http_hit = False
            ver = ver_factory()
            ver_hit = False
            # Repopulate TTL cache so a later ``force_refresh=False`` returns this payload,
            # not pre-refresh fragments.
            self._cache.set("inventory", inv, ttl)
            self._cache.set("skills_installed", sk, ttl)
            self._cache.set("http_probe", http, ttl)
            self._cache.set("hermes_version", ver, ttl)
        else:
            inv, inv_hit = self._cache.get_or_set("inventory", ttl, inv_factory)
            sk, sk_hit = self._cache.get_or_set("skills_installed", ttl, skills_factory)
            http, http_hit = self._cache.get_or_set("http_probe", ttl, http_factory)
            ver, ver_hit = self._cache.get_or_set("hermes_version", ttl, ver_factory)

        # Local import keeps ``ham.*`` import graph free of eager ``api.*`` deps.
        from src.api.hermes_hub import build_hermes_hub_payload

        hub = build_hermes_hub_payload()

        inv_public = _omit_inventory_raw_blobs(inv)
        skills_public = copy.deepcopy(sk)
        if isinstance(skills_public, dict):
            for k in ("hermes_home", "project_root", "config_path"):
                skills_public.pop(k, None)
            skills_public["raw_redacted"] = (
                "[omitted in gateway snapshot — use /api/hermes-skills/installed for allowlisted operator views]"
            )
            inst = skills_public.get("installations")
            if isinstance(inst, list) and len(inst) > 120:
                skills_public["installations"] = inst[:120]
                skills_public["installations_truncated"] = True

        degraded: list[str] = []
        warnings: list[str] = list(inv.get("warnings") or [])
        if not inv.get("available"):
            degraded.append("hermes_cli_inventory")
        if http.get("status") in ("unreachable", "not_configured", "auth_required"):
            degraded.append("hermes_http_gateway")
        if ver.get("status") != "ok":
            degraded.append("hermes_version_cli")

        activity: dict[str, Any] = {
            "control_plane_runs": [],
            "control_plane_error": None,
            "ham_run_store_count": RunStore().count(),
        }
        pid = (project_id or "").strip() or None
        if pid:
            try:
                if get_project_store().get_project(pid) is None:
                    activity["control_plane_error"] = "unknown_project_id"
                else:
                    runs = self._cp_store.list_for_project(pid, limit=30)
                    activity["control_plane_runs"] = [
                        {
                            "ham_run_id": r.ham_run_id,
                            "provider": r.provider,
                            "action_kind": r.action_kind,
                            "status": r.status,
                            "summary": r.summary,
                            "updated_at": r.updated_at,
                        }
                        for r in runs
                    ]
            except OSError as exc:
                activity["control_plane_error"] = str(exc)[:200]

        droid_count = len(DEFAULT_DROID_REGISTRY.ids())
        runners = build_external_runner_cards(droid_count=droid_count)

        tools_count = len((inv_public.get("tools") or {}).get("toolsets") or [])
        plugins_count = len((inv_public.get("plugins") or {}).get("items") or [])
        mcp_count = len((inv_public.get("mcp") or {}).get("servers") or [])
        skills_catalog_count = int((inv_public.get("skills") or {}).get("catalog_count") or 0)
        skills_installed_count = (
            int(skills_public.get("live_count") or 0) if isinstance(skills_public, dict) else 0
        )

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        captured_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        operator_connection = _operator_connection(
            captured_at=captured_at,
            ttl=ttl,
            degraded=degraded,
            ver=ver,
            http=http,
            hub=hub,
        )

        return {
            "kind": "ham_hermes_gateway_snapshot",
            "schema_version": GATEWAY_SNAPSHOT_SCHEMA_VERSION,
            "captured_at": captured_at,
            "ttl_seconds": ttl,
            "operator_connection": operator_connection,
            "freshness": {
                "inventory_cached": inv_hit,
                "skills_installed_cached": sk_hit,
                "http_probe_cached": http_hit,
                "hermes_version_cached": ver_hit,
                "build_latency_ms": elapsed_ms,
            },
            "hermes_version": {
                "cli_report": ver,
            },
            "hermes_hub": hub,
            "runtime_inventory": inv_public,
            "skills_installed": skills_public,
            "http_gateway": http,
            "counts": {
                "tools_lines": tools_count,
                "plugins": plugins_count,
                "mcp": mcp_count,
                "skills_catalog": skills_catalog_count,
                "skills_installed": skills_installed_count,
                "droids_registered": droid_count,
            },
            "commands_and_menus": _commands_menu_surface(),
            "activity": activity,
            "external_runners": runners,
            "degraded_capabilities": degraded,
            "warnings": warnings,
            "future_adapter_placeholders": _future_placeholders(),
        }


_default: HermesGatewayBroker | None = None


def default_broker() -> HermesGatewayBroker:
    global _default
    if _default is None:
        _default = HermesGatewayBroker()
    return _default
