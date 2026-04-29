"""Read-only live Hermes skills observation via allowlisted ``hermes skills list`` (v1 overlay).

Does not mutate Hermes home, does not install skills, does not read arbitrary trees.
"""
from __future__ import annotations

import os
import subprocess
from typing import Any

from src.ham.hermes_runtime_inventory import (
    cap_raw,
    redact_paths,
    redact_secrets,
    resolve_hermes_cli_binary,
)
from src.ham.hermes_skills_catalog import list_catalog_entries
from src.ham.hermes_skills_probe import _resolve_hermes_home_path, probe_capabilities

_KIND = "hermes_skills_live_overlay"
_ALLOWED_SUFFIX: tuple[str, ...] = ("skills", "list", "--source", "all")
_CMD_TIMEOUT_S = 25.0
_RAW_CAP = 12_000
_MAX_PARSE_ROWS = 500
_MAX_CELL_CHARS = 256


def _normalize_join_key(s: str) -> str:
    return " ".join(s.strip().lower().split())


def _final_catalog_segment(catalog_id: str) -> str:
    parts = catalog_id.strip().split(".")
    return parts[-1] if parts else ""


def _run_skills_list(hermes_bin: str, *, env: dict[str, str]) -> tuple[int, str, str]:
    cmd = [hermes_bin, *_ALLOWED_SUFFIX]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_CMD_TIMEOUT_S,
            env=env,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except OSError as exc:
        return 1, "", str(exc)
    out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    return proc.returncode, out.strip(), (proc.stderr or "").strip()


def _parse_skills_list_output(text: str) -> tuple[list[dict[str, str]], list[str]]:
    """Parse Rich/box table rows from ``hermes skills list`` stdout."""
    warnings: list[str] = []
    rows: list[dict[str, str]] = []
    seen_name_keys: set[str] = set()

    for line in text.splitlines():
        if "│" not in line:
            continue
        # Data rows use light vertical bar; skip heavy box lines.
        if any(c in line for c in ("┏", "┗", "┣", "┡", "━")):
            continue
        parts = line.split("│")
        if len(parts) < 5:
            continue
        name = parts[1].strip()[:_MAX_CELL_CHARS]
        category = parts[2].strip()[:_MAX_CELL_CHARS]
        source = parts[3].strip()[:_MAX_CELL_CHARS]
        trust = parts[4].strip()[:_MAX_CELL_CHARS]
        if not name:
            continue
        if name.lower() == "name" and category.lower() == "category":
            continue
        nk = _normalize_join_key(name)
        if nk in seen_name_keys:
            continue
        seen_name_keys.add(nk)
        rows.append(
            {
                "name": name,
                "category": category,
                "hermes_source": source,
                "hermes_trust": trust,
            }
        )
        if len(rows) >= _MAX_PARSE_ROWS:
            warnings.append(f"Live skills list capped at {_MAX_PARSE_ROWS} unique rows.")
            break

    return rows, warnings


def _build_catalog_indexes(
    entries: list[dict[str, Any]],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Map normalized display_name / final segment -> catalog_ids (may be ambiguous)."""
    by_display: dict[str, list[str]] = {}
    by_segment: dict[str, list[str]] = {}
    for e in entries:
        cid = str(e.get("catalog_id") or "")
        if not cid:
            continue
        dn = _normalize_join_key(str(e.get("display_name") or ""))
        if dn:
            by_display.setdefault(dn, []).append(cid)
        seg = _normalize_join_key(_final_catalog_segment(cid))
        if seg and len(seg) >= 2:
            by_segment.setdefault(seg, []).append(cid)
    for m in (by_display, by_segment):
        for k in m:
            m[k] = sorted(set(m[k]))
    return by_display, by_segment


def _resolve_live_row_to_catalog_id(
    name: str,
    *,
    by_display: dict[str, list[str]],
    by_segment: dict[str, list[str]],
) -> tuple[str | None, str]:
    """Return (catalog_id or None, resolution for this live row: linked | live_only | unknown)."""
    nk = _normalize_join_key(name)
    if not nk:
        return None, "unknown"

    prim = by_display.get(nk)
    if prim:
        if len(prim) == 1:
            return prim[0], "linked"
        return None, "unknown"

    seg_matches = by_segment.get(nk)
    if seg_matches and len(seg_matches) == 1:
        return seg_matches[0], "linked"

    return None, "live_only"


def build_skills_installed_overlay() -> dict[str, Any]:
    """CLI-backed live skills + join to vendored catalog (additive; catalog remains authority)."""
    caps = probe_capabilities()
    mode = str(caps.get("mode") or "unsupported")
    warnings: list[str] = list(caps.get("warnings") or [])
    hermes_home_path = _resolve_hermes_home_path()
    home_hint = str(hermes_home_path) if caps.get("hermes_home_detected") else None

    catalog_entries = list_catalog_entries()
    by_display, by_segment = _build_catalog_indexes(catalog_entries)

    empty: dict[str, Any] = {
        "kind": _KIND,
        "status": "unavailable",
        "cli_source": "hermes skills list --source all",
        "live_count": 0,
        "linked_count": 0,
        "live_only_count": 0,
        "unknown_count": 0,
        "catalog_only_count": len(catalog_entries),
        "installations": [],
        "warnings": warnings,
        "raw_redacted": "",
    }

    if mode == "remote_only":
        warnings.append(
            "Live Hermes skills CLI observation is disabled (HAM_HERMES_SKILLS_MODE=remote_only).",
        )
        return {
            **empty,
            "status": "remote_only",
            "warnings": warnings,
        }

    binary = resolve_hermes_cli_binary()
    if not binary:
        warnings.append(
            "Hermes CLI not found on PATH (install Hermes or set HAM_HERMES_CLI_PATH).",
        )
        return {
            **empty,
            "status": "unavailable",
            "warnings": warnings,
        }

    env = os.environ.copy()
    if home_hint:
        env["HERMES_HOME"] = str(hermes_home_path.expanduser().resolve())
        env.setdefault("HAM_HERMES_HOME", env["HERMES_HOME"])

    code, combined, err_tail = _run_skills_list(binary, env=env)
    redacted = redact_paths(redact_secrets(combined), home_hint)
    raw_redacted = cap_raw(redacted)
    if err_tail:
        err_r = redact_paths(redact_secrets(err_tail), home_hint)
        raw_redacted = cap_raw(redacted + (f"\nstderr: {err_r}" if err_r else ""))

    if code != 0:
        warnings.append(
            f"Hermes skills list exited with code {code}; live overlay unavailable.",
        )
        return {
            **empty,
            "status": "error",
            "warnings": warnings,
            "raw_redacted": raw_redacted,
        }

    parsed, parse_warnings = _parse_skills_list_output(combined)
    warnings.extend(parse_warnings)

    installations: list[dict[str, Any]] = []
    linked_ids: set[str] = set()
    linked_n = live_only_n = unknown_n = 0

    for row in parsed:
        cid, res = _resolve_live_row_to_catalog_id(
            row["name"],
            by_display=by_display,
            by_segment=by_segment,
        )
        if res == "linked" and cid:
            linked_ids.add(cid)
            linked_n += 1
        elif res == "live_only":
            live_only_n += 1
        else:
            unknown_n += 1
        installations.append(
            {
                "name": row["name"],
                "category": row["category"],
                "hermes_source": row["hermes_source"],
                "hermes_trust": row["hermes_trust"],
                "catalog_id": cid,
                "resolution": res,
            }
        )

    catalog_only = len(catalog_entries) - len(linked_ids)
    st = "ok"
    if unknown_n > 0:
        warnings.append(
            "One or more live skills could not be linked to a unique catalog id "
            "(duplicate display_name or ambiguous name).",
        )
    if not parsed and combined.strip():
        st = "parse_degraded"
        warnings.append(
            "Could not parse rows from hermes skills list output; CLI format may have changed.",
        )

    return {
        "kind": _KIND,
        "status": st,
        "cli_source": "hermes skills list --source all",
        "live_count": len(installations),
        "linked_count": linked_n,
        "live_only_count": live_only_n,
        "unknown_count": unknown_n,
        "catalog_only_count": max(0, catalog_only),
        "installations": installations,
        "warnings": warnings,
        "raw_redacted": raw_redacted,
    }
