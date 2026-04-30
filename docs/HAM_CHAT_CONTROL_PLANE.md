# Ham chat control plane (operator skills)

## Goal

Use **dashboard chat** as the conversational front-end for **operator intent**: map what the user wants to the right **Cursor skill**, slash command, or doc path—without pretending the LLM can mutate `.ham.json` or run tools by itself.

Hermes remains the **sole supervisory orchestrator** for the Ham *runtime*; this document is about **product control plane** UX (chat + API), not replacing `hermes_feedback.py`.

**ControlPlaneRun (v1):** [`docs/CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md) describes the **ControlPlaneRun** durable record for **provider** launches (Cursor / Droid) and Cursor status polling—implemented under `src/persistence/control_plane_run.py` (separate from bridge `.ham/runs`, audit JSONL, and memory; not a full orchestration graph).

**Harness contract (Cursor + Droid):** [`docs/HARNESS_PROVIDER_CONTRACT.md`](HARNESS_PROVIDER_CONTRACT.md) defines provider **capabilities**, **preservation** rules, and how they relate to `ControlPlaneRun` (Hermes is not the harness anchor there).

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

The **`goham`** skill is **dashboard navigation** (where to click in the workspace UI)—**not** Electron managed-browser / GoHAM chat execution.

Chat should name the **skill id**, the **`.cursor/skills/.../SKILL.md`** path, and any **slash command** from `.cursor/rules/commands.mdc` when applicable.

## Structured UI actions (Phase B — shipped)

| Piece | Behavior |
|-------|----------|
| Marker line | Model adds final line: `HAM_UI_ACTIONS_JSON: {"actions":[...]}` (see `src/ham/ui_actions.py`). |
| Server | Strips marker from stored assistant text; validates actions (allowlisted paths, settings tabs, toast length). |
| `POST /api/chat` | Response field **`actions`**: `navigate`, `open_settings`, `toast`, `toggle_control_panel` (legacy `set_workbench_view` removed; product chat is Hermes Workspace). |
| `POST /api/chat/stream` | NDJSON: `session` → `delta` (token chunks) → `done` (`messages`, `actions`) or `error`. Gateway uses streaming for **openrouter** / **http** (`stream: true`); **mock** chunks the reply. |
| Client | `postChatStream` in `frontend/src/lib/ham/api.ts`; Hermes Workspace chat (`WorkspaceChatScreen`) shows tokens as they arrive; `applyHamUiActions` runs on `done`. |
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
| `GET /api/hermes-hub` | Read-only snapshot: **`gateway_mode`** / dashboard chat summary + same Hermes **skills capabilities** probe as `/api/hermes-skills/capabilities` (no fake inventory). |
| `frontend/src/pages/HermesHub.tsx` | **Hermes** hub (`/hermes`): honest control-plane cards + link to **`/skills`**; not a Hermes CLI or runtime explorer. |

**Phase 2a scope:** shared target only; no profile-target install, no uninstall, no rollback API, no Hermes CLI subprocess install, no arbitrary URL/GitHub installs from the client.

### `GET /api/models` readiness fields (re-exported on `GET /api/hermes-hub`)

The model catalog includes three booleans so clients do not have to infer gateway health from individual row `supports_chat` flags:

- **`openrouter_chat_ready`** — `true` only when **`gateway_mode`** is **`openrouter`** and **`OPENROUTER_API_KEY`** is set and passes the server’s plausibility check (upstream billing/health is still a separate smoke test).
- **`http_chat_ready`** — `true` only when **`gateway_mode`** is **`http`** (including the case where **`HERMES_GATEWAY_MODE`** is unset but **`HERMES_GATEWAY_BASE_URL`** is set, which implies HTTP mode) **and** that base URL is non-empty.
- **`dashboard_chat_ready`** — umbrella signal: **`true`** if dashboard chat should be considered available on a supported path — **`openrouter_chat_ready`**, **`http_chat_ready`**, or **mock** mode (built-in mock assistant).

OpenRouter-labeled composer rows may stay **`supports_chat: false`** in **HTTP** mode with a message aimed at those tiers, not at the whole app. **`openrouter_chat_ready: false`** in that situation does **not** by itself mean chat is unavailable; use **`http_chat_ready`** / **`dashboard_chat_ready`** for the active path.

## Operational chat (Phase 1 — shipped)

Server-side **`src/ham/chat_operator.py`** runs **before** the LLM when `HAM_CHAT_OPERATOR` is true (default) and the last message is from the user.

| Intent (heuristic or `operator` payload) | Behavior |
|------------------------------------------|----------|
| `list_projects` / `inspect_project` / `inspect_agents` | Registry + merged config; **blocked** if API host cannot `stat` `project.root`. |
| `list_runs` / `inspect_run` | `RunStore` under project root or API cwd. |
| `update_agents_preview` | Hermes catalog skill add/remove → `settings/preview` → response includes **`pending_apply`** for UI + token. |
| `apply_settings` | Client **`operator.phase=apply_settings`**, `confirmed=true`, echoes preview `changes` + `base_revision`; **`Authorization: Bearer HAM_SETTINGS_WRITE_TOKEN`**. |
| `register_project` | Path must exist on API host; confirm + same settings token as apply. |
| `launch_run` | One-shot `run_bridge_v0` + reviewer + **`persist_ham_run_record`** at project root; requires **`HAM_RUN_LAUNCH_TOKEN`** and **`OPENROUTER_API_KEY`** on host. |
| `droid_preview` / NL `preview factory droid …` | Allowlisted Factory **`droid exec`** workflows (`readonly_repo_audit`, `safe_edit_low`): structured preview + `proposal_digest` + registry revision; blocked on bad root or missing Custom Droid file. See **`docs/FACTORY_DROID_CONTRACT.md`**. |
| `droid_launch` | After preview: `confirmed=true`, matching digest + `droid_base_revision`. **`safe_edit_low`** requires **`Authorization: Bearer`** = **`HAM_DROID_EXEC_TOKEN`**. Audit line in **`<root>/.ham/_audit/droid_exec.jsonl`**. |
| `cursor_agent_preview` | **Cursor Cloud Agents** (official `api.cursor.com`): structured preview + `cursor_proposal_digest` + `cursor_base_revision` (`cursor-agent-v2`). Resolves **repository URL only** from operator `cursor_repository`, then `project.metadata.cursor_cloud_repository`, then optional **`HAM_CURSOR_DEFAULT_REPOSITORY`**. Does **not** require local `project.root` to exist. **No** Cursor launch during preview. Requires server-side **Cursor API key** (`CURSOR_API_KEY` or saved credentials). |
| `cursor_agent_launch` | After preview: `confirmed=true`, matching digest + `cursor_base_revision`, **`Authorization: Bearer`** = **`HAM_CURSOR_AGENT_LAUNCH_TOKEN`**. Calls Cursor **`POST /v0/agents`** via [`src/integrations/cursor_cloud_client.py`](src/integrations/cursor_cloud_client.py) (Bearer auth). **Primary audit:** central JSONL (**`HAM_CURSOR_AGENT_AUDIT_FILE`** or default `~/.ham/_audit/cursor_cloud_agent.jsonl`). **Mirror** append to `<root>/.ham/_audit/cursor_cloud_agent.jsonl` only if `project.root` is a writable directory. |
| `cursor_agent_status` | **`cursor_agent_id`** + `project_id`; **`GET /v0/agents/{id}`** with server-side Cursor key only (no Ham launch token). Same central + optional mirror audit. NL: `cursor agent status` + `bc_…` + project mention. |

`POST /api/chat` and **`POST /api/chat/stream`** accept optional **`operator`** (see `ChatOperatorPayload` in `src/api/chat.py`) and return **`operator_result`** JSON. The dashboard chat UI may surface **Apply / Confirm launch / Confirm register** when `pending_*` is present (Hermes Workspace or future surfaces). **`pending_droid`** carries Factory droid preview fields for a client confirm step (UI wiring optional in Phase 1). **`pending_cursor_agent`** carries Cursor Cloud Agent preview fields for confirm + launch.

## Clerk (identity + authz slice)

### Where app-wide access really lives (Clerk Dashboard)

1. **Restricted mode** and **Allowlist** (exact emails and/or whole email domains) in the [Clerk Dashboard](https://dashboard.clerk.com) are the **intended primary** control plane for who can sign up or sign in to your Clerk application. Configure those first.
2. **Organizations → Verified Domains** is for **org membership / enrollment** flows (e.g. auto-join by domain inside an organization). It is **not** the same as a global “only these domains may use the app” gate—do not confuse it with Dashboard allowlist/restricted mode.
3. **HAM server-side** checks below are **defense in depth**: they catch misconfiguration or drift and enforce policy on the API even if Dashboard settings are incomplete.

### HAM API behavior

| Piece | Role |
|-------|------|
| **Who / allowed** | **`HAM_CLERK_REQUIRE_AUTH`** or **`HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS`** + **`CLERK_JWT_ISSUER`**: when Clerk session auth is active, protected dashboard and control-plane routes (including **`POST /api/chat`**, **`POST /api/chat/stream`**, **`GET /api/models`**, runs/projects/context-engine/cursor-settings proxies, Hermes skills install, project settings, and **`GET /api/clerk-access-probe`**) require **`Authorization: Bearer`** Clerk session JWT; server verifies via JWKS (`src/ham/clerk_auth.py`). **`GET /api/status`** and **`GET /`** stay public. Include **`email`** in the Clerk session JWT template so HAM can evaluate allowlists. Chat operator permissions come from JWT **`permissions`** (or **`org_role`** fallback: `org:member` → `ham:preview` + `ham:status`; `org:admin` → includes `ham:launch`). Custom claims: `ham:preview`, `ham:status`, `ham:launch`, `ham:admin`. |
| **Email / domain gate** | Optional **`HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS`** with **`HAM_CLERK_ALLOWED_EMAILS`** and/or **`HAM_CLERK_ALLOWED_EMAIL_DOMAINS`** (comma-separated, case-insensitive). If enforcement is on and **both** lists are empty after parsing, HAM **denies everyone** (fail closed). The same gate applies to **all** Clerk-protected API routes above (defense in depth alongside [Clerk Dashboard](https://dashboard.clerk.com) allowlists). Denials return **`403`** with **`HAM_EMAIL_RESTRICTION`** and append a row to **`HAM_OPERATOR_AUDIT_FILE`** (`event: ham_access_denied`, `denial_reason`, `route`, evaluated email) — **not** Clerk metadata (`src/ham/clerk_email_access.py`). |
| **HAM operator secrets** | When **`Authorization`** is the Clerk session, **`HAM_*_TOKEN`** values are **`X-Ham-Operator-Authorization: Bearer …`**. Legacy: single header **`Authorization`** = HAM token when neither Clerk flag is on. |
| **Phases** | Preview-style operator phases require **`ham:preview`**; read/status intents **`ham:status`**; mutating launch/apply/register **`ham:launch`**. Enforcement is in **`process_operator_turn`** (`src/ham/chat_operator.py` + `src/ham/clerk_policy.py`) — not client-only. |
| **Audit** | Handled operator turns append **`HAM_OPERATOR_AUDIT_FILE`** with Clerk user/org id and permission evaluation. Email denials append the same sink with **`event: ham_access_denied`**. |
| **Cursor API** | Unchanged: **`CURSOR_API_KEY`** / saved credentials for **`api.cursor.com`**; Clerk does **not** replace the Cursor team key. |
| **M2M (future)** | `clerk_m2m_note()` documents the seam; keep **`HAM_DROID_RUNNER_SERVICE_TOKEN`** / launch tokens for service paths until M2M is wired. |

Frontend: set **`VITE_CLERK_PUBLISHABLE_KEY`** to wrap the app with **`ClerkProvider`**; **`ClerkAccessBridge`** registers **`getToken()`** for shared **`api.ts`** fetches and shows a shell banner when the probe returns **`HAM_EMAIL_RESTRICTION`**. Workspace chat passes the session JWT on stream requests (`frontend/src/features/hermes-workspace/screens/chat/WorkspaceChatScreen.tsx`). **`HamAccessRestrictedError`** maps **`HAM_EMAIL_RESTRICTION`** to a clear toast + transcript error on chat failures.

**Instructional skill (not policy):** `.cursor/skills/factory-droid-workflows/SKILL.md`.

## Next (not built yet)

1. **Stronger grounding** — optional second-pass JSON from a small model if marker parsing is too brittle in production.
2. **Settings UX (partial)** — Context & Memory panel ships preview/apply; chat can now drive preview/apply for Agent Builder; optional **rollback** button in chat.
3. **Hermes skills Phase 2b+** — Hermes profile-target install, uninstall/rollback endpoints if needed, optional remote/sidecar topologies without pretending local writes.

## Constraints

- Do not merge **recovery-grade dollars** with **observational** metrics here—out of scope.
- Skills catalog is **operator documentation**, not executable code—execution stays in Cursor CLI / Ham runtime paths.
