"""Read-only probe: Hermes home layout and future install targets (Phase 1, no mutations)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _resolve_hermes_home_path() -> Path:
    """Resolve default Hermes user home (not a specific profile)."""
    for key in ("HAM_HERMES_HOME", "HERMES_HOME"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return Path(raw).expanduser().resolve()
    return (Path.home() / ".hermes").resolve()


def probe_capabilities() -> dict[str, Any]:
    """
    Report whether this API host can observe a local Hermes layout.

    Set ``HAM_HERMES_SKILLS_MODE=remote_only`` when the API is deployed without
    co-located Hermes (e.g. Cloud Run) so the UI does not imply install readiness.
    """
    warnings: list[str] = []
    forced = (os.environ.get("HAM_HERMES_SKILLS_MODE") or "").strip().lower()
    hermes_path = _resolve_hermes_home_path()
    exists = hermes_path.is_dir()

    if forced == "remote_only":
        if exists:
            warnings.append(
                "Hermes home path exists on this host but HAM_HERMES_SKILLS_MODE=remote_only; "
                "install flows remain disabled for this deployment configuration."
            )
        else:
            warnings.append(
                "HAM_HERMES_SKILLS_MODE=remote_only: API is not co-located with operator Hermes home; "
                "Phase 2+ installs require a local or volume-mounted Hermes environment."
            )
        return {
            "hermes_home_detected": exists,
            "hermes_home_path_hint": str(hermes_path) if exists else None,
            "shared_target_supported": False,
            "profile_target_supported": False,
            "profile_listing_supported": False,
            "mode": "remote_only",
            "warnings": warnings,
        }

    if not exists:
        warnings.append(
            "Hermes home directory not found. Install Hermes CLI locally or set HERMES_HOME / HAM_HERMES_HOME."
        )
        return {
            "hermes_home_detected": False,
            "hermes_home_path_hint": None,
            "shared_target_supported": False,
            "profile_target_supported": False,
            "profile_listing_supported": False,
            "mode": "unsupported",
            "warnings": warnings,
        }

    profiles_dir = hermes_path / "profiles"
    profile_names: list[str] = []
    profile_listing_supported = False
    if profiles_dir.is_dir():
        try:
            profile_names = sorted(
                p.name
                for p in profiles_dir.iterdir()
                if p.is_dir() and not p.name.startswith(".")
            )
            profile_listing_supported = True
        except OSError as exc:
            warnings.append(f"Could not list Hermes profiles directory: {exc}")
    else:
        warnings.append(
            "No ~/.hermes/profiles directory yet; Hermes profile targets will appear after profiles are created."
        )

    # Shared layer = default Hermes home config scope (Phase 2 will wire external_dirs).
    shared_target_supported = True
    profile_target_supported = profile_listing_supported

    return {
        "hermes_home_detected": True,
        "hermes_home_path_hint": str(hermes_path),
        "shared_target_supported": shared_target_supported,
        "profile_target_supported": profile_target_supported,
        "profile_listing_supported": profile_listing_supported,
        "mode": "local",
        "warnings": warnings,
        "profile_count": len(profile_names),
    }


def list_hermes_targets() -> dict[str, Any]:
    """
    Read-only install target discovery for Hermes runtime (not Ham IntentProfile, not Cursor subagents).
    """
    caps = probe_capabilities()
    targets: list[dict[str, Any]] = []

    shared_available = bool(
        caps.get("hermes_home_detected") and caps.get("shared_target_supported")
    )
    targets.append(
        {
            "kind": "shared",
            "id": "default",
            "label": "Default Hermes home (shared skills layer)",
            "available": shared_available,
            "notes": "Phase 2 will attach a HAM-managed bundle via Hermes skills.external_dirs.",
        }
    )

    if caps.get("mode") != "local" or not caps.get("hermes_home_path_hint"):
        return {"targets": targets, "capabilities": caps}

    hermes_path = Path(caps["hermes_home_path_hint"])
    profiles_dir = hermes_path / "profiles"
    if not caps.get("profile_listing_supported") or not profiles_dir.is_dir():
        return {"targets": targets, "capabilities": caps}

    try:
        names = sorted(
            p.name
            for p in profiles_dir.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        )
    except OSError:
        return {"targets": targets, "capabilities": caps}

    for name in names:
        targets.append(
            {
                "kind": "hermes_profile",
                "id": name,
                "label": f"Hermes profile: {name}",
                "available": True,
                "notes": "Hermes CLI profile (see `hermes profile list`); not a Ham bridge IntentProfile.",
            }
        )

    return {"targets": targets, "capabilities": caps}
