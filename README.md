![Ham — first code monkey in space](assets/ham-mascot.png)

# Ham

Open-source multi-agent autonomous developer swarm: Hermes supervisory orchestration and critique, Factory Droid execution, and a local Context Engine (`memory_heist`) with LiteLLM/OpenRouter model routing.

- **Architecture**: see [VISION.md](VISION.md)
- **Agent / IDE context index**: [AGENTS.md](AGENTS.md)
- **Gaps vs vision**: [GAPS.md](GAPS.md)
- **Product direction (non-binding)**: [PRODUCT_DIRECTION.md](PRODUCT_DIRECTION.md)
- **Context Engine hardening plan**: [docs/HAM_HARDENING_REMEDIATION.md](docs/HAM_HARDENING_REMEDIATION.md)
- **Chat control plane (skills + roadmap)**: [docs/HAM_CHAT_CONTROL_PLANE.md](docs/HAM_CHAT_CONTROL_PLANE.md)
- **Browser Runtime (Playwright) setup/caveats**: [docs/BROWSER_RUNTIME_PLAYWRIGHT.md](docs/BROWSER_RUNTIME_PLAYWRIGHT.md)
- **Cloud Agent managed missions**: [docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md](docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md) (SDK bridge, feed projection, deployment) — feed scoped per mission: [docs/MISSION_AWARE_FEED_CONTROLS.md](docs/MISSION_AWARE_FEED_CONTROLS.md)
- **Deploy (Cloud Run)**: [docs/DEPLOY_CLOUD_RUN.md](docs/DEPLOY_CLOUD_RUN.md) | **Handoff**: [docs/DEPLOY_HANDOFF.md](docs/DEPLOY_HANDOFF.md)
- **Control plane runs**: [docs/CONTROL_PLANE_RUN.md](docs/CONTROL_PLANE_RUN.md)

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env   # add OPENROUTER_API_KEY
python main.py "your task"
```

**Playwright browser runtime (`/api/browser/*`):** the API must have Chromium when you use in-process Playwright. One-shot (creates **`./.venv`** on PEP 668 distros if needed, e.g. Pop!_OS/Ubuntu):

```bash
./scripts/install_playwright_chromium.sh
```

Activate that venv when you run the API, or use `.venv/bin/python -m uvicorn ...`. Or manually: `python -m playwright install chromium` inside your venv (on Linux, if the browser will not start: `python -m playwright install-deps chromium`). See [`docs/BROWSER_RUNTIME_PLAYWRIGHT.md`](docs/BROWSER_RUNTIME_PLAYWRIGHT.md).

**Dashboard + API on Vercel / Cloud Run:** see [`docs/DEPLOY_HANDOFF.md`](docs/DEPLOY_HANDOFF.md) (env vars, CORS, verify script). GCP commands: [`docs/DEPLOY_CLOUD_RUN.md`](docs/DEPLOY_CLOUD_RUN.md).

**Local dashboard + API (Vite + FastAPI):** from repo root run `python3 scripts/run_local_api.py` (loads `.env`, defaults `HERMES_GATEWAY_MODE=mock`, and uses loose Clerk for read-only routes unless you override). In another terminal: `npm run dev` in `frontend/` (proxies `/api/*` to port 8000). OpenAPI: `http://127.0.0.1:8000/docs`. More detail: [`AGENTS.md`](AGENTS.md) and [`.cursor/skills/cloud-agent-starter/SKILL.md`](.cursor/skills/cloud-agent-starter/SKILL.md).

## Tests

```bash
pip install pytest
python -m pytest tests/ -q
```

Frontend typecheck: `npm run lint` in `frontend/` (`tsc --noEmit`). See [`AGENTS.md`](AGENTS.md) for per-area test guidance.

## Project layout

- `src/hermes_feedback.py` — Hermes supervisory/critic MVP surface (reviewer implemented)
- `src/tools/droid_executor.py` — Droid execution backend (bounded `subprocess.run`, timeout, stdout/stderr caps; profile argv + policy gate what actually runs)
- `src/memory_heist.py` — repo context, instructions, git, sessions
- `src/llm_client.py` — LiteLLM / OpenRouter
- `src/swarm_agency.py` — Hermes-supervised role context assembly (no CrewAI; orchestration is Hermes-led)
