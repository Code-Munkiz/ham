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

## Structured UI actions (Phase B — shipped)

| Piece | Behavior |
|-------|----------|
| Marker line | Model adds final line: `HAM_UI_ACTIONS_JSON: {"actions":[...]}` (see `src/ham/ui_actions.py`). |
| Server | Strips marker from stored assistant text; validates actions (allowlisted paths, settings tabs, toast length). |
| `POST /api/chat` | Response field **`actions`**: `navigate`, `open_settings`, `toast`, `toggle_control_panel`. |
| `POST /api/chat/stream` | NDJSON: `session` → `delta` (token chunks) → `done` (`messages`, `actions`) or `error`. Gateway uses streaming for **openrouter** / **http** (`stream: true`); **mock** chunks the reply. |
| Client | `postChatStream` in `frontend/src/lib/ham/api.ts`; `Chat.tsx` shows tokens as they arrive; `applyUiActions` runs on `done`. |
| Session persistence | Default in-memory; set **`HAM_CHAT_SESSION_STORE=sqlite`** (+ optional **`HAM_CHAT_SESSION_DB`**) so sessions survive API restarts (`src/persistence/sqlite_chat_session_store.py`). |
| Request flag | `enable_ui_actions` (default **true**); set **false** to omit instructions and always get `actions: []`. |

## Allowlisted settings writes (Phase C — shipped, v1)

| Piece | Behavior |
|-------|----------|
| Write target | Server writes **only** `{project_root}/.ham/settings.json` (deep-merge allowlisted keys; unknown request fields rejected by Pydantic). |
| `discover_config` | `project_settings_replacement=` in `src/memory_heist.py` previews merged config after a hypothetical write without touching disk. |
| `POST .../settings/preview` | Dry-run: `effective_before` / `effective_after`, `diff`, `warnings` (e.g. `settings.local.json` overrides), `base_revision`, `proposal_digest`. No auth required. |
| `POST .../settings/apply` | Requires `Authorization: Bearer` matching **`HAM_SETTINGS_WRITE_TOKEN`**; conflict if `base_revision` stale (**409**). Backup + audit JSON on disk. |
| `POST .../settings/rollback` | Same bearer; restores from `backup_id` under `.ham/_backups/settings/`. |
| `GET /api/settings/write-status` | `{ "writes_enabled": bool }` — whether the token is set (does not reveal the secret). |
| Allowlist | `memory_heist.session_compaction_*`, `session_tool_prune_chars`; `architect_instruction_chars`, `commander_instruction_chars`, `critic_instruction_chars` (see `src/ham/settings_write.py`). |

Chat and the LLM **do not** apply settings; the UI (or CLI) calls **preview** then **apply** after human confirmation.

## Next (not built yet)

1. **Subagent rule catalog** — optional read-only `GET /api/cursor-subagents` for `.cursor/rules/subagent-*.mdc` (heavier; keep separate from skills).
2. **Stronger grounding** — optional second-pass JSON from a small model if marker parsing is too brittle in production.
3. **Settings UX (partial)** — Context & Memory panel: numeric fields → preview → diff/warnings → apply (pasted bearer token per session). Optional: chat-suggested proposal JSON parsed client-side only (never auto-apply).

## Constraints

- Do not merge **recovery-grade dollars** with **observational** metrics here—out of scope.
- Skills catalog is **operator documentation**, not executable code—execution stays in Cursor CLI / Ham runtime paths.
