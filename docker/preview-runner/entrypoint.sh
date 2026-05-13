#!/usr/bin/env bash
# Spike stub: manual operators populate /workspace (bundle unpack) before npm commands.
set -euo pipefail

echo "ham-preview-runner: spike entrypoint"
echo "PREVIEW_SOURCE_URI=${PREVIEW_SOURCE_URI:-}"
echo "PREVIEW_PORT=${PREVIEW_PORT:-3000}"

if [[ ! -f /workspace/package.json ]]; then
  echo "No /workspace/package.json yet — fetch/unpack bundle here during manual spike." >&2
  exit 1
fi

exec npm run dev -- --host 0.0.0.0 --port "${PREVIEW_PORT}"
