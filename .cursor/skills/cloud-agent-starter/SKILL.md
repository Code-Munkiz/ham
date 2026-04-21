---
name: cloud-agent-starter
description: >-
  Minimal starter runbook for Cloud agents to install, run, and test Ham quickly.
  Covers backend/frontend startup, chat gateway modes, Cursor key setup, browser
  runtime checks, and how to keep this skill current as new runbook knowledge is found.
---

# Cloud Agent Starter — run + test Ham fast

## When to use

- First run in a fresh Cloud workspace
- Any task that needs local app startup and quick health checks
- Any task that touches chat/gateway modes, browser runtime, or Cursor API wiring

## 1) Fast setup (do this first)

From repo root:

1. Install backend deps:
   - `python3 -m pip install -r requirements.txt`
2. Install pytest (not in `requirements.txt`):
   - `python3 -m pip install pytest`
3. Install frontend deps:
   - `npm install --prefix frontend`
4. Create local env file:
   - `cp .env.example .env`

## 2) Authentication + mode defaults (practical)

### Chat mode (feature flag you usually set first)

- `HERMES_GATEWAY_MODE=mock` (default safe local mode; no external key needed)
- Real model calls:
  - Set `HERMES_GATEWAY_MODE=openrouter`
  - Set `OPENROUTER_API_KEY=...`
- External OpenAI-compatible gateway:
  - Set `HERMES_GATEWAY_MODE=http`
  - Set `HERMES_GATEWAY_BASE_URL=...`
  - Optional: `HERMES_GATEWAY_API_KEY=...`

### Cursor Cloud API key ("login")

- Option A (env): set `CURSOR_API_KEY` in `.env`.
- Option B (API, persists server-side):
  - `POST /api/cursor/credentials` with `{ "api_key": "..." }`
- Verify key identity:
  - `GET /api/cursor/credentials-status`

### Write-protected routes (set only when needed)

- `HAM_SETTINGS_WRITE_TOKEN` for project settings apply/rollback
- `HAM_RUN_LAUNCH_TOKEN` for operator launch_run turns
- `HAM_SKILLS_WRITE_TOKEN` for Hermes skills install apply

## 3) Start the app (backend + frontend)

Use two terminals/tmux panes:

- Backend (repo root):
  - `python3 -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000`
- Frontend (`frontend/`):
  - `npm run dev`

Quick smoke checks:

- `curl -sS http://127.0.0.1:8000/api/status`
- `curl -sS -I http://127.0.0.1:3000`
- Open `http://127.0.0.1:8000/docs`

## 4) Testing workflows by codebase area

## A) Context Engine (`src/memory_heist.py`)

- Run focused suite:
  - `python3 -m pytest tests/test_memory_heist.py -q`
- Use when touching repo scan, config discovery, git diff capture, or session compaction.

## B) Hermes reviewer/supervision (`src/hermes_feedback.py`)

- Run focused suite:
  - `python3 -m pytest tests/test_hermes_feedback.py -q`
- Use when touching review loop, critique prompts, or learning-signal shaping.

## C) Droid registry/execution metadata (`src/registry`, `src/tools`)

- Run focused suite:
  - `python3 -m pytest tests/test_droid_registry.py -q`
- Use when changing droid records, defaults, or registry behavior.

## D) API surface (`src/api/*`)

Run backend, then smoke test key routes:

- `curl -sS http://127.0.0.1:8000/api/status`
- `curl -sS -X POST http://127.0.0.1:8000/api/chat -H 'content-type: application/json' -d '{"messages":[{"role":"user","content":"hello"}]}'`
- `curl -sS http://127.0.0.1:8000/api/context-engine`

Mode-specific check:

- In mock mode, `/api/chat` should return a "Mock assistant reply..." response.

## E) Frontend (`frontend/`)

- Type/lint gate:
  - `npm run lint --prefix frontend`
- Manual check:
  - Open `http://127.0.0.1:3000`
  - Confirm dashboard loads and can call backend (`/api/status`, chat UI flows)

## F) Browser runtime (`src/api/browser_runtime.py`)

Prereq for full runtime behavior:

- `python3 -m playwright install chromium`

Minimal checks:

- `curl -sS http://127.0.0.1:8000/api/browser/policy`
- Create a session:
  - `curl -sS -X POST http://127.0.0.1:8000/api/browser/sessions -H 'content-type: application/json' -d '{"owner_key":"local-dev"}'`

Useful env flags:

- `HAM_BROWSER_ALLOW_PRIVATE_NETWORK=true|false`
- `HAM_BROWSER_ALLOWED_DOMAINS=...`
- `HAM_BROWSER_BLOCKED_DOMAINS=...`
- `HAM_BROWSER_SESSION_TTL_SECONDS=...`

## 5) Common quick fixes

- `python3 -m pytest ...` fails with `No module named pytest`:
  - Run `python3 -m pip install pytest`
- `uvicorn` not found in PATH:
  - Use `python3 -m uvicorn ...` instead of bare `uvicorn`.
- Chat endpoint errors in non-mock mode:
  - Re-check `HERMES_GATEWAY_MODE` and matching credentials in `.env`.

## 6) Keep this skill updated

When you discover a new reliable runbook trick:

1. Add it under the correct codebase area above (do not add a generic dump section).
2. Include one concrete command and one expected result.
3. Prefer focused tests (`tests/test_*.py`) over full-suite runs.
4. Remove stale steps immediately when routes/env names change.
5. Keep this file minimal; move deep architecture details to `AGENTS.md`/`VISION.md`.
