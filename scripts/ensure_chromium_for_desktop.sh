#!/usr/bin/env bash
# Download Playwright's Chromium into ~/.cache/ms-playwright (no sudo).
# HAM Desktop Phase 4B auto-detects this path when system Chrome/Chromium is missing.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Missing $ROOT/.venv — create venv and pip install -r requirements.txt first." >&2
  exit 1
fi
exec "$ROOT/.venv/bin/python" -m playwright install chromium
