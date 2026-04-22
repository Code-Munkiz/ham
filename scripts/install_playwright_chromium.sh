#!/usr/bin/env bash
# One-shot: Python deps + Playwright Chromium (required for /api/browser/* in-app browser).
# On PEP 668 systems (Ubuntu/Pop!_OS, etc.) pip cannot target system Python — this script
# uses an active venv, or ./.venv, or creates ./.venv if missing.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

resolve_python() {
  if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "${VIRTUAL_ENV}/bin/python" ]; then
    echo "${VIRTUAL_ENV}/bin/python"
    return 0
  fi
  if [ -x "${ROOT}/.venv/bin/python" ]; then
    echo "${ROOT}/.venv/bin/python"
    return 0
  fi
  if [ -x "${ROOT}/venv/bin/python" ]; then
    echo "${ROOT}/venv/bin/python"
    return 0
  fi
  return 1
}

if ! PY="$(resolve_python)"; then
  echo "No virtualenv found. Creating ${ROOT}/.venv (PEP 668: system pip install is blocked)..."
  python3 -m venv "${ROOT}/.venv"
  PY="${ROOT}/.venv/bin/python"
fi

echo "Using: ${PY}"
"${PY}" -m pip install -U pip
"${PY}" -m pip install -r requirements.txt
"${PY}" -m playwright install chromium
echo ""
echo "OK: Playwright Chromium installed."
echo "On Linux, if the browser still fails to start, run:"
echo "  ${PY} -m playwright install-deps chromium"
echo ""
echo "Start the API with the same Python, e.g.:"
echo "  source ${ROOT}/.venv/bin/activate   # if you use this venv"
echo "  ${PY} -m uvicorn src.api.server:app --reload --port 8000"
