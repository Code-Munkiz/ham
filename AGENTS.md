# Ham — Agent Context Index

This file declares which files are first-class project context. Any agent
working on this repo should read these before proposing changes.

## Read order (recommended)

1. `VISION.md` — pillars, boundaries, and how components connect
2. This file — where implementation lives (see § *Git workflow* for direct-main testing; Cursor: `ham-direct-main-workflow.mdc`)
3. `SWARM.md` — repo coding instructions (loaded by `memory_heist`)
4. `PRODUCT_DIRECTION.md` — product lens: HAM-native model vs reference ecosystems
5. `docs/TEAM_HERMES_STATUS.md` (when changing Command Center, Activity, Capabilities, or desktop Hermes copy) — **API-side** vs **desktop-side** operator story, boundaries, troubleshooting

## Ham bet: memory, Hermes, and CLI-native muscle

Three ideas stay stable while execution backends evolve:

1. **Repo-grounded context (`memory_heist`)** — Workspace truth (scan, git, merged `.ham` config, instruction files, session compaction) is assembled once and injected into agents so supervision and planning do not hallucinate project state.

2. **Hermes learning loop (`hermes_feedback`)** — Critique and structured review over **evidence-shaped outcomes** (bridge/run envelopes, capped text). The goal is a compounding signal: routing and quality improve over time; durable institutional memory is still incremental (see `GAPS.md` and hardening docs).

3. **CLI-first execution surface** — Heavy work is delegated to **CLI-based agentic runtimes** (subprocess + framed IO), not re-embedded vendor HTTP stacks inside Ham. **Auth and account state stay with the tool** (its login flows, tokens on disk, device/browser steps). Ham supplies **scoped intent, policy limits, and capture**; Hermes reasons over **comparable envelopes** regardless of whether the muscle is Factory/Droid-style, Claude Code–style, ElizaOS-flavored hosts, OpenClaw-informed gateways, or future adapters—**one supervision vocabulary, many CLIs**.

**Narrow exception (interactive dashboard chat):** The Ham API may expose **`POST /api/chat`** with **HAM-native** JSON to the browser and implement it via a **server-side adapter** to an external OpenAI-compatible agent API (see `docs/HERMES_GATEWAY_CONTRACT.md`, `src/integrations/nous_gateway_client.py`). The browser **never** calls that gateway directly. This does **not** replace **`HermesReviewer`** / `main.py` critique-on-run flow—they stay separate.

Shipped muscle today centers on **Bridge + Droid executor** (`src/tools/droid_executor.py`, `src/bridge/`). Reference notes (patterns only, not parity targets): `docs/reference/factory-droid-reference.md`, `docs/reference/openclaw-reference.md`, `docs/reference/elizaos-reference.md`. Ham remains **HAM-native** in naming and contracts; see `PRODUCT_DIRECTION.md`.

## Architecture

- `.cursor/rules/ham-local-control-boundary.mdc` — local control boundary (web UI + Windows bridge, mandatory desktop/IDE lane, escalation patterns, ancillary cloud **`/api/browser`**, verify-first/minimal-diff; Linux **installers removed** — see rule file)
- `VISION.md` — canonical architecture, core pillars, design principles
- **`src/ham_cli/`** — HAM operator CLI v1 (`python -m src.ham_cli` or `./scripts/ham`): `doctor`, `status`, `api status`, **`desktop package win`** — diagnostics + **Windows** desktop packaging helpers; not chat/missions (see `main.py` for bridge/Hermes one-shot CLI)
- `docs/CONTROL_PLANE_RUN.md` — `ControlPlaneRun` substrate (v1 file-backed: `src/persistence/control_plane_run.py`): durable provider-neutral launch record (Cursor/Droid) + Cursor status updates, separate from bridge runs and audit JSONL; read API: `src/api/control_plane_runs.py` (`GET /api/control-plane-runs`, `GET /api/control-plane-runs/{ham_run_id}`) — not orchestration, queues, or mission graphs
- `docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md` — what’s shipped vs partial vs out of scope for Cursor Cloud Agent + `ManagedMission`, and phased gap closure (correlation, optional Hermes-on-mission, honest E2E scope)
- `docs/MISSION_AWARE_FEED_CONTROLS.md` — mission-scoped live feed + operator controls (`mission_registry_id`); client transcript rendering over bounded feed `events`

## Pillar modules

- `src/hermes_feedback.py` — Hermes supervisory core + critic/learner surface (`HermesReviewer` MVP complete; supervisory wiring still transitional)
- `src/tools/droid_executor.py` — Droid execution engine (implementation-heavy execution; local self-orchestration while executing)
- `src/memory_heist.py` — Context Engine (repo scan, git state, config, sessions)
- `src/llm_client.py` — LiteLLM / OpenRouter wiring
- `src/swarm_agency.py` — Hermes-supervised **context assembly** (shared `ProjectContext` + per-role render budgets for Architect / routing / critic prompts); **not** a separate orchestration framework (no CrewAI)
- `src/registry/droids.py` — `DroidRecord` + `DroidRegistry` + `DEFAULT_DROID_REGISTRY` (builder, reviewer)
- `src/persistence/run_store.py` — read-side `RunStore` over `.ham/runs/*.json`
- `src/api/server.py` — FastAPI app: read API (`/api/status`, `/api/runs`, **`GET /api/context-engine`**, **`GET /api/projects/{id}/context-engine`**, …) plus **`POST /api/chat`**, **`POST /api/chat/stream`** (see `src/api/chat.py` — optional `project_id` + **HAM active agent guidance** from Agent Builder; distinct from Cursor operator skills and Hermes CLI profiles), **`GET /api/cursor-skills`** (Cursor operator skills), **`GET /api/hermes-skills/*`** (Hermes **runtime** skills catalog + host probe + **Phase 2a** shared install preview/apply; see `src/api/hermes_skills.py`, `src/ham/hermes_skills_install.py`), **`GET /api/capability-library/*`** and **`POST .../save|remove|reorder`** (per-project **My library** of saved `hermes:` / `capdir:` catalog refs; `HAM_CAPABILITY_LIBRARY_WRITE_TOKEN`; see `src/api/capability_library.py`, `src/ham/capability_library/`), **`GET /api/cursor-subagents`**, **`GET /api/projects/{id}/agents`** (HAM agent builder profiles; on `app` in `src/api/server.py`), and **project settings** preview/apply (`src/api/project_settings.py`, `HAM_SETTINGS_WRITE_TOKEN` for mutating routes)
- `src/api/workspace_tools.py`, `src/ham/worker_adapters/claude_agent_adapter.py` — Workspace **Connected Tools** (`GET /api/workspace/tools`, `POST /api/workspace/tools/scan`): optional **Claude Agent SDK** readiness when `claude-agent-sdk` is installed (see `requirements.txt`); presence-only auth hints (`ANTHROPIC_API_KEY`, or `CLAUDE_CODE_USE_BEDROCK=1` plus `AWS_REGION` / `AWS_DEFAULT_REGION`, or `CLAUDE_CODE_USE_VERTEX=1` plus a project id env — values never returned). Optional gated one-shot smoke: `POST /api/workspace/tools/claude_agent_sdk/smoke` requires `HAM_CLAUDE_AGENT_SMOKE_ENABLED=1` and either a Clerk-authenticated session or `HAM_CLAUDE_AGENT_SMOKE_TOKEN` (Bearer or `X-Ham-Smoke-Token`) — **not** dashboard chat routing or a second orchestrator; Cloud Run image includes the SDK for readiness and this smoke path only
- `src/ham/cursor_skills_catalog.py` — loads `.cursor/skills` for chat control plane + API index (operator docs; **not** Hermes runtime skills)
- `src/ham/hermes_skills_catalog.py` — vendored Hermes-runtime catalog manifest (`src/ham/data/hermes_skills_catalog.json`)
- `scripts/build_hermes_skills_catalog.py` — regenerate catalog from pinned **NousResearch/hermes-agent** (`skills/` + `optional-skills/`); requires network unless `--repo-root` points at a checkout
- `src/ham/hermes_skills_probe.py` — read-only Hermes home / profile discovery (`HAM_HERMES_SKILLS_MODE=remote_only` for non-co-located APIs)
- `src/ham/hermes_skills_install.py` — Phase 2a shared-target install: HAM-managed bundles under `~/.hermes/ham-runtime-bundles/`, merge `skills.external_dirs` in Hermes `config.yaml`, atomic write, lock, backup + audit (`HAM_HERMES_SKILLS_SOURCE_ROOT` + `.ham-hermes-agent-commit` pin, `HAM_SKILLS_WRITE_TOKEN` for apply)
- `src/ham/cursor_subagents_catalog.py` — loads `.cursor/rules/subagent-*.mdc` for chat + **`GET /api/cursor-subagents`**
- `src/ham/ui_actions.py` — parse/validate `HAM_UI_ACTIONS_JSON` for chat → UI
- `src/ham/settings_write.py` — allowlisted writes to `.ham/settings.json` (backup + audit); includes **`agents`** subtree (HAM agent profiles + `primary_agent_id`)
- `src/ham/agent_profiles.py` — Pydantic models + validation for HAM agent profiles (Hermes runtime skill catalog ids on `skills: string[]`; not Hermes CLI profiles)
- `src/ham/active_agent_context.py` — compact **guidance** block from primary HAM agent profile + vendored Hermes catalog entries for `/api/chat` (context only; no install/execution)
- `docs/HAM_CHAT_CONTROL_PLANE.md` — chat + skills intent mapping roadmap

## Deploy (API on GCP)

- **Staging SOT:** GCP project **`clarity-staging-488201`**, region **`us-central1`**, Cloud Run **`ham-api`** — see `docs/DEPLOY_CLOUD_RUN.md` (Cursor key via **Secret Manager** `ham-cursor-api-key` → env `CURSOR_API_KEY`).
- `Dockerfile` — Cloud Run–style image (`uvicorn src.api.server:app`, `PORT` aware)
- `docs/DEPLOY_CLOUD_RUN.md` — Artifact Registry + `gcloud builds submit` + `gcloud run deploy` + env vars + **private Hermes on GCE** (Direct VPC egress preferred, Serverless VPC connector fallback)
- `docs/DEPLOY_HANDOFF.md` — Vercel + Cloud Run checklist (what to set in each host)
- `docs/examples/ham-api-cloud-run-env.yaml` — copy to `.gcloud/ham-api-env.yaml` for `--env-vars-file`
- `docs/HERMES_GATEWAY_CONTRACT.md` — server-side adapter to Hermes/OpenAI-compatible chat (streaming `http` mode)
- `scripts/verify_ham_api_deploy.sh` — CORS + `/api/chat` + stream smoke test; **fails if responses look like `mock`** unless `HAM_VERIFY_ALLOW_MOCK=1`
- `scripts/render_cloud_run_env.py` — merge `.env` secrets into env YAML for deploy (`OPENROUTER_API_KEY` for openrouter; **`HERMES_GATEWAY_API_KEY`** for `http` when set in `.env`)

## Configuration & entry

- `main.py` — runtime entrypoint (CLI arg parsing, env load, orchestration assembly)
- `SWARM.md` — project-level coding instructions (loaded by memory_heist)
- `AGENTS.md` — this file
- `requirements.txt` — Python dependencies
- `README.md` — project overview and pointers
- `.env.example` — environment variable template
- `.ham.json` / `.ham/settings.json` — project config (if present)

## Hardening & remediation

- `docs/HAM_HARDENING_REMEDIATION.md` — audit summary, continuation/parser coupling, remediation order, deferred work

## Git workflow (testing / direct-main)

Two audiences: **owner/local canonical** vs **HAM VM / Cloud Agent / ephemeral remotes**.

### Cloud Agent / HAM VM Git policy

**HAM VM, Cursor Cloud Agents, and other ephemeral/remote automation environments** — **branch + PR only**:

**They may:**

- create a **feature branch** from `main` (use a descriptive, collision-safe branch name such as `cursor/<topic>-<shortid>`).
- commit **scoped** changes only.
- **`git push origin <that-branch>`** (or `-u origin <branch>` on first push).
- **`gh pr create`** targeting **`main`** when landing **product or code changes**.

**Typical landing sequence:**

```txt
git checkout -b <safe-branch-name>
git add <exact files>
git commit -m "<message>"
git push -u origin <safe-branch-name>
gh pr create --title "<title>" --body "<body>"
```

**They must not:**

- **`git push origin main`** (or any variant that advances remote `refs/heads/main` directly).
- **force-push** `main`: no `git push --force*` to `origin main` / upstream `main`.
- **repair or overwrite remote `main`** from this clone.
- Treat this workspace as **canonical source of truth** for **`main`** ( **`MAIN_PUSH_REQUIRES_OWNER_LOCAL_CONTEXT`** applies).

If asked to push to **`main`**:

1. Respond with **`MAIN_PUSH_REQUIRES_OWNER_LOCAL_CONTEXT`** and plain language:
   **`I can push this to a branch and open a PR instead.`**
2. Then carry out **`git checkout -b …` → push branch → `gh pr create`** as above.

**Read-only / report-only missions:** if the mission is strictly investigation with **no landed code/doc commits**, summarize without `gh pr create` unless the operator asked you to ship a change.

**Docs-only churn:** Prefer **in-place edits** per *Cloud Agent PR hygiene* later in this section. Use `gh pr list` overlap checks before any docs-only PR. If `gh` is unavailable or returns an auth error (for example HTTP 401), you cannot satisfy the overlap scan from automation alone—coordinate with a human who has `gh auth login`, or extend an existing open docs PR/branch manually; do not open parallel duplicate docs PRs blindly.

**Incident note (2026-04):** a VM force-push overwrote GitHub `main`; combine this policy with **branch protection** and tight VM credentials until access is productized (prefer **GitHub App** tokens).

---

### Owner-local canonical (direct `main`)

**Owner/local canonical repo** is a workstation **you control** with a trusted path (e.g. `C:\Projects\GoHam\ham`). **Nothing here blocks you** from pushing to **`main`** when **you intend to**. The **direct-`main`** flow below applies **only** in that environment.

For **that** workflow, prefer **`main` directly** — not feature branches or automatic PRs.

**Standing rule (owner-local):** Do not create draft PRs by default. Do not run `gh pr create`, `gh pr ready`, `gh pr edit`, or suggest opening a PR / pushing a feature branch for review **unless** the user explicitly asks for a PR.

**Procedure (owner-local canonical only):**

1. `git status --short --branch` and `git branch --show-current`.
2. If not on `main`: `git checkout main`, then `git pull origin main`.
3. Apply the requested change. Stage **only** intended files.
4. **Do not stage:** `desktop/live-smoke/`, repomix outputs, build artifacts, temp scripts, unrelated dirty files, or your local Cursor settings file at .cursor/settings.json (gitignored).
5. Run **scoped** tests for the touched area.
6. Commit on `main`: `git commit -m "<clear commit message>"`.
7. Push: `git push origin main`.

**Report:** commit hash, files changed, tests run, pushed yes/no, deploy/smoke status if applicable.

**If direct push to `main` is blocked** (branch protection, permissions): do **not** create a PR automatically. Stop and report `DIRECT_MAIN_PUSH_BLOCKED` with reason and required action.

**PR exception** — only when the user explicitly says e.g. “open a PR”, “make a draft PR”, “use feature branch”, or “do this as PR review”.

**Draft PRs:** Do not add PR clutter. Before substantial work, you may list and **classify** open draft PRs (superseded, docs-only safe to close, contains useful unmerged work, unknown); do **not** close or merge automatically until classified and the user approves a batch plan. Cursor enforces the short form of these rules in `.cursor/rules/ham-direct-main-workflow.mdc`.

**Separate cleanup run** — paste when you want a dedicated draft-PR audit (agents classify only; no auto-close/merge unless clearly safe):

```md
Clean up HAM draft PR clutter safely.

## Goal

There are many draft PRs for small docs notes. I want to stop accumulating PR clutter.

## Instructions

1. List all open draft PRs.

2. For each draft PR, classify:

- `SUPERSEDED_BY_MAIN`
- `DOCS_ONLY_SAFE_TO_CLOSE`
- `CONTAINS_UNMERGED_USEFUL_WORK`
- `UNKNOWN_REVIEW_NEEDED`

3. For each PR, report:
- PR number
- title
- branch
- changed files
- whether its commits are already in `main`
- recommended action

4. Do not close or merge anything yet unless clearly safe.

5. After classification, ask for approval with a batch plan:
- close these PRs
- merge these PRs
- leave these open
```

## Guidance

- `.cursor/rules/` — Cursor project rules (architecture, diffs, roles, vision sync)
- `.cursor/skills/` — eight reusable operator skills (see skills table in [`CURSOR_SETUP_HANDOFF.md`](CURSOR_SETUP_HANDOFF.md))
- `CURSOR_SETUP_HANDOFF.md` — human guide to rules, skills, subagents, commands
- `CURSOR_EXACT_SETUP_EXPORT.md` — verbatim snapshot of Cursor setup + first-class docs (regenerate via `python scripts/build_cursor_export.py`)
- `GAPS.md` — tracked gaps and active implementation notes

## Frontend (workspace UI)

- `desktop/` — Milestone 1 Electron shell (thin wrapper; see `desktop/README.md`); `npm start` after `npm run dev` in `frontend/`
- `frontend/` — Vite + React workspace; `npm run dev` (port 3000), `npm run lint` (`tsc --noEmit`)
- `frontend/src/features/hermes-workspace/screens/skills/WorkspaceSkillsScreen.tsx` — **Skills** catalog UI (`/workspace/skills`, with redirects from `/skills` and `/hermes-skills`); distinct from Cursor operator skills; API remains `/api/hermes-skills/*`

## Tests

- `tests/test_memory_heist.py` — Context Engine + Phase 1/3 guardrails (23 cases)
- `tests/test_context_engine_api.py` — Context Engine dashboard routes (project root validation; 3 cases)
- `tests/test_hermes_feedback.py` — Critic MVP + Phase 3 guardrails (7 cases)
- `tests/test_droid_registry.py` — Droid registry conventions (10 cases)
- Run: `python -m pytest` — full suite (`pytest.ini` sets `pythonpath = .`; run `pytest tests/ --collect-only -q` for current count — on the order of 1800+ tests)
- Other tests under `tests/` as added; bootstrap with `/test-context-regressions` for Context Engine focus

## Cursor Cloud specific instructions

### Services overview

| Service | Command | Port | Notes |
|---------|---------|------|-------|
| Backend API | `python3 scripts/run_local_api.py` | 8000 | Sets `HERMES_GATEWAY_MODE=mock` + loose Clerk by default |
| Frontend | `npm run dev` (in `frontend/`) | 3000 | Vite proxies `/api/*` to `:8000` automatically |

### Startup caveats

- **pytest is not in `requirements.txt`** — install separately: `pip install pytest`.
- The backend uses `scripts/run_local_api.py` for local dev (not bare `uvicorn`). It auto-loads `.env`, sets mock gateway mode, and disables Clerk auth enforcement. Alternatively use `python3 -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000`.
- Create `.env` from `.env.example` before first run. Default mock mode needs no API keys.
- Frontend lint is `npm run lint --prefix frontend` (`tsc --noEmit`).
- Full test suite: `python3 -m pytest tests/ -q`. Some HAM-on-X reactive inbox tests may have pre-existing failures unrelated to setup.
- **Hanging tests in Cloud VMs:** `tests/test_workspace_terminal.py` (3 tests) hangs indefinitely in cloud agent environments due to PTY requirements. Exclude with `--ignore=tests/test_workspace_terminal.py`. One pre-existing failure in `tests/test_model_capabilities.py::test_known_vision_model_enables_image_input` can be deselected.
- **PyJWT system conflict:** The base image has a system-installed `PyJWT 2.7.0` without RECORD metadata. Use `pip install --ignore-installed PyJWT>=2.8.0` before `pip install -r requirements.txt` if install fails.
- See `.cursor/skills/cloud-agent-starter/SKILL.md` for detailed per-area testing workflows and common quick fixes.

### HAM / Cursor Cloud Agent truth table

- **Cursor Cloud Agent** executes repo work (provider execution/runtime).
- **HAM** orchestrates missions — owns `ManagedMission` state, feed, audit, UI, follow-up/cancel controls.
- Browser never talks directly to Cursor: `Browser → HAM backend → Cursor SDK/API`.
- HAM remains the system of record; REST launch path remains primary.

### SDK bridge current truth

- SDK bridge is **live** (`HAM_CURSOR_SDK_BRIDGE_ENABLED=true`).
- It attaches to existing `bc-*` Cursor agents/runs via `src/integrations/cursor_sdk_bridge_client.py` + `bridge.mjs`.
- It streams provider-native events (`status`, `thinking`, `assistant_message`, `completed`) into HAM feed (backend bridge + SSE path to ingest; operators still poll `/feed` via HAM; no Cursor calls from the browser).
- Feed mode `sdk_stream_bridge`: native provider stream through backend bridge; frontend still talks only to HAM.
- Feed mode `rest_projection`: fallback REST refresh/projection (not provider-native streaming).
- Rollback: set `HAM_CURSOR_SDK_BRIDGE_ENABLED=false` — forces REST projection without changing launch path or frontend flow.

### Cloud Agent PR hygiene (prevent spam; Git lands branch + PR)

HAM appends deterministic guardrails to **Cursor Cloud Agent** launch prompts (`src/ham/cursor_agent_workflow.py`, `CURSOR_AGENT_BASE_REVISION=cursor-agent-v2`). See also **§ Cloud Agent / HAM VM Git policy** above for **`main`** vs **`branch → PR`** ( **`MAIN_PUSH_REQUIRES_OWNER_LOCAL_CONTEXT`** ).

From **HAM VM / Cursor Cloud**:

- **Code or doc edits you ship:** use **branch → push branch → `gh pr create`** into **`main`** (never **`git push origin main`** or **force-push `main`** from that environment).
- **Plan/report-only missions:** summarize without **`gh pr create`** unless the operator asked you to land commits.
- **Docs-only churn:** Prefer in-place edits to **canonical** paths: `README.md`, `AGENTS.md`, `VISION.md`, `docs/README.md`, `docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`, `docs/MISSION_AWARE_FEED_CONTROLS.md`, `docs/HAM_HARDENING_REMEDIATION.md`, `GAPS.md`, `.cursor/skills/**/SKILL.md`. **`CURSOR_EXACT_SETUP_EXPORT.md`** is regenerated via `python scripts/build_cursor_export.py`.
- Avoid duplicating identical “Cloud Agent truth” bullets across unrelated files when one canonical paragraph suffices.
- **Before opening a docs-only PR:** run  
  `gh pr list --repo <org>/<repo> --state open --limit 50`  
  and scan titles/branches (`gh pr view <n> --json files` helps). If overlapping docs intent exists → report **`OVERLAPPING_DOCS_PR_FOUND`** and extend the existing PR/list it — do **not** open parallel duplicates from the same automation.
- **Code vs docs cleanup:** do not lump unrelated observability/UI fixes together with unrelated doc sweeps unless the operator asked — separate PR scopes reduce reviewer noise.

When opening a permitted PR:

- Prefer titles like `docs(agent): …`, `fix(missions): …`, `feat(missions): …`, `chore(agent): …`.
- Mention **mission_registry_id / agent id** when known; list files touched; say **docs-only vs code-bearing**; list tests/commands run — see also direct-main discipline in `.cursor/rules/ham-direct-main-workflow.mdc` where applicable.

## Local hooks (Phase A baseline)

Repo hardening landed in PR1 (`pyproject.toml`, `requirements-dev.txt`, `.pre-commit-config.yaml`, `.github/CODEOWNERS`, `.github/pull_request_template.md`, `.github/ISSUE_TEMPLATE/*`, `.github/dependabot.yml`). To opt in locally:

```bash
pip install -r requirements-dev.txt
pre-commit install
# one-off audit pass
pre-commit run --all-files
```

What runs:

- **`ruff`** (lint) and **`ruff format --check`** — fast, single binary; config in `pyproject.toml [tool.ruff]`. Curated rule set: `E,F,I,N,B,UP,S,C901`. Tests/scripts get per-file ignores.
- **`mypy`** — warning-only baseline (`ignore_missing_imports = true`, no `disallow_untyped_defs` yet); not in pre-commit, but installed via `requirements-dev.txt` for local use. Will be ratcheted module-by-module in a follow-up PR.
- **`pre-commit-hooks`** standard hygiene: trailing whitespace, EOF newlines, YAML/JSON syntax, merge-conflict markers, large files (>1MB), private-key detector.
- **`gitleaks`** with **`--redact`** — secret-value scrubbed; pre-push stage only so commits stay fast. CI integration lands in Phase B.

What is **not** yet enforced:

- ESLint / Prettier on `frontend/` and `desktop/` (Phase A.2 follow-up).
- Coverage gate (`pytest --cov-fail-under=…`) (Phase B).
- Vitest scaffold + frontend test runner (Phase C).
- Vulture / deptry / knip / jscpd dead/duplicate-code checks (Phase C, warning-only).
- Branch protection / ruleset on `main` and GitHub native secret scanning (Phase B; requires repo settings change).

Do **not** wire `--fix`/`--write` autofixers into CI. Autofix is a local pre-commit concern; CI runs `--check` variants only. See the readiness lift plan in `~/.factory/specs/2026-05-03-ham-agent-readiness-lift-plan-foundations.md` for the full phased plan.

## CI guardrails (Phase B baseline)

Phase B added CI steps and a separate `secret-scan` workflow without raising the bar all at once. What runs today:

**Blocking** (failure blocks merge):

- `python` job → `python -m pytest tests/ -q --durations=20` (existing green path; `--durations=20` adds test-performance reporting at no measurable extra time).
- `python` job → `large-file-guard` step (fails if any **git-tracked** file is >1MB; current tree has zero tracked files >1MB).
- `frontend` job → `npm run lint` (existing `tsc --noEmit`).
- `gitleaks` job (in `.github/workflows/secret-scan.yml`) → scans PR diff or full tree on push, always with `--redact` so secret values never appear in logs.

**Warning-only** (`continue-on-error: true`, surfaces in the run UI but never blocks):

- `ruff check . --output-format=github` — the codebase has ~530 pre-existing lint findings; ratchet to blocking after a dedicated cleanup PR.
- `ruff format --check .` — ~280 files would reformat; ratchet after a separate `ruff format --write` PR.
- `mypy src --ignore-missing-imports` — baseline only; per-module strict overrides in a follow-up.
- `pytest --cov=src --cov-report=xml` — coverage report uploaded as artifact `coverage-xml`; **no** `--cov-fail-under` threshold yet.
- `python scripts/check_docs_freshness.py` — checks canonical docs were touched within 180 days and that markdown link targets in those files still resolve on disk (see `scripts/check_docs_freshness.py` for the tracked path list).

**Not yet wired** (deferred per the lift plan):

- Branch protection / ruleset on `main` — see `docs/BRANCH_PROTECTION_SETUP.md`. Enable only after PR2 has at least one green run on `main`.
- ESLint / Prettier on `frontend/` and `desktop/` (Phase A.2).

## Frontend tests (Phase C.1 baseline)

Phase C.1 introduced Vitest as the frontend test runner. Pure-function tests
live under `frontend/src/**/__tests__/*.test.ts`. The runner is wired with
jsdom + `@testing-library/jest-dom` matchers so component smoke tests can
land in a follow-up without further setup.

Run locally from `frontend/`:

```bash
npm install            # one-time, picks up vitest + jsdom + @testing-library/*
npm test               # one-shot run (CI mode)
npm run test:watch     # interactive watch mode for local dev
```

What's covered today:

- `frontend/src/lib/ham/__tests__/voiceRecordingErrors.test.ts` — locks user-
  facing copy for MediaRecorder / getUserMedia error mapping.
- `frontend/src/lib/ham/__tests__/desktopDownloadsManifest.test.ts` — happy /
  sad paths for the manifest parser (trust boundary on fetched JSON).
- `frontend/src/features/hermes-workspace/screens/social/lib/__tests__/socialViewModel.test.ts`
  — pins product-truth helpers (mode/readiness/frequency/volume mapping).

CI status:

- `frontend` job → `npm test` runs **warning-only** for one cycle
  (`continue-on-error: true` in `.github/workflows/ci.yml`). Promote to
  blocking in a follow-up PR after one green run on `main`.

Out of scope for C.1 (deferred):

- Component / route smoke tests (need Clerk env mocking).
- Coverage threshold for the frontend.
- ESLint / Prettier on `frontend/`.

## Python dead-code + unused-deps (Phase C.2 baseline)

Phase C.2 wires two Python static-analysis tools into the existing `python`
CI job, both **warning-only** (`continue-on-error: true`). They surface
signal without blocking merges; ratchet to blocking later via a one-line
follow-up PR after a cleanup pass.

Run locally from the repo root (after `pip install -r requirements-dev.txt`):

```bash
vulture src              # dead-code (uses [tool.vulture] in pyproject.toml)
deptry .                 # unused / transitive deps (uses [tool.deptry])
```

What's covered today:

- **Vulture** — `min_confidence=80`, `paths=["src"]`, excludes `tests/`
  and `.venv/`. Surfaces unused imports, unused variables, dead branches.
  Current baseline: 7 findings (all 90–100% confidence) — eligible for a
  separate cleanup PR.
- **Deptry** — scans `requirements.txt` against actual imports. The
  `[tool.deptry.per_rule_ignores]` table holds explicit, commented entries
  for known false positives:
  - `DEP001` ignores `winpty` (Windows-only, ships via `pywinpty`).
  - `DEP002` ignores `python-multipart` (FastAPI `Form()` implicit),
    `google-cloud-storage` (dotted import), `pywinpty`, `cryptography`
    (pinned for TLS/JWT). Plus `package_module_name_map` quietens the
    package→module hint warnings.
  - Visible `DEP003` findings (`requests`, `starlette`) are intentional
    cleanup signal — treat them as TODO to promote to direct deps.

CI status:

- `python` job → `vulture src` and `deptry .` run **warning-only**
  (`continue-on-error: true` in `.github/workflows/ci.yml`). Promote to
  blocking only after the listed dead-code cleanup PR lands.

Out of scope for C.2 (deferred):

- Cleaning the 7 vulture findings (separate cleanup PR).
- Promoting `requests` / `starlette` from transitive to direct deps.
- Pre-commit integration of vulture / deptry (CI is sufficient for now).

## Frontend dead-code + duplicate-code (Phase C.3 baseline)

Phase C.3 wires two frontend static-analysis tools into the existing
`frontend` CI job, both **warning-only** (`continue-on-error: true`).
They surface signal without blocking merges; cleanup is a separate
follow-up PR.

Run locally from `frontend/` (after `npm install` picks up the new
devDeps):

```bash
npm run dup-check    # jscpd; reads frontend/.jscpd.json
npm run knip         # knip; reads frontend/knip.json
```

What's covered today:

- **jscpd** (`^4.0.5`) — token-based duplicate-code detector.
  `min-lines=8`, `min-tokens=70`, scans `src/**/*.{ts,tsx}`, ignores
  test files. Current baseline: **54 clones, 754 duplicated lines
  (2.57%)** — well under the 5% concerning threshold. Heaviest cluster
  in `frontend/src/components/settings/DesktopLocalControlStatusCard.tsx`
  and `frontend/src/features/hermes-workspace/adapters/conductorAdapter.ts`.
- **knip** (`^5.62.0`) — TS-aware unused files / exports / deps finder.
  Reads `frontend/knip.json` (entry=`index.html`, project=`src+scripts`,
  ignores `src/components/ui/**` shadcn primitives, ignoreDependencies
  for build-config-implicit deps `autoprefixer`, `tailwindcss`,
  `@testing-library/react`). Current baseline: 17 unused files, 8
  unused deps, 2 unused devDeps, 134 unused exports, 130 unused exported
  types, 1 duplicate export. **All cleanup is deferred** to separate
  follow-up PRs.

CI status:

- `frontend` job → `npm run dup-check` and `npm run knip` run
  **warning-only** (`continue-on-error: true` in
  `.github/workflows/ci.yml`). Knip is invoked with `--no-exit-code` as
  belt-and-suspenders so the binary itself never fails the step.

Out of scope for C.3 (deferred):

- Cleaning any flagged duplicate, file, export, or dependency.
- Promoting any check (Vitest, vulture, deptry, jscpd, knip) to blocking.
- Pre-commit integration of jscpd / knip (CI is sufficient for now).
- HTML / JSON report uploads (console output is enough for the baseline).
- Frontend ESLint / Prettier (Phase A.2 follow-up).

## Issue label taxonomy

GitHub issue labels are managed by `scripts/sync_github_labels.sh` —
an idempotent bash script that wraps `gh label create --force` for each
entry. Re-run any time the taxonomy changes; existing default GitHub
labels (`bug`, `enhancement`, `documentation`, etc.) are NOT touched and
coexist with the prefixed taxonomy below.

Five orthogonal dimensions plus one operational tag:

- **`priority:P0`/P1/P2/P3** — actionability ladder (drop-everything →
  backlog).
- **`severity:critical`/high/medium/low** — impact ladder (orthogonal to
  priority; e.g. a `severity:high` regression can still be `priority:P2`
  if a workaround exists).
- **`status:needs-triage`/blocked** — workflow state.
- **`area:frontend`/backend/desktop/ci/docs** — codebase surface (matches
  the labels used in `.github/dependabot.yml`).
- **`type:bug`/feature/agent-run** — issue category. `type:agent-run`
  is for capturing notable Cursor / Hermes / droid_executor runs via
  `.github/ISSUE_TEMPLATE/agent_run.yml`.
- **`dependencies`** — Dependabot / Renovate update PRs.

To sync the live labels on the GitHub repo with the script after editing:

```bash
# locally (requires gh authenticated with `repo` scope)
./scripts/sync_github_labels.sh

# or trigger the manual workflow from the Actions tab:
gh workflow run sync-labels.yml
```

The workflow at `.github/workflows/sync-labels.yml` also auto-runs on
pushes to `main` that touch `scripts/sync_github_labels.sh` itself, so
edits to the taxonomy land on the repo without a separate manual step.

Out of scope (deferred):

- Migrating existing issues from old unprefixed labels (`bug`,
  `needs-triage`, `feature`, `agent`) to the new `type:` / `status:`
  prefixes — there are 0 open issues at the time of this taxonomy.
- Deleting GitHub's default labels — kept for compatibility with external
  tools that expect them.
- Wiring labels into branch protection or required-status checks.
