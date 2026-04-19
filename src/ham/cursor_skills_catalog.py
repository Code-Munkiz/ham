"""
Load Ham operator skills from `.cursor/skills/*/SKILL.md` for the chat control plane.

Used by GET /api/cursor-skills and optional chat system-prompt injection. Cursor
subagent *rules* (.mdc) are not shipped here—only skills the team combines for intents.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    raw = (os.environ.get("HAM_REPO_ROOT") or "").strip()
    if raw:
        return Path(raw).resolve()
    return Path.cwd().resolve()


def _parse_skill_frontmatter(content: str) -> dict[str, str]:
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    fm = parts[1]
    out: dict[str, str] = {}
    lines = fm.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("name:"):
            out["name"] = line.split(":", 1)[1].strip().strip('"').strip("'")
        elif line.startswith("description:"):
            rest = line.split(":", 1)[1].strip()
            if rest in (">-", ">", "|"):
                i += 1
                chunks: list[str] = []
                while i < len(lines):
                    ln = lines[i]
                    if not ln.strip():
                        i += 1
                        continue
                    if ln.startswith("  "):
                        chunks.append(ln.strip())
                        i += 1
                        continue
                    break
                out["description"] = " ".join(chunks)
                continue
            out["description"] = rest
        i += 1
    return out


def list_cursor_skills(*, repo_root: Path | None = None) -> list[dict[str, Any]]:
    """Return skill records sorted by id (directory name)."""
    root = repo_root or _repo_root()
    skills_dir = root / ".cursor" / "skills"
    if not skills_dir.is_dir():
        return []

    out: list[dict[str, Any]] = []
    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir():
            continue
        md = child / "SKILL.md"
        if not md.is_file():
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = _parse_skill_frontmatter(text)
        skill_id = child.name
        name = fm.get("name") or skill_id
        desc = (fm.get("description") or "").strip()
        try:
            rel_path = str(md.relative_to(root))
        except ValueError:
            rel_path = str(md)
        out.append(
            {
                "id": skill_id,
                "name": name,
                "description": desc,
                "path": rel_path,
            }
        )
    return out


def render_skills_for_system_prompt(
    skills: list[dict[str, Any]],
    *,
    max_chars: int = 4_000,
) -> str:
    """Compact block for LLM system context (operator intents, not full SKILL bodies)."""
    if not skills:
        return ""

    lines = [
        "**Operator skills (Ham repo `.cursor/skills`; use these to map user intents to workflows):**",
        "",
    ]
    for s in skills:
        sid = s.get("id", "")
        name = s.get("name", sid)
        desc = (s.get("description") or "").replace("\n", " ").strip()
        if len(desc) > 320:
            desc = desc[:317] + "…"
        lines.append(f"- `{sid}` — **{name}**: {desc}")
        lines.append("")

    text = "\n".join(lines).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"
