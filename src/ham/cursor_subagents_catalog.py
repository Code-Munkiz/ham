"""
Load Cursor subagent rule stubs from ``.cursor/rules/subagent-*.mdc``.

These are **review/audit charters** (specialized Cursor subagents), not executable
skills. Used by ``GET /api/cursor-subagents`` and optional chat system-prompt context.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    raw = (os.environ.get("HAM_REPO_ROOT") or "").strip()
    if raw:
        return Path(raw).resolve()
    return Path.cwd().resolve()


def _parse_mdc_frontmatter(content: str) -> dict[str, Any]:
    """Parse a minimal YAML-like frontmatter block (first ``---`` fence)."""
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    fm = parts[1]
    body = parts[2]
    out: dict[str, Any] = {"_body": body}
    for raw_line in fm.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("description:"):
            val = line.split(":", 1)[1].strip()
            if (val.startswith('"') and val.endswith('"')) or (
                val.startswith("'") and val.endswith("'")
            ):
                val = val[1:-1]
            out["description"] = val
        elif line.startswith("globs:"):
            out["globs"] = line.split(":", 1)[1].strip() or None
        elif line.startswith("alwaysApply:"):
            v = line.split(":", 1)[1].strip().lower()
            out["always_apply"] = v == "true"
    return out


def _first_markdown_heading(body: str) -> str | None:
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return None


_SUBAGENT_FILE_RE = re.compile(r"^subagent-.+\.mdc$")


def list_cursor_subagents(*, repo_root: Path | None = None) -> list[dict[str, Any]]:
    """
    Return subagent records for ``.cursor/rules/subagent-*.mdc``, sorted by id.

    Each record: ``id``, ``title``, ``description``, ``globs``, ``always_apply``, ``path``.
    """
    root = repo_root or _repo_root()
    rules_dir = root / ".cursor" / "rules"
    if not rules_dir.is_dir():
        return []

    out: list[dict[str, Any]] = []
    for path in sorted(rules_dir.iterdir()):
        if not path.is_file():
            continue
        if not _SUBAGENT_FILE_RE.match(path.name):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = _parse_mdc_frontmatter(text)
        body = str(fm.pop("_body", "") or "")
        subagent_id = path.stem  # e.g. subagent-context-engine-auditor
        title = _first_markdown_heading(body) or subagent_id
        desc = str(fm.get("description") or "").strip()
        globs = fm.get("globs")
        if globs is not None and isinstance(globs, str):
            globs = globs.strip() or None
        always_apply = bool(fm.get("always_apply", False))
        try:
            rel_path = str(path.relative_to(root))
        except ValueError:
            rel_path = str(path)
        out.append(
            {
                "id": subagent_id,
                "title": title,
                "description": desc,
                "globs": globs,
                "always_apply": always_apply,
                "path": rel_path,
            }
        )
    return out


def render_subagents_for_system_prompt(
    subagents: list[dict[str, Any]],
    *,
    max_chars: int = 2_800,
) -> str:
    """Compact block for LLM system context (charters + globs; not full rule bodies)."""
    if not subagents:
        return ""

    lines = [
        "**Cursor subagent rules (Ham repo `.cursor/rules/subagent-*.mdc`; review/audit charters for specialized checks):**",
        "",
    ]
    for s in subagents:
        sid = s.get("id", "")
        title = s.get("title") or sid
        desc = (s.get("description") or "").replace("\n", " ").strip()
        if len(desc) > 280:
            desc = desc[:277] + "…"
        globs = s.get("globs")
        glob_s = f" · `globs: {globs}`" if globs else ""
        aa = " · alwaysApply" if s.get("always_apply") else ""
        lines.append(f"- `{sid}` — **{title}**: {desc}{glob_s}{aa}")
        lines.append("")

    text = "\n".join(lines).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"
