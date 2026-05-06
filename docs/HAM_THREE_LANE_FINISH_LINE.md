# HAM Three-Lane Finish-Line Roadmap

## Purpose

[`HAM_THREE_LANE_ARCHITECTURE.md`](HAM_THREE_LANE_ARCHITECTURE.md) defines **what the three lanes are** (web app, desktop app, cloud/hosted agent). This doc defines **"done enough"** for each lane: what evidence already exists, what gaps remain, and a small, honest **finish-line checklist** that the team can reduce to PR-sized work.

It is **not** a re-architecture. It does not redraw boundaries, rename modes, or commit to new strategic bets. It is a focused product-truth checklist so contributors and agents can tell when a lane is **shippable** vs **still-beta** without reading every runbook.

### Scope of this roadmap

- **In scope:** product-truth checklists per lane, cross-lane boundary risks, human-gated vs agent-safe distinction, "do not build yet" list, suggested order of work.
- **Out of scope:** code changes, new APIs, new flags, hosted-config changes, secrets rotation, branch-protection edits, npm audit / auto-merge / strict-typing toggles, Sentry / analytics / DAST adoption.
- **Hard non-goals:** touching live social actions, autonomy execution paths, or anything in the GoHAM permission model beyond *documenting* what already exists.

### Definition of done (DoD) shorthand used below

| Symbol | Meaning |
|:---:|---|
| ✅ | Already in repo / already true on `main` — evidence cited |
| 🟡 | Partial — exists but rough; a follow-up PR closes it |
| ⏳ | Not yet — explicit gap; PR-sized next step described |
| 🚫 | Deliberately deferred — see [What should not be built yet](#what-should-not-be-built-yet) |

---

## Lane 1 — Web app

### Positioning recap

Hosted browser command center on Vercel, talking to Cloud Run API. Primary navigation under `/workspace/*` (chat, files, terminal, settings, social cockpit + policy, operations / conductor / missions, skills, profiles, memory). Auth via Clerk when configured; workspace/session state lives in cloud, not the browser.

### Finish-line checklist

| Surface | Status | Evidence / Gap |
|---|:---:|---|
| Hosted browser command center | ✅ | `frontend/` Vite + React app, deployed on Vercel; proxies `/api/*` to Cloud Run (see `frontend/vite.config.ts`, [`DEPLOY_HANDOFF.md`](DEPLOY_HANDOFF.md)) |
| Workspace management | ✅ | `/workspace/*` routes; chat / files / terminal / settings panes wired |
| Chat / session UX | ✅ | `POST /api/chat`, `POST /api/chat/stream` (server-side adapter; browser never calls Hermes directly) — see [`HERMES_GATEWAY_CONTRACT.md`](HERMES_GATEWAY_CONTRACT.md) |
| Settings ↔ local-runtime messaging | 🟡 | Settings UI exists; copy still occasionally implies "browser sees laptop" without naming the bridge. Finish-line PR: copy audit on settings + Hermes operator strip |
| Social cockpit / HAMgomoon UI | ✅ | `frontend/src/features/hermes-workspace/screens/social/*` with social view-model tests pinning product truth (mode / readiness / frequency / volume) |
| Operations / conductor / missions | 🟡 | Mission feed + controls scoped by `mission_registry_id` ([`MISSION_AWARE_FEED_CONTROLS.md`](MISSION_AWARE_FEED_CONTROLS.md)); follow-up: visual three-lane diagram and clearer empty-state copy |
| Formatter & lint baseline | ✅ | `frontend/.prettierrc.json` + CI `format:check` blocking (PR #199 / #200 / #201); knip + jscpd warning-only |
| Vitest baseline | ✅ | `frontend/src/**/__tests__/*.test.{ts,tsx}` runnable via `npm test`; CI warning-only |

### Evidence of readiness

- `npm run lint`, `npm run format:check`, `npm test`, `npm run build` all pass on `main`.
- 30+ Vitest cases pin product-truth helpers (social view-model, voice-recording errors, desktop-downloads manifest).
- Hosted deploy path (Vercel + Cloud Run) is documented end-to-end in [`DEPLOY_HANDOFF.md`](DEPLOY_HANDOFF.md).

### Remaining gaps

- **Frontend ESLint** is still missing — `npm run lint` is `tsc --noEmit` (type-check, not a linter). Adding a real ESLint config is a separate PR.
- **TS `strict` mode** is not on; tracked but not in this roadmap.
- **Settings copy audit** for "what runs in the browser vs the bridge vs cloud" — small docs-and-copy PR.

### PR-sized next steps (web lane)

1. `docs(web): copy audit for local-runtime vs hosted browser` — settings strings only; no behavior change.
2. `docs(web): add three-lane visual diagram` — embed inline SVG/mermaid in [`HAM_THREE_LANE_ARCHITECTURE.md`](HAM_THREE_LANE_ARCHITECTURE.md).
3. `chore(frontend): add eslint config` — separate from this roadmap; tracked here only as a downstream signal.

---

## Lane 2 — Desktop app

### Positioning recap

Electron, Windows-first today. `desktop/` ships local-control modules (browser-real CDP, sidecar, audit, web-bridge, preload contract). Tag-driven release pipeline produces signed-and-verified Windows portable + NSIS installers via `.github/workflows/desktop-release.yml`.

### Finish-line checklist

| Surface | Status | Evidence / Gap |
|---|:---:|---|
| Electron Windows-first app | ✅ | `desktop/main.cjs`, `desktop/preload.cjs`, electron-builder Windows targets in `desktop/package.json` |
| Local control surface | ✅ | `desktop/local_control_*.cjs` (status / policy / audit / sidecar / browser real-CDP / web-bridge); 99 tests pass via `npm --prefix desktop run test:local-control` |
| Local files / browser / computer-control boundary | ✅ | Documented in [`desktop/local_control_v1.md`](desktop/local_control_v1.md) and [`capabilities/computer_control_pack_v1.md`](capabilities/computer_control_pack_v1.md) |
| Desktop release / download path | ✅ | `.github/workflows/desktop-release.yml` builds portable + NSIS on `desktop-v*` tag; SHA256 sidecar + GitHub Release notes |
| GoHAM local-mode permissions | 🟡 | Implemented in code (kill-switch, audit hooks, web-bridge enablement) but **not consolidated** into one human-readable permission doc. Finish-line PR: single `docs/desktop/goham_permissions.md` summarizing prompts, kill-switch, audit boundary |
| Unsupported / stale Linux installer expectations | 🟡 | [`HAM_THREE_LANE_ARCHITECTURE.md`](HAM_THREE_LANE_ARCHITECTURE.md) already says "Windows-first; do not imply Linux installers." Finish-line PR: ensure `README.md`, `desktop/README.md`, and any `*INSTALLER*.md` echo the same line |
| Formatter baseline | ✅ | `desktop/.prettierrc.json` + CI `format:check` blocking (PRs #202 / #203 / #204) |
| Type checker | ⏳ | Desktop is plain CommonJS `.cjs` with no JSDoc-typed boundary. Not on the immediate finish line; tracked as future work, **not** this PR |

### Evidence of readiness

- `npm --prefix desktop run test:local-control` → 99 / 99 pass.
- `npm --prefix desktop run format:check` blocks merges in CI.
- 10+ `desktop-v*` tags in the last release window — release automation is exercised, not theoretical.

### Remaining gaps

- **Support matrix doc**: explicit table showing Windows = supported, macOS = "not yet" or "best-effort dev", Linux = "not a product path".
- **GoHAM permission model**: what the user is consenting to, what the kill-switch covers, what is logged.
- **Stale Linux references**: any older README / docs paragraphs that imply a shipping Linux installer should be retired or labeled archival.

### PR-sized next steps (desktop lane)

1. `docs(desktop): add Windows-first support matrix` — single table, links from `desktop/README.md` + [`HAM_THREE_LANE_ARCHITECTURE.md`](HAM_THREE_LANE_ARCHITECTURE.md).
2. `docs(desktop): consolidate GoHAM local-mode permissions` — collect today's kill-switch / audit / bridge enablement copy into one operator-readable doc.
3. `docs(desktop): retire stale Linux-installer prose` — search-and-narrow, archive into `docs/archive/` if needed.

---

## Lane 3 — Cloud / hosted agent lane

### Positioning recap

Cloud Run API (`src/api/server.py`, FastAPI) serves the Vercel frontend. Hermes gateway (server-side adapter) handles model traffic. Cursor / Factory / Droid execution runs as subprocess CLI muscle behind durable launch records (`ControlPlaneRun`). Managed missions / jobs / review queues persist in Firestore (or local SQLite in dev). Audit, secrets, and social/autonomy safety gates are server-side.

### Finish-line checklist

| Surface | Status | Evidence / Gap |
|---|:---:|---|
| Cloud Run API | ✅ | `Dockerfile`, [`DEPLOY_CLOUD_RUN.md`](DEPLOY_CLOUD_RUN.md), `scripts/verify_ham_api_deploy.sh` |
| Vercel ↔ Cloud Run integration | ✅ | Frontend proxies `/api/*` to Cloud Run; verified end-to-end in [`DEPLOY_HANDOFF.md`](DEPLOY_HANDOFF.md) |
| Hermes gateway | ✅ | `src/integrations/nous_gateway_client.py` + [`HERMES_GATEWAY_CONTRACT.md`](HERMES_GATEWAY_CONTRACT.md) (`HERMES_GATEWAY_MODE` / `HERMES_GATEWAY_API_KEY`); browser never calls directly |
| Cursor / Factory / Droid execution | ✅ | `src/tools/droid_executor.py`, `src/integrations/cursor_sdk_bridge_client.py`, `bridge.mjs`; `HAM_CURSOR_SDK_BRIDGE_ENABLED` toggles bridge vs REST projection ([`ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md)) |
| Managed missions / jobs / review queues | 🟡 | `ManagedMission` shipped with feed/audit; honest E2E scope and correlation gaps tracked in [`ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md). Finish-line PR per phase |
| Audit / logging / secrets boundaries | ✅ | `src/ham/social_delivery_log.py` (redact), GCP Secret Manager (`ham-cursor-api-key`), `.env.example` template; **no** secret values in git |
| Social / autonomy safety gates | 🟡 | HAMgomoon Telegram automation + `HAM_X` redaction utilities exist; consolidated **operator-readable** safety doc would help. Finish-line PR: `docs/ham-x-agent/safety_gates.md` index of what is gated, by whom, with what default |
| OpenAPI snapshot | ✅ | `docs/api/openapi.json` (3.1.0, 198 paths, 163 schemas) committed; regenerated via `scripts/export_openapi.py` (PR #198) |

### Evidence of readiness

- Pytest suite (1900+ tests) green on `main` per CI.
- OpenAPI snapshot is committed, not just runtime — agents can read it without booting the API.
- Cloud Run + Vercel deploy paths are scripted and documented; recovery runbook exists ([`RUNBOOK_HAM_MODEL_RECOVERY.md`](RUNBOOK_HAM_MODEL_RECOVERY.md)).

### Remaining gaps

- **Mission UX parity**: managed-mission phases A–D have curl examples ([`examples/managed_cloud_agent_phases/README.md`](examples/managed_cloud_agent_phases/README.md)), but the operator UI is not yet at parity for every phase — tracked, not this PR.
- **Audit boundary doc**: which sinks exist (server logs, social-delivery log JSONL, audit JSONL) and which are *truth* vs *advisory*.
- **Safety-gate index**: a single page that names every "must stay human-gated" surface (see [What must stay human-gated](#what-must-stay-human-gated) below).

### PR-sized next steps (cloud lane)

1. `docs(cloud): audit boundary one-pager` — list each log sink and mark canonical vs advisory.
2. `docs(cloud): safety-gate index for social/autonomy` — one page that points at every approval surface; no behavior change.
3. `docs(cloud): mission phase UX parity table` — extend [`ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md) with a "where the UI stands per phase" column.

---

## Cross-lane boundary risks

These are the places where lanes touch and where wrong copy or wrong default flags create real harm. Each row is a **risk we are explicitly aware of**, not a bug to fix in this PR.

| Risk | Where it shows up | Mitigation today |
|---|---|---|
| **Hosted browser pretending to be the laptop** | "Open my files" / "Run on my browser" copy in web settings | [`HAM_THREE_LANE_ARCHITECTURE.md`](HAM_THREE_LANE_ARCHITECTURE.md) explicitly says the browser does not magically see the laptop; copy audit pending |
| **Cloud-side Playwright marketed as desktop control** | `/api/browser*` routes vs `desktop/local_control_*` modules | Two separate modules + two separate docs; **never** combine in product copy |
| **Hermes called from the browser** | Old SPA prototypes that hit gateway URLs directly | Server-side adapter pattern is enforced in `src/api/chat.py`; browser only knows `/api/chat` |
| **GoHAM autonomy without consent UI** | High-autonomy local/browser flows | Today gated by desktop kill-switch + audit hooks; user-facing permission summary doc is the next step |
| **Cursor Cloud Agent overwriting `main`** | VM force-push incident (2026-04) | `MAIN_PUSH_REQUIRES_OWNER_LOCAL_CONTEXT` policy in [`AGENTS.md`](../AGENTS.md); branch protection still pending |
| **Linux installer rumours** | Old README paragraphs, screenshots | Architecture doc says Windows-first; full prose audit pending |
| **Social posts shipped without operator approval** | HAMgomoon / `HAM_X` paths | All live social actions stay behind explicit operator approvals; safety-gate index pending |
| **Secrets leaked via OpenAPI / docs / logs** | Generated OpenAPI snapshots, log dumps | OpenAPI exporter sets safe mock env defaults; gitleaks runs on every PR + push; redact() applied in social delivery log |

---

## What must stay human-gated

These are non-negotiable approval surfaces. Agents and droids may **draft / propose / explain**, but a human operator presses the button.

- **Live social posts** (any HAMgomoon / Telegram / X publish path).
- **High-autonomy GoHAM mode** transitions (entering / leaving, scope expansion).
- **Desktop local-control elevation** (browser-real CDP attach, web-bridge pairing token issuance, kill-switch override).
- **Production deploys** to Cloud Run or Vercel (CI builds; promotion is operator-gated).
- **Branch protection / ruleset edits** on `main` (enabling, disabling, weakening).
- **Secrets writes** — Secret Manager, `.env`, GitHub Actions secrets.
- **Pushes to `main`** from any **HAM VM / Cursor Cloud Agent / ephemeral remote** (always `branch → PR`).
- **Force-push to any shared branch**.
- **`gh pr merge --auto`** on PRs touching social / autonomy / secrets / deploy / branch-protection.

---

## What agents / droids can safely do

These are the "yes, please" lanes — agentic work with low blast radius and reversible outputs.

- **Docs PRs** that follow the [`AGENTS.md`](../AGENTS.md) Cloud Agent Git policy (`branch → push → PR into main`).
- **Tooling-only scaffolds** (e.g. add a formatter config + scripts; do **not** mass-format source in the same PR).
- **Test-only PRs** that pin existing behavior (e.g. social view-model assertions).
- **OpenAPI / generated artifact regeneration** via committed scripts (`scripts/export_openapi.py`, `scripts/build_cursor_export.py`, `scripts/build_hermes_skills_catalog.py`).
- **Dependabot / Renovate dependency PRs** within the configured grouping rules in `.github/dependabot.yml`.
- **CI hardening PRs** that add a new check as **warning-only** first; promotion to blocking is a separate PR.
- **Issue triage** using the 5-dimension label taxonomy (`priority:*`, `severity:*`, `status:*`, `area:*`, `type:*`).
- **Reading the wiki / OpenAPI / runbooks** as context for any task.

---

## What should not be built yet

Avoid premature commitments — these are explicit "wait" items.

- **macOS / Linux desktop installers** — Windows-first stays the product path until packaging budget is real.
- **Re-embedding Cursor / Droid HTTP stacks in the browser** — execution stays subprocess CLI muscle; supervision stays HAM-side.
- **Generic "HAM Agent Mode"** marketing — use **GoHAM mode** for high-autonomy. Reserve "agent mode" wording so it does not conflict with IDE marketing.
- **Cross-tenant social autonomy** — single-operator, single-workspace gates first.
- **DAST / Sentry / product-analytics adoption** — tracked in readiness, but **not** part of finish-line scope.
- **Strict typing flag-flip** (mypy strict, tsc strict) — productive when ratcheted module-by-module, not flipped repo-wide.
- **Branch-protection auto-enable from CI** — must be operator-applied; documented in [`docs/BRANCH_PROTECTION_SETUP.md`](BRANCH_PROTECTION_SETUP.md) where present.
- **Coverage gate on `main`** — coverage is uploaded warning-only today; gating is a separate decision.

---

## Suggested implementation order

The order below is intentionally **docs-first**. Every step is small, reversible, and unblocks the next.

1. **Web lane UX / product-truth cleanup** — settings + Hermes operator-strip copy audit; ensure no surface implies "the browser sees the laptop" without naming the bridge. *(Docs only.)*
2. **Desktop support matrix + local-control permission docs** — single Windows-first matrix, plus a consolidated GoHAM permission summary referencing existing kill-switch / audit / web-bridge code paths. *(Docs only.)*
3. **Cloud agent execution / audit boundary docs** — one-pager mapping each log sink to canonical-vs-advisory, plus the safety-gate index for social / autonomy approval surfaces. *(Docs only.)*
4. **GoHAM permission model doc** — ties web + desktop + cloud copy together so high-autonomy flows have one canonical operator page. *(Docs only.)*
5. **Implementation PRs per lane** — only after the four docs land. Each lane gets its own scoped PRs (e.g. frontend ESLint, desktop type checker baseline, cloud audit boundary helpers). No omnibus PRs.

Each numbered step above is intended to be **one PR**, not a milestone.

---

## Validation hooks for this roadmap

- `python3 scripts/check_docs_freshness.py` — runs over the canonical allowlist; this file is a new doc, not on the allowlist, so the script will not regress on it. Re-run before any follow-up PR that edits this file plus an allowlisted doc.
- `gh pr list --repo Code-Munkiz/ham --state open --limit 50` — overlap scan before opening another docs-only PR (per [`AGENTS.md`](../AGENTS.md) Cloud-Agent PR hygiene). Report `GH_PR_OVERLAP_CHECK_UNAVAILABLE` if `gh` lacks auth.

---

## Related reading

- [`HAM_THREE_LANE_ARCHITECTURE.md`](HAM_THREE_LANE_ARCHITECTURE.md) — the lane definitions this roadmap walks against
- [`ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md) — managed mission phase shipping status
- [`MISSION_AWARE_FEED_CONTROLS.md`](MISSION_AWARE_FEED_CONTROLS.md) — `mission_registry_id` scoping
- [`HERMES_GATEWAY_CONTRACT.md`](HERMES_GATEWAY_CONTRACT.md) — server-side adapter contract
- [`desktop/local_control_v1.md`](desktop/local_control_v1.md) — desktop local-control product path
- [`capabilities/computer_control_pack_v1.md`](capabilities/computer_control_pack_v1.md) — control-plane semantics
- [`api/README.md`](api/README.md) — committed OpenAPI snapshot + regen instructions
- [`AGENTS.md`](../AGENTS.md) — Cloud Agent Git policy and PR hygiene
- [`VISION.md`](../VISION.md) — pillars and stable bets
