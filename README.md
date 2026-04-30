![Ham — first code monkey in space](assets/ham-mascot.png)

# Ham

Open-source multi-agent autonomous developer swarm: Hermes supervisory orchestration and critique, Factory Droid execution, and a local Context Engine (`memory_heist`) with LiteLLM/OpenRouter model routing.

- **Architecture**: see [VISION.md](VISION.md)
- **Agent / IDE context index**: [AGENTS.md](AGENTS.md)
- **Gaps vs vision**: [GAPS.md](GAPS.md) (Cloud Agent + managed missions: [docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md](docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md))
- **Product direction (non-binding)**: [PRODUCT_DIRECTION.md](PRODUCT_DIRECTION.md)
- **Context Engine hardening plan**: [docs/HAM_HARDENING_REMEDIATION.md](docs/HAM_HARDENING_REMEDIATION.md)
- **Chat control plane (skills + roadmap)**: [docs/HAM_CHAT_CONTROL_PLANE.md](docs/HAM_CHAT_CONTROL_PLANE.md)
- **Browser Runtime (Playwright) setup/caveats**: [docs/BROWSER_RUNTIME_PLAYWRIGHT.md](docs/BROWSER_RUNTIME_PLAYWRIGHT.md)
- **Control plane runs (Cursor / Droid launches)**: [docs/CONTROL_PLANE_RUN.md](docs/CONTROL_PLANE_RUN.md)
- **Managed Cloud Agent missions (roadmap + scope)**: [docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md](docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md)
- **Workspace chat → Cursor Cloud Agent routing (smoke note)**: [docs/HAM_CLOUD_AGENT_ROUTING_SMOKE.md](docs/HAM_CLOUD_AGENT_ROUTING_SMOKE.md)
- **Local control (desktop / bridge boundary)**: [docs/desktop/local_control_v1.md](docs/desktop/local_control_v1.md)
- **Cursor / IDE setup (rules, skills, commands)**: [CURSOR_SETUP_HANDOFF.md](CURSOR_SETUP_HANDOFF.md)

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

## Project layout

- `main.py` — CLI entry: env load, bridge + Hermes review one-shot flows
- `src/hermes_feedback.py` — Hermes supervisory/critic MVP surface (reviewer implemented)
- `src/tools/droid_executor.py` — Droid execution backend (bounded `subprocess.run`, timeout, stdout/stderr caps; profile argv + policy gate what actually runs)
- `src/memory_heist.py` — repo context, instructions, git, sessions
- `src/llm_client.py` — LiteLLM / OpenRouter
- `src/swarm_agency.py` — Hermes-supervised role context assembly (no CrewAI; orchestration is Hermes-led)
- `src/api/server.py` — FastAPI app (status, runs, chat, skills, settings, browser runtime, etc.)
- `src/ham_cli/` — operator CLI (`python -m src.ham_cli` or `./scripts/ham`): doctor, status, Windows desktop packaging helpers
- `src/bridge/` — Bridge contracts, policy, runtime (bounded execution against registry profiles)
- `frontend/` — Vite + React workspace UI (`npm run dev`, port 3000)
- `desktop/` — Electron shell for local workspace + local control (see `desktop/README.md`)

## Documentation index

High-signal docs beyond the links at the top of this file:

| Topic | Doc |
|--------|-----|
| Coding conventions for this repo | [SWARM.md](SWARM.md) |
| Hermes gateway (dashboard chat adapter) | [docs/HERMES_GATEWAY_CONTRACT.md](docs/HERMES_GATEWAY_CONTRACT.md) |
| Chat control plane (skills, operator, UI actions) | [docs/HAM_CHAT_CONTROL_PLANE.md](docs/HAM_CHAT_CONTROL_PLANE.md) |
| Factory Droid contract (workflows from chat) | [docs/FACTORY_DROID_CONTRACT.md](docs/FACTORY_DROID_CONTRACT.md) |
| Hermes + HAM operator story (API vs desktop) | [docs/TEAM_HERMES_STATUS.md](docs/TEAM_HERMES_STATUS.md) |
| Cloud Agent / fresh workspace runbook | [.cursor/skills/cloud-agent-starter/SKILL.md](.cursor/skills/cloud-agent-starter/SKILL.md) |
