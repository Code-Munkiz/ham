#!/usr/bin/env bash
set -euo pipefail

echo "ham-preview-runner: spike entrypoint"
echo "PREVIEW_SOURCE_URI_SET=$([[ -n "${PREVIEW_SOURCE_URI:-}" ]] && echo true || echo false)"
echo "PREVIEW_PORT=${PREVIEW_PORT:-3000}"

if [[ ! -f /workspace/package.json ]]; then
  if [[ -z "${PREVIEW_SOURCE_URI:-}" ]]; then
    echo "No /workspace/package.json and PREVIEW_SOURCE_URI is empty." >&2
    exit 1
  fi
  echo "Downloading and unpacking preview source bundle into /workspace"
  python3 /usr/local/bin/ham-preview-download-source.py --source-uri "${PREVIEW_SOURCE_URI}" --destination /workspace
fi

if [[ ! -f /workspace/package.json ]]; then
  echo "Source materialized but /workspace/package.json is missing." >&2
  exit 1
fi

if [[ -f /workspace/package-lock.json ]]; then
  echo "package-lock.json detected; running npm ci"
  npm ci --no-audit --no-fund
else
  echo "No package-lock.json; running npm install"
  npm install --no-audit --no-fund
fi

exec npm run dev -- --host 0.0.0.0 --port "${PREVIEW_PORT}"
