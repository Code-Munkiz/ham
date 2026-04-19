![Ham — first code monkey in space](assets/ham-mascot.png)

# Ham

Open-source multi-agent autonomous developer swarm: Hermes supervisory orchestration and critique, Factory Droid execution, and a local Context Engine (`memory_heist`) with LiteLLM/OpenRouter model routing.

- **Architecture**: see [VISION.md](VISION.md)
- **Agent / IDE context index**: [AGENTS.md](AGENTS.md)
- **Gaps vs vision**: [GAPS.md](GAPS.md)
- **Product direction (non-binding)**: [PRODUCT_DIRECTION.md](PRODUCT_DIRECTION.md)
- **Context Engine hardening plan**: [docs/HAM_HARDENING_REMEDIATION.md](docs/HAM_HARDENING_REMEDIATION.md)

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env   # add OPENROUTER_API_KEY
python main.py "your task"
```

**Dashboard + API on Vercel / Cloud Run:** see [`docs/DEPLOY_HANDOFF.md`](docs/DEPLOY_HANDOFF.md) (env vars, CORS, verify script). GCP commands: [`docs/DEPLOY_CLOUD_RUN.md`](docs/DEPLOY_CLOUD_RUN.md).

## Project layout

- `src/hermes_feedback.py` — Hermes supervisory/critic MVP surface (reviewer implemented)
- `src/tools/droid_executor.py` — Droid execution engine stub (runtime migration still pending)
- `src/memory_heist.py` — repo context, instructions, git, sessions
- `src/llm_client.py` — LiteLLM / OpenRouter
- `src/swarm_agency.py` — Hermes-supervised role context assembly (no CrewAI; orchestration is Hermes-led)
