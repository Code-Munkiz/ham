# Ham chat control plane (operator skills)

## Goal

Use **dashboard chat** as the conversational front-end for **operator intent**: map what the user wants to the right **Cursor skill**, slash command, or doc path—without pretending the LLM can mutate `.ham.json` or run tools by itself.

Hermes remains the **sole supervisory orchestrator** for the Ham *runtime*; this document is about **product control plane** UX (chat + API), not replacing `hermes_feedback.py`.

## Shipped (Phase A)

| Piece | Role |
|-------|------|
| `GET /api/cursor-skills` | JSON index of `.cursor/skills/*/SKILL.md` (id, name, description, path). |
| `include_operator_skills` on `POST /api/chat` | Default **true**: appends a capped skills summary to the **server-side system prompt** so the model can route intents to real workflows. |
| `src/ham/cursor_skills_catalog.py` | Loader + `render_skills_for_system_prompt()`. |
| Docker image | `COPY .cursor/skills` so Cloud Run has the same catalog as local dev. |

Set `HAM_REPO_ROOT` if the API process cwd is not the repo root (optional).

## Combining skills for intents

Skills are **composable checklists** for Cursor/Hermes-aligned work, for example:

| Intent | Primary skill | Often paired with |
|--------|----------------|-------------------|
| Harden context engine | `context-engine-hardening` | `repo-context-regression-testing` |
| Wire agents to `memory_heist` | `agent-context-wiring` | `prompt-budget-audit` |
| Validate critic loop | `hermes-review-loop-validation` | `prompt-budget-audit` |
| Navigate dashboard / explain UI | `goham` | — |

Chat should name the **skill id**, the **`.cursor/skills/.../SKILL.md`** path, and any **slash command** from `.cursor/rules/commands.mdc` when applicable.

## Next (not built yet)

1. **Structured actions** — model returns JSON `{ "action": "open_settings", "tab": "context" }`; UI executes (requires tool schema + UI handlers).
2. **Settings writes** — audited `PATCH` for merged `.ham.json` / project config from the API (auth + validation + backups).
3. **Subagent rule catalog** — optional read-only `GET /api/cursor-subagents` for `.cursor/rules/subagent-*.mdc` (heavier; keep separate from skills).

## Constraints

- Do not merge **recovery-grade dollars** with **observational** metrics here—out of scope.
- Skills catalog is **operator documentation**, not executable code—execution stays in Cursor CLI / Ham runtime paths.
