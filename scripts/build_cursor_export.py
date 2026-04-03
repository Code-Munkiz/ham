"""One-off builder for CURSOR_EXACT_SETUP_EXPORT.md (verbatim embed)."""
from __future__ import annotations

from pathlib import Path

FENCE = "```"

def main() -> None:
    root = Path(__file__).resolve().parent.parent
    rules = sorted(root.glob(".cursor/rules/*.mdc"))
    skills = sorted(root.glob(".cursor/skills/*/SKILL.md"))
    ctx = [
        root / "AGENTS.md",
        root / "VISION.md",
        root / "GAPS.md",
        root / "docs" / "HAM_HARDENING_REMEDIATION.md",
    ]
    lines: list[str] = []
    lines.append("# Cursor setup — exact export")
    lines.append("")
    lines.append(
        "Generated snapshot of `.cursor/` rules and skills, plus first-class "
        "context documents from the handoff source-of-truth list."
    )
    lines.append("")
    lines.append("## File counts (this document)")
    lines.append("")
    lines.append("| Category | Count |")
    lines.append("|----------|-------|")
    lines.append(f"| Rules (`.mdc`) | {len(rules)} |")
    lines.append(f"| Skills (`SKILL.md`) | {len(skills)} |")
    lines.append(f"| First-class context | {len(ctx)} |")
    lines.append(f"| **Total embedded files** | **{len(rules) + len(skills) + len(ctx)}** |")
    lines.append("")
    lines.append(
        "**Subagents** (4): `subagent-*.mdc`. **Commands**: embedded in `commands.mdc`."
    )
    lines.append("")
    lines.append(
        "**Not embedded**: `README.md`, `SWARM.md`, `main.py`, pillar modules under "
        "`src/`, directory `tests/`, optional `.ham.json` / `.ham/settings.json`."
    )
    lines.append("")
    lines.append(
        "**Ambiguity / drift**: Rules and skills may describe behaviors (e.g. "
        "`MAX_DIFF_CHARS`, `ProjectContext.render` budget args) not yet present in "
        "`src/memory_heist.py`; verify against current code."
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    def emit(path: Path) -> None:
        rel = path.relative_to(root).as_posix()
        lines.append(f"## `{rel}`")
        lines.append("")
        lines.append(FENCE)
        lines.append(path.read_text(encoding="utf-8").rstrip())
        lines.append(FENCE)
        lines.append("")
        lines.append("---")
        lines.append("")

    for p in rules:
        emit(p)
    for p in skills:
        emit(p)
    for p in ctx:
        emit(p)

    out = root / "CURSOR_EXACT_SETUP_EXPORT.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out, out.stat().st_size)


if __name__ == "__main__":
    main()
