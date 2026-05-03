#!/usr/bin/env python3
"""Doc freshness + reference validator (Phase B baseline).

Runs in CI as **warning-only** until the team is comfortable making it
blocking. Run locally:

    python scripts/check_docs_freshness.py

Behavior:
- Confirms each tracked canonical doc was modified within FRESHNESS_DAYS.
- Confirms inline relative paths in those docs still resolve on disk.
- Exits 0 on success, 1 on any failure. Output is human-readable.

Intentionally read-only. Does NOT touch files, secrets, or git history.
Does NOT print contents of `.env`, `.ham/`, `.data/`, or provider data.
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Canonical docs we track for freshness. Add narrowly; broad lists create churn.
CANONICAL_DOCS = [
    "README.md",
    "AGENTS.md",
    "VISION.md",
    "PRODUCT_DIRECTION.md",
    "GAPS.md",
    "docs/README.md",
]

# How recent a doc must be (last commit touching it) to count as "fresh".
FRESHNESS_DAYS = 180

# Match clearly-file-shaped paths in markdown to keep false positives low:
# - markdown link targets `[text](relative/path)` (the most reliable signal)
# - inline-code that looks like `dir/file.ext` (must contain a slash)
# Things we deliberately skip: CLI invocations, glob patterns, env-style
# paths in angle brackets, dotted module paths, attribute references.
PATH_LIKE = re.compile(
    r"""
    (?:
        \[[^\]]+\]\(([^)#\s]+)\)         # markdown link
        |
        `([A-Za-z0-9_./\-]+/[A-Za-z0-9_./\-]+\.[A-Za-z0-9]+)`  # `dir/file.ext`
    )
    """,
    re.VERBOSE,
)

URL_PREFIX = re.compile(r"^(?:https?:|mailto:|tel:|//|#)")
SKIP_TOKENS = ("*", "<", ">", "{", "}", " ")
TOP_LEVEL_HINTS = (
    "src/",
    "frontend/",
    "desktop/",
    "docs/",
    "tests/",
    "scripts/",
    ".github/",
    ".cursor/",
    "configs/",
    "config/",
    "models/",
    "assets/",
    "main.py",
    "README",
    "AGENTS",
    "VISION",
    "GAPS",
    "PRODUCT_DIRECTION",
    "SWARM",
    "Dockerfile",
)


def last_commit_iso(path: Path) -> str | None:
    """Return the ISO date of the last commit touching `path`, or None."""
    try:
        out = subprocess.check_output(
            ["git", "log", "-1", "--format=%cI", "--", str(path.relative_to(REPO_ROOT))],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        return None
    return out or None


def strip_fences(text: str) -> str:
    """Remove fenced code blocks so we don't lint shell snippets as paths."""
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def extract_relative_paths(md_text: str) -> list[str]:
    out: list[str] = []
    for match in PATH_LIKE.finditer(strip_fences(md_text)):
        candidate = match.group(1) or match.group(2) or ""
        candidate = candidate.strip()
        if not candidate:
            continue
        if URL_PREFIX.match(candidate):
            continue
        if any(tok in candidate for tok in SKIP_TOKENS):
            continue
        # Strip query strings / anchors
        candidate = candidate.split("#", 1)[0].split("?", 1)[0]
        if not candidate:
            continue
        # Only check candidates that look clearly path-shaped to avoid
        # false positives on CLI strings, attribute paths, or env names.
        looks_path_like = (
            candidate.startswith(TOP_LEVEL_HINTS)
            or candidate.startswith("./")
            or candidate.startswith("../")
            or any(candidate.startswith(t) for t in ("src/", "tests/", "frontend/", "desktop/", "docs/"))
        )
        if not looks_path_like:
            continue
        out.append(candidate)
    return out


def check_freshness(doc: Path, now: datetime) -> str | None:
    iso = last_commit_iso(doc)
    if iso is None:
        return f"WARN  {doc.relative_to(REPO_ROOT)}: no git history found"
    last = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    age = now - last
    if age > timedelta(days=FRESHNESS_DAYS):
        return (
            f"WARN  {doc.relative_to(REPO_ROOT)}: last touched "
            f"{age.days} days ago (>{FRESHNESS_DAYS}d)"
        )
    return None


def _exists(target: Path) -> bool:
    if target.exists():
        return True
    return Path(str(target).rstrip("/")).exists()


def check_references(doc: Path) -> list[str]:
    issues: list[str] = []
    text = doc.read_text(encoding="utf-8", errors="replace")
    for raw in extract_relative_paths(text):
        # Try resolving relative to the doc first (markdown convention),
        # then fall back to repo root. Either match counts as resolved.
        candidates = [
            (doc.parent / raw).resolve(),
            (REPO_ROOT / raw).resolve(),
        ]
        if any(_exists(c) for c in candidates):
            continue
        issues.append(
            f"WARN  {doc.relative_to(REPO_ROOT)}: dangling reference -> {raw}"
        )
    return issues


def main() -> int:
    now = datetime.now(timezone.utc)
    findings: list[str] = []

    for rel in CANONICAL_DOCS:
        doc = (REPO_ROOT / rel).resolve()
        if not doc.exists():
            findings.append(f"WARN  {rel}: not found")
            continue
        f = check_freshness(doc, now)
        if f:
            findings.append(f)
        findings.extend(check_references(doc))

    if findings:
        print("Documentation freshness/reference findings:")
        for line in findings:
            print(f"  {line}")
        # Non-zero exit so CI surfaces it; CI wires this with continue-on-error
        # so it stays warning-only until the team is ready to enforce.
        return 1

    print("OK: canonical docs are fresh and references resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
