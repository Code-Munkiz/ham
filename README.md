![Ham — first code monkey in space](assets/ham-mascot.png)

# Ham

Open-source multi-agent autonomous developer swarm: Hermes supervisory orchestration and critique, Factory Droid execution, and a local Context Engine (`memory_heist`) with LiteLLM/OpenRouter model routing.

- **Architecture**: see [VISION.md](VISION.md)
- **Agent / IDE context index**: [AGENTS.md](AGENTS.md)
- **Gaps vs vision**: [GAPS.md](GAPS.md)
- **Product direction (non-binding)**: [PRODUCT_DIRECTION.md](PRODUCT_DIRECTION.md)
- **Builder Platform north star (aspirational, phased)**: [docs/BUILDER_PLATFORM_NORTH_STAR.md](docs/BUILDER_PLATFORM_NORTH_STAR.md)
- **Context Engine hardening plan**: [docs/HAM_HARDENING_REMEDIATION.md](docs/HAM_HARDENING_REMEDIATION.md)
- **Chat control plane (skills + roadmap)**: [docs/HAM_CHAT_CONTROL_PLANE.md](docs/HAM_CHAT_CONTROL_PLANE.md)
- **Browser Runtime (Playwright) setup/caveats**: [docs/BROWSER_RUNTIME_PLAYWRIGHT.md](docs/BROWSER_RUNTIME_PLAYWRIGHT.md)
- **Cloud Agent + managed missions** (roadmap, SDK bridge, feed): [docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md](docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md); mission-scoped feed and controls: [docs/MISSION_AWARE_FEED_CONTROLS.md](docs/MISSION_AWARE_FEED_CONTROLS.md)
- **HAM product roadmap** (attachments Phase 2A+, Export-to-PDF Phase 2B, media/RAG): [docs/HAM_ROADMAP.md](docs/HAM_ROADMAP.md)
- **Deploy (Cloud Run)**: [docs/DEPLOY_CLOUD_RUN.md](docs/DEPLOY_CLOUD_RUN.md) | **Handoff**: [docs/DEPLOY_HANDOFF.md](docs/DEPLOY_HANDOFF.md)
- **Control plane runs**: [docs/CONTROL_PLANE_RUN.md](docs/CONTROL_PLANE_RUN.md)
- **Documentation index**: [docs/README.md](docs/README.md)

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env
```

For **`python main.py`** with a real model, set `OPENROUTER_API_KEY` (see `.env.example` for gateway defaults). For a quick local dashboard + API smoke path, `scripts/run_local_api.py` loads `.env`, defaults `HERMES_GATEWAY_MODE=mock` when unset, and aligns with [AGENTS.md](AGENTS.md).

```bash
python main.py "your task"
```

**Local API (FastAPI, dashboard + Workspace UI):** from repo root run `python3 scripts/run_local_api.py` (`PORT`, default `8000`). In another terminal: `npm run dev` in [`frontend/`](frontend/) (Vite proxies `/api/*` to the backend; OpenAPI at `http://127.0.0.1:8000/docs`). See [AGENTS.md](AGENTS.md) and [`.cursor/skills/cloud-agent-starter/SKILL.md`](.cursor/skills/cloud-agent-starter/SKILL.md) for Clerk env overrides and uvicorn alternatives.

**Playwright browser runtime (`/api/browser/*`):** the API must have Chromium when you use in-process Playwright. One-shot (creates **`./.venv`** on PEP 668 distros if needed, e.g. Pop!_OS/Ubuntu):

```bash
./scripts/install_playwright_chromium.sh
```

Activate that venv when you run the API, or use `.venv/bin/python -m uvicorn ...`. Or manually: `python -m playwright install chromium` inside your venv (on Linux, if the browser will not start: `python -m playwright install-deps chromium`). See [`docs/BROWSER_RUNTIME_PLAYWRIGHT.md`](docs/BROWSER_RUNTIME_PLAYWRIGHT.md).

**Dashboard + API on Vercel / Cloud Run:** see [`docs/DEPLOY_HANDOFF.md`](docs/DEPLOY_HANDOFF.md) (env vars, CORS, verify script). GCP commands: [`docs/DEPLOY_CLOUD_RUN.md`](docs/DEPLOY_CLOUD_RUN.md).

## Tests

```bash
pip install pytest
python -m pytest tests/ -q
```

Frontend typecheck: `npm run lint` in `frontend/` (`tsc --noEmit`). See [`AGENTS.md`](AGENTS.md) for per-area test guidance.

Before landing edits to canonical markdown, run `python scripts/check_docs_freshness.py` (same check as the CI **warning-only** doc freshness step; tracked paths are **`CANONICAL_DOCS`** in that script). **Docs-only PR hygiene** (for example overlap checks with `gh pr list` before opening another PR) is spelled out in [AGENTS.md](AGENTS.md).

## Project layout

- `main.py` — CLI entry (bridge / Hermes one-shot orchestration wiring)
- `src/api/server.py` — FastAPI app (runs, chat, Cursor/managed missions routes; see [AGENTS.md](AGENTS.md))
- `src/api/workspace_tools.py` — workspace tool/worker discovery (`GET /api/workspace/tools`) and optional Claude Agent SDK smoke path (see [AGENTS.md](AGENTS.md))
- `src/hermes_feedback.py` — Hermes supervisory/critic MVP surface (reviewer implemented)
- `src/tools/droid_executor.py` — Droid execution backend (bounded `subprocess.run`, timeout, stdout/stderr caps; profile argv + policy gate what actually runs)
- `src/memory_heist.py` — repo context, instructions, git, sessions
- `src/llm_client.py` — LiteLLM / OpenRouter
- `src/swarm_agency.py` — Hermes-supervised role context assembly (no CrewAI; orchestration is Hermes-led)
- `src/ham_cli/` — operator CLI (`python -m src.ham_cli` or `./scripts/ham`)
- `scripts/run_local_api.py` — local API runner with dev-friendly defaults
- [`frontend/`](frontend/) — Vite + React workspace (`npm run dev`; proxies `/api`)
- [`desktop/`](desktop/) — Electron shell (see `desktop/README.md`)
