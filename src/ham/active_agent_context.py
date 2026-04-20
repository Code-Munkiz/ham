"""Resolve HAM Agent Builder profile + Hermes catalog skill summaries for chat guidance (context only)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.ham.agent_profiles import HamAgentProfile, HamAgentsConfig, agents_config_from_merged
from src.ham.hermes_skills_catalog import get_catalog_entry_detail
from src.memory_heist import discover_config

logger = logging.getLogger(__name__)

_MAX_SKILL_SUMMARY_CHARS = 160
_MAX_SKILLS_LISTED = 16
_MAX_GUIDANCE_CHARS = 2800


@dataclass(frozen=True)
class ActiveAgentGuidanceResult:
    """Compact guidance text for system prompt + HAM-owned metadata for API responses."""

    guidance_text: str
    meta: dict[str, Any]


def _primary_profile(cfg: HamAgentsConfig) -> HamAgentProfile:
    for p in cfg.profiles:
        if p.id == cfg.primary_agent_id:
            return p
    return cfg.profiles[0]


def build_active_agent_guidance(profile: HamAgentProfile) -> ActiveAgentGuidanceResult:
    """Compose bounded markdown guidance from the active profile and vendored catalog entries."""
    lines: list[str] = [
        "## HAM active agent guidance",
        "",
        "Project-configured assistant (Agent Builder). **Context only** — does not enable tools, "
        "does not execute attached catalog entries, and does not imply they are installed on the server.",
        "",
        f"- **Agent:** {profile.name.strip()} (`{profile.id}`)",
    ]
    if profile.enabled is False:
        lines.append(
            "- **Builder status:** marked disabled — guidance still included so the model knows the setting.",
        )
    desc = (profile.description or "").strip()
    if desc:
        cap = 400
        short = desc[:cap] + ("…" if len(desc) > cap else "")
        lines.append(f"- **Description:** {short}")

    skills_requested = len(profile.skills)
    skills_resolved = 0
    skills_skipped = 0
    skill_lines: list[str] = []

    if profile.skills:
        lines.append(
            "- **Attached Hermes runtime catalog skills** (names/summaries from the vendored catalog only):",
        )
        for sid in profile.skills[:_MAX_SKILLS_LISTED]:
            detail = get_catalog_entry_detail(sid)
            if detail is None:
                skills_skipped += 1
                continue
            skills_resolved += 1
            dn = str(detail.get("display_name") or sid).strip() or sid
            trust = str(detail.get("trust_level") or "").strip()
            summ = str(detail.get("summary") or "").strip()
            if len(summ) > _MAX_SKILL_SUMMARY_CHARS:
                summ = summ[: _MAX_SKILL_SUMMARY_CHARS - 1] + "…"
            trust_part = f", {trust}" if trust else ""
            skill_lines.append(f"  - **{dn}** (`{sid}`{trust_part}): {summ}")
        lines.extend(skill_lines)
        remainder = len(profile.skills) - min(len(profile.skills), _MAX_SKILLS_LISTED)
        if remainder > 0:
            lines.append(
                f"- **Note:** {remainder} additional skill id(s) omitted here (listing cap {_MAX_SKILLS_LISTED}).",
            )
        if skills_skipped:
            lines.append(
                f"- **Note:** {skills_skipped} id(s) missing from the vendored catalog — omitted from this list.",
            )
    else:
        lines.append("- **Attached Hermes runtime catalog skills:** none.")

    text = "\n".join(lines).strip()
    if len(text) > _MAX_GUIDANCE_CHARS:
        text = text[: _MAX_GUIDANCE_CHARS - 1] + "…"

    meta: dict[str, Any] = {
        "profile_id": profile.id,
        "profile_name": profile.name.strip(),
        "skills_requested": skills_requested,
        "skills_resolved": skills_resolved,
        "skills_skipped_catalog_miss": skills_skipped,
        "guidance_applied": True,
    }
    return ActiveAgentGuidanceResult(guidance_text=text, meta=meta)


def try_active_agent_guidance_for_project_root(root: Path) -> ActiveAgentGuidanceResult | None:
    """Load merged config for ``root`` and build guidance; return ``None`` on failure (chat continues)."""
    try:
        resolved = root.expanduser().resolve()
        if not resolved.is_dir():
            return None
        merged = discover_config(resolved).merged
        cfg = agents_config_from_merged(merged)
        profile = _primary_profile(cfg)
        return build_active_agent_guidance(profile)
    except OSError as exc:
        logger.debug("active agent guidance: bad project root %s: %s", root, exc)
        return None
    except Exception as exc:
        logger.warning("active agent guidance: unexpected error for %s: %s", root, exc)
        return None
