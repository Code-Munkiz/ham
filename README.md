![Ham — first code monkey in space](assets/ham-mascot.png)

# Ham

Open-source multi-agent autonomous developer swarm: CrewAI orchestration, Factory Droid execution, Hermes review/learning, and a local Context Engine (`memory_heist`).

- **Architecture**: see [VISION.md](VISION.md)
- **Agent / IDE context index**: [AGENTS.md](AGENTS.md)
- **Gaps vs vision**: [GAPS.md](GAPS.md)
- **Context Engine hardening plan**: [docs/HAM_HARDENING_REMEDIATION.md](docs/HAM_HARDENING_REMEDIATION.md)

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env   # add OPENROUTER_API_KEY
python main.py "your task"
```

## Project layout

- `src/swarm_agency.py` — CrewAI crew
- `src/memory_heist.py` — repo context, instructions, git, sessions
- `src/llm_client.py` — LiteLLM / OpenRouter
- `src/hermes_feedback.py` — Hermes critic stub
- `src/tools/droid_executor.py` — Droid tool stub
