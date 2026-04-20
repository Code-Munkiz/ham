# Ham chat control plane (operator skills)

## Goal

Use **dashboard chat** as the conversational front-end for **operator intent**: map what the user wants to the right **Cursor skill**, slash command, or doc path—without pretending the LLM can mutate `.ham.json` or run tools by itself.

Hermes remains the **sole supervisory orchestrator** for the Ham *runtime*; this document is about **product control plane** UX (chat + API), not replacing `hermes_feedback.py`.

## Shipped (Phase A)

| Piece | Role |
|-------|------|
| `GET /api/cursor-skills` | JSON index of `.cursor/skills/*/SKILL.md` (id, name, description, path). |
| `GET /api/cursor-subagents` | JSON index of `.cursor/rules/subagent-*.mdc` (id, title, description, globs, always_apply, path)—**review charters**, not runnable skills. |
| `include_operator_skills` / `include_operator_subagents` on `POST /api/chat` (and stream) | Default **true**: append capped **skills** + **subagent** indexes to the **server-side system prompt** (workflows vs review charters). Set either flag **false** to save tokens. |
| `src/ham/cursor_skills_catalog.py` | Loader + `render_skills_for_system_prompt()`. |
| Docker image | `COPY .cursor/skills` and `COPY .cursor/rules` so Cloud Run has skills + subagent stubs. |

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

## Hermes runtime skills (Phase 1 catalog + Phase 2a shared install)

**Distinct from** the Cursor operator catalog (`GET /api/cursor-skills`, `.cursor/skills`): Hermes skills are **runtime** agent skills (may include scripts) and follow Hermes semantics (`~/.hermes/skills`, `skills.external_dirs`, profiles).

| Piece | Role |
|-------|------|
| `GET /api/hermes-skills/catalog` | Vendored catalog from pinned **hermes-agent** (`skills/` + `optional-skills/`). Regenerate: `python scripts/build_hermes_skills_catalog.py` (bumps commit via `--commit-sha` when you change the pin). |
| `GET /api/hermes-skills/catalog/{catalog_id}` | Detail + manifest/warnings/provenance. |
| `GET /api/hermes-skills/capabilities` | Host probe: `local` / `remote_only` / `unsupported`; **`shared_runtime_install_supported`** when local Hermes home + **`HAM_HERMES_SKILLS_SOURCE_ROOT`** + `.ham-hermes-agent-commit` match catalog pin; **`skills_apply_writes_enabled`** when **`HAM_SKILLS_WRITE_TOKEN`** is set. Set **`HAM_HERMES_SKILLS_MODE=remote_only`** when the API is not co-located with operator Hermes home. |
| `GET /api/hermes-skills/targets` | Read-only **shared** + **Hermes profile** targets (filesystem discovery only; not Ham `IntentProfile`, not Cursor subagents). **Phase 2a install** accepts **`{"kind":"shared"}`** only. |
| `GET /api/hermes-skills/install/write-status` | Whether apply is enabled (token set on server). |
| `POST /api/hermes-skills/install/preview` | Dry-run: `proposal_digest`, `base_revision`, `config_diff`, bundle path; no mutations. Rejects **`REMOTE_UNSUPPORTED`** when not co-located. |
| `POST /api/hermes-skills/install/apply` | Bearer **`HAM_SKILLS_WRITE_TOKEN`**: materialize bundle under **`~/.hermes/ham-runtime-bundles/`**, merge **`skills.external_dirs`**, atomic YAML write, backup + audit under **`~/.hermes/_ham_*`**. |
| `frontend/src/pages/HermesSkills.tsx` | **Skills** page (`/skills`); Phase 2a **Preview / Apply** in detail panel when **`shared_runtime_install_supported`**. |

**Phase 2a scope:** shared target only; no profile-target install, no uninstall, no rollback API, no Hermes CLI subprocess install, no arbitrary URL/GitHub installs from the client.

## Next (not built yet)

1. **Stronger grounding** — optional second-pass JSON from a small model if marker parsing is too brittle in production.
2. **Settings UX (partial)** — Context & Memory panel ships preview/apply; optional: chat-suggested proposal JSON parsed client-side only (never auto-apply); optional **rollback** button.
3. **Hermes skills Phase 2b+** — Hermes profile-target install, uninstall/rollback endpoints if needed, optional remote/sidecar topologies without pretending local writes.

## Constraints

- Do not merge **recovery-grade dollars** with **observational** metrics here—out of scope.
- Skills catalog is **operator documentation**, not executable code—execution stays in Cursor CLI / Ham runtime paths.
