# Swarm Global Instructions

- Always write clean Python.
- Prefer small, composable modules over monolithic scripts.
- Document public APIs briefly; keep implementation comments minimal unless non-obvious.
- Fail fast with clear error messages; avoid silent catches in orchestration code.
- Supervisory orchestration is **Hermes-led only**; do not introduce CrewAI (or other orchestration frameworks)—see `VISION.md` and `.cursor/rules/ham-architecture.mdc`.
