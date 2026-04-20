#!/usr/bin/env python3
"""
Build ``src/ham/data/hermes_skills_catalog.json`` from a pinned NousResearch/hermes-agent tree.

Reads ``skills/`` (bundled) and ``optional-skills/`` (official optional) SKILL.md trees.
No runtime GitHub calls from the Ham API — run this script in CI or locally when bumping the pin.

Examples:
  python scripts/build_hermes_skills_catalog.py
  python scripts/build_hermes_skills_catalog.py --repo-root ~/src/hermes-agent
  python scripts/build_hermes_skills_catalog.py --output /tmp/catalog.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    print("PyYAML is required (pip install pyyaml).", file=sys.stderr)
    raise SystemExit(1) from exc

DEFAULT_COMMIT = "73d0b083510367adec42746e90c41ace16c0afb2"
REPO_ZIP_TMPL = "https://github.com/NousResearch/hermes-agent/archive/{sha}.tar.gz"
REPO_TOPDIR_TMPL = "hermes-agent-{sha}"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_frontmatter(skill_md: Path) -> dict[str, Any]:
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _norm_env_vars(raw: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, dict) and item.get("name"):
            name = str(item["name"])
            desc = item.get("prompt") or item.get("help") or item.get("description") or ""
            out.append({"name": name, "description": str(desc) if desc else ""})
    return out


def _config_keys_from_metadata(meta: Any) -> list[str]:
    if not isinstance(meta, dict):
        return []
    hermes = meta.get("hermes")
    if not isinstance(hermes, dict):
        return []
    cfg = hermes.get("config")
    if not isinstance(cfg, list):
        return []
    keys: list[str] = []
    for row in cfg:
        if isinstance(row, dict) and row.get("key"):
            keys.append(str(row["key"]))
    return keys


def _manifest_files(skill_dir: Path, *, max_files: int = 48) -> list[str]:
    paths: list[str] = []
    for p in sorted(skill_dir.rglob("*")):
        if p.is_file() and ".git" not in p.parts:
            try:
                rel = p.relative_to(skill_dir).as_posix()
            except ValueError:
                continue
            paths.append(rel)
            if len(paths) >= max_files:
                break
    return paths


def _discover_skills(repo_root: Path, commit_sha: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    specs: list[tuple[str, str, str, str]] = [
        ("skills", "bundled", "builtin", "skills"),
        ("optional-skills", "official", "official", "optional-skills"),
    ]
    for subdir, prefix, trust_level, source_label in specs:
        base = repo_root / subdir
        if not base.is_dir():
            continue
        for skill_md in sorted(base.rglob("SKILL.md")):
            skill_dir = skill_md.parent
            try:
                rel_dir = skill_dir.relative_to(base)
            except ValueError:
                continue
            parts = rel_dir.parts
            catalog_id = prefix + "." + ".".join(parts) if parts else prefix
            rel_in_repo = f"{subdir}/{rel_dir.as_posix()}"

            fm = _parse_frontmatter(skill_md)
            name = str(fm.get("name") or parts[-1] if parts else skill_dir.name)
            desc = fm.get("description")
            summary = str(desc).strip() if desc is not None else ""
            version_pin = str(fm.get("version") or "0.0.0")

            platforms_raw = fm.get("platforms")
            if isinstance(platforms_raw, list):
                platforms = [str(p) for p in platforms_raw]
            elif platforms_raw is None:
                platforms = ["linux", "macos", "windows"]
            else:
                platforms = [str(platforms_raw)]

            req_env = _norm_env_vars(fm.get("required_environment_variables"))
            config_keys = _config_keys_from_metadata(fm.get("metadata"))

            has_scripts = (skill_dir / "scripts").is_dir()

            content_hash = _sha256_file(skill_md)

            if prefix == "official":
                official_cli_path = "/".join(parts)
                source_ref = f"official/{official_cli_path}"
            else:
                source_ref = f"NousResearch/hermes-agent@{commit_sha[:12]}:{rel_in_repo}"

            entry = {
                "catalog_id": catalog_id,
                "display_name": name,
                "summary": summary[:2000] if summary else f"Hermes {prefix} skill ({rel_in_repo}).",
                "trust_level": trust_level,
                "source_kind": "hermes_repo_pin",
                "source_ref": source_ref,
                "version_pin": version_pin,
                "content_hash_sha256": content_hash,
                "platforms": platforms,
                "required_environment_variables": req_env,
                "config_keys": config_keys,
                "has_scripts": has_scripts,
                "installable_by_default": trust_level in ("builtin", "official"),
                "detail": {
                    "provenance_note": (
                        f"Generated from NousResearch/hermes-agent @ {commit_sha} ({source_label}/{rel_dir.as_posix() if parts else subdir}). "
                        "Read-only catalog; install not performed by Ham in Phase 1."
                    ),
                    "warnings": [],
                    "manifest_files": _manifest_files(skill_dir),
                },
            }
            entries.append(entry)

    entries.sort(key=lambda e: e["catalog_id"])
    return entries


def _fetch_repo_archive(commit_sha: str) -> Path:
    url = REPO_ZIP_TMPL.format(sha=commit_sha)
    tmp = Path(tempfile.mkdtemp(prefix="ham-hermes-src-"))
    archive = tmp / "repo.tar.gz"
    try:
        urllib.request.urlretrieve(url, archive)
        with tarfile.open(archive, "r:gz") as tf:
            if sys.version_info >= (3, 12):
                tf.extractall(tmp, filter="data")
            else:
                tf.extractall(tmp)
    finally:
        archive.unlink(missing_ok=True)
    top = tmp / REPO_TOPDIR_TMPL.format(sha=commit_sha)
    if not top.is_dir():
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError(f"Expected extracted directory {top} after fetching {url}")
    return top


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit-sha",
        default=DEFAULT_COMMIT,
        help=f"hermes-agent git SHA (default: {DEFAULT_COMMIT[:12]}…)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Use existing checkout instead of downloading GitHub archive.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "src" / "ham" / "data" / "hermes_skills_catalog.json",
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Require --repo-root (do not download).",
    )
    args = parser.parse_args()
    commit_sha = args.commit_sha.strip()
    cleanup: Path | None = None
    repo_root: Path
    if args.repo_root:
        repo_root = args.repo_root.resolve()
        if not (repo_root / "skills").is_dir() and not (repo_root / "optional-skills").is_dir():
            print(f"Repo root missing skills/ or optional-skills/: {repo_root}", file=sys.stderr)
            raise SystemExit(1)
    else:
        if args.no_fetch:
            print("Provide --repo-root or omit --no-fetch to download.", file=sys.stderr)
            raise SystemExit(1)
        print(f"Fetching {REPO_ZIP_TMPL.format(sha=commit_sha)} …", file=sys.stderr)
        repo_root = _fetch_repo_archive(commit_sha)
        cleanup = repo_root.parent

    try:
        entries = _discover_skills(repo_root, commit_sha)
    finally:
        if cleanup is not None:
            shutil.rmtree(cleanup, ignore_errors=True)

    out = {
        "schema_version": 1,
        "catalog_note": (
            f"Generated by scripts/build_hermes_skills_catalog.py from NousResearch/hermes-agent @ {commit_sha}. "
            "Bundled skills → catalog_id prefix `bundled.` (trust builtin). "
            "optional-skills → prefix `official.` (trust official). "
            "Regenerate when bumping the pin."
        ),
        "upstream": {
            "repo": "NousResearch/hermes-agent",
            "commit": commit_sha,
        },
        "entries": entries,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(entries)} entries to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
