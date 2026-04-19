#!/usr/bin/env python3
"""
Merge `.env` secrets into `.gcloud/ham-api-env.yaml` for `gcloud run deploy --env-vars-file`.

Reads OPENROUTER_API_KEY (required when template uses openrouter), and optionally
DEFAULT_MODEL / HERMES_GATEWAY_MODEL from `.env`. Writes a temp YAML file and prints its path.

Usage:
  ENV_FILE=$(python scripts/render_cloud_run_env.py)
  gcloud run deploy ... --env-vars-file "$ENV_FILE"
  rm -f "$ENV_FILE"
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = REPO / ".gcloud" / "ham-api-env.yaml"


def _yaml_quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE,
        help="Base env YAML (default: .gcloud/ham-api-env.yaml)",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Print shell: export HAM_CLOUD_RUN_ENV_FILE=...",
    )
    args = parser.parse_args()

    load_dotenv(REPO / ".env")
    import os

    template_text = args.template.read_text()
    wants_openrouter = bool(
        re.search(r"^HERMES_GATEWAY_MODE:\s*openrouter\s*$", template_text, re.MULTILINE)
    )

    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if wants_openrouter and not key:
        print(
            "OPENROUTER_API_KEY missing in .env (required for openrouter deploy).",
            file=sys.stderr,
        )
        sys.exit(1)

    replacements: dict[str, str] = {}
    if key:
        replacements["OPENROUTER_API_KEY"] = key
    for env_name, yaml_key in (
        ("DEFAULT_MODEL", "DEFAULT_MODEL"),
        ("HERMES_GATEWAY_MODEL", "HERMES_GATEWAY_MODEL"),
    ):
        v = (os.environ.get(env_name) or "").strip()
        if v:
            replacements[yaml_key] = v

    lines = template_text.splitlines()
    out: list[str] = []
    keys_done: set[str] = set()

    for line in lines:
        m = re.match(r"^([A-Z][A-Z0-9_]*):\s*", line)
        if m and m.group(1) in replacements:
            name = m.group(1)
            out.append(f"{name}: {_yaml_quote(replacements[name])}")
            keys_done.add(name)
        else:
            out.append(line)

    insert_at = 0
    for i, ln in enumerate(out):
        if ln.startswith("HERMES_GATEWAY_MODE"):
            insert_at = i + 1
            break
    for name, val in replacements.items():
        if name not in keys_done:
            out.insert(insert_at, f"{name}: {_yaml_quote(val)}")
            insert_at += 1

    fd, path = tempfile.mkstemp(prefix="ham-cloud-run-env-", suffix=".yaml")
    with open(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")

    if args.export:
        print(f"export HAM_CLOUD_RUN_ENV_FILE={path}")
    else:
        print(path)


if __name__ == "__main__":
    main()
