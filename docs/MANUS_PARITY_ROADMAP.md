# Manus Parity Roadmap

**Status:** Tier 1 shipped 2026-05-19; Tier 2 design pending.
**Scope:** What needs to be true for HAM to operate like Manus 1.6 / Replit Agent 3-4 / Base44 as an end-to-end chat-to-app builder, sized for a 3-5 person team.
**Related:**
[BUILDER_PLATFORM_NORTH_STAR.md](BUILDER_PLATFORM_NORTH_STAR.md) ·
[HAM_ROADMAP.md](HAM_ROADMAP.md) ·
[CUSTOM_BUILDER_STUDIO_SPEC.md](CUSTOM_BUILDER_STUDIO_SPEC.md) ·
[BUILDER_PLATFORM_GCP_RUNTIME_PLAN.md](BUILDER_PLATFORM_GCP_RUNTIME_PLAN.md) ·
[CODING_AGENT_ROUTING_MATRIX.md](CODING_AGENT_ROUTING_MATRIX.md)

---

## TL;DR

HAM has the skeleton (chat → intent → build → preview → activity stream) and a working GCP GKE preview runtime. What's missing for Manus parity is mostly the **orchestration brain** and **streaming polish**, not the plumbing. The two largest gaps are:

1. HAM's scaffolds are deterministic templates ([src/ham/builder_chat_scaffold.py](../src/ham/builder_chat_scaffold.py), ~1400 LoC) rather than LLM-generated.
2. There is no Planner → Executor → Verifier loop, which is the de facto pattern across Manus and Replit (independently converged).

The third critical item — **unrestricted network egress** from preview pods — is a security gap, not a UX gap, but blocks any responsible production rollout.

## Common patterns observed across Manus, Replit, Base44

1. **Plan-then-build with a visible task list.** Manus writes `todo.md`; Replit has Plan Mode; Base44 surfaces it implicitly. The plan is a first-class artifact, not a prompt-time scratchpad.
2. **Planner → Executor(s) → Verifier** decomposition. Manus and Replit converged independently. Single-monolithic agents have been retired.
3. **CodeAct over JSON tool-calling.** Both Manus and Replit chose "agent emits Python that calls tools" over function-calling, citing reliability on long tool chains.
4. **Isolated per-session sandbox with cheap forks.** Replit's Snapshot Engine uses 16 MiB CoW chunks in GCS with constant-time fork manifests. Manus uses per-task Ubuntu VMs. WebContainers (Bolt.new) are the outlier; container-side sandboxes are the agentic-builder norm.
5. **Curated event stream to UI, not raw model output.** "Wire particle events into Home.tsx" is filtered narration, not token-streamed thoughts.
6. **Versioning as runtime primitive.** Replit auto-commits to git per workflow step; Manus's event stream + file memory both treat rewind as core.
7. **Models abstracted, tiered, hidden.** None expose model choice or accept BYO keys. Replit tiers as Lite/Economy/Power; Manus routes per-subtask; Base44 doesn't name the model.
8. **Batteries-included backend services.** DB, auth, deploys, connectors are platform-native — the agent never asks the user to provision infra.

## Where HAM diverges (intentional)

- **BYO keys** is HAM's position. None of Manus/Replit/Base44 do this. It means HAM's multi-agent router must be visible to the user and overridable, and capability discovery has to surface "agent X is available because you connected key Y."
- **OSS, small team scope.** 3-5 users means several Tier 3 items (billing tiers, real-time collab, GDPR export) are explicitly deferred.

## HAM gap punch list

### Tier 1 — demo-blocking or critical security

| # | Item | Why | Shipped |
|---|---|---|---|
| 1 | Planner / todo-list step with human approval gate | Universal pattern across all three platforms; today HAM has only regex intent classification | PRs #366 #367 #368 (refs #356 #358 #359) |
| 2 | LLM-generated scaffolds | [src/ham/builder_chat_scaffold.py](../src/ham/builder_chat_scaffold.py) is deterministic templates only — works for calculator/tetris, fails for anything else | PR #364 (refs #361) |
| 3 | SSE / WebSocket streaming (replace polling) | Activity feed is polled; Manus/Replit stream curated events | PR #365 (refs #357) |
| 4 | Cancel button with cooperative interrupt | Runaway agent runs are unrecoverable except by killing the pod | PR #368 (refs #359) |
| 5 | Runtime errors from preview pod → chat | Today the preview is a black box — crashes show a blank screen, not a chat message | PR #369 (refs #360) |
| 6 | ✅ NetworkPolicy on preview pods | **Biggest security gap.** gVisor is in place ([gcp_preview_worker_manifest.py:65-82](../src/ham/gcp_preview_worker_manifest.py#L65-L82)) but pods can reach any external IP — exfiltrate, mine, hit internal services | PR #347 |
| 7 | ✅ Live preview janitor + job TTL | Jobs in `running` state linger forever if worker crashes; live janitor + TTL fields shipped | PR #349 |
| 8 | Queue (Cloud Tasks / Pub/Sub) between API and runtime worker | Currently synchronous — API restart loses in-flight builds | PR #363 (refs #355) |
| 9 | ✅ Sentry SDK + request-ID middleware | Zero error tracking today; production failures disappear | PR #348 |

### Tier 2 — user retention

| # | Item | Why | Shipped |
|---|---|---|---|
| 10 | Verifier step with Playwright self-test | `scripts/ham-builder-qa/` already does this manually — fold into agent loop | (partial — see #19) |
| 11 | Snapshot + rewind (content-addressed storage) | Today HAM does full source rewrite per turn; Replit's Snapshot Engine is the bar | |
| 12 | Real publish target (Cloud Run or Vercel API) | Publish button is a stub; users get no shareable URL | |
| 13 | BYO key UI + consolidate credential stores | Four scattered stores: [cursor_credentials.py](../src/persistence/cursor_credentials.py), [connected_tool_credentials.py](../src/persistence/connected_tool_credentials.py), [workspace_tool_credentials.py](../src/persistence/workspace_tool_credentials.py), [firestore_connected_tool_credentials.py](../src/persistence/firestore_connected_tool_credentials.py) | |
| 14 | Project export (zip / push-to-GitHub via OAuth) | Manus has a GitHub button; HAM is OSS and users will expect to own their code | |
| 15 | ✅ npm / pip package allowlist | Supply-chain risk; today builders run unrestricted `npm install` | PR #352 (npm wrapped at runtime; pip branch forward-looking) |
| 16 | ✅ Mobile preview iframe emulation | DESKTOP/MOBILE toggle in workbench is a stub | PR #350 |
| 17 | Lint / typecheck verifier gate on generated code | Frontend CI blocks on `tsc`, generated code is not gated | |
| 18 | ✅ Prewarmed preview pod pool | Cold-starts ~10-30s today; Replit has a warm pool | PR #353 |
| 19 | ✅ Test-generation alongside features in the verifier | Replit Agent 3 writes tests; HAM doesn't | PR #351 |
| 20 | User-writable skills | Manus `/skill-creator` equivalent; current skills are read-only from vendored Hermes catalog |
| 21 | GitHub OAuth | Also unlocks #14 export flow |
| 22 | Content-addressed snapshot diff | Replace full-rewrite to make rewind cheap |

### Tier 3 — defer for 3-5 user scope

Billing infra · tiered rate limits · real-time collab (CRDTs/OT) · GDPR data export · notifications (email/Slack) · project templates and fork-from-existing · OpenTelemetry distributed tracing · external webhook receiver · schema migrations · feature flags · enterprise RBAC.

### Already in place — do not redo

- Clerk auth + email/domain restriction at the API level
- gVisor sandbox + non-root + read-only FS + dropped caps on preview pods
- Manifest validation (rejects `..` and shell metacharacters)
- Context-window compaction in [src/memory_heist.py](../src/memory_heist.py)
- Frontend TypeScript blocking in CI
- Soft-delete via [src/ham/workspace_purge.py](../src/ham/workspace_purge.py)
- Retry logic on Clerk session and Nous gateway HTTP fallback
- Responsive mobile UI (separate concern from preview emulation)

## File landmarks

| Layer | File |
|---|---|
| Chat → intent classification | [src/ham/agent_router.py](../src/ham/agent_router.py), [src/ham/builder_mutation_router.py](../src/ham/builder_mutation_router.py) |
| Scaffold (template-driven, ~1400 LoC) | [src/ham/builder_chat_scaffold.py](../src/ham/builder_chat_scaffold.py) |
| Edit worker (Hermes-wired) | [src/ham/builder_edit_worker.py](../src/ham/builder_edit_worker.py) |
| Job model (`CloudRuntimeJob`) | [src/persistence/builder_runtime_job_store.py](../src/persistence/builder_runtime_job_store.py) |
| GCP preview pods | [src/ham/gcp_preview_runtime_client.py](../src/ham/gcp_preview_runtime_client.py), [src/ham/gcp_preview_worker_manifest.py](../src/ham/gcp_preview_worker_manifest.py) |
| Janitor (dry-run only) | [src/ham/preview_janitor.py](../src/ham/preview_janitor.py) |
| Frontend workbench (~113KB) | [frontend/src/features/hermes-workspace/workbench/WorkspaceWorkbench.tsx](../frontend/src/features/hermes-workspace/workbench/WorkspaceWorkbench.tsx) |
| Capabilities API (~2400 LoC) | [src/api/builder_sources.py](../src/api/builder_sources.py) |
| QA harness (fold into verifier) | [scripts/ham-builder-qa/](../scripts/ham-builder-qa/) — Playwright snapshot/preview alignment |

## Execution plan: parallelizing Tier 1 for Factory AI

You cannot hand all of Tier 1 to a cloud agent platform in a single fire-and-forget batch. Three reasons:
1. Most Tier 1 specs touch the same hot files ([chat.py](../src/api/chat.py), [builder_sources.py](../src/api/builder_sources.py), [builder_runtime_worker.py](../src/ham/builder_runtime_worker.py), `WorkspaceWorkbench.tsx`) — parallel agents will merge-conflict.
2. Five items depend on contracts that must be decided first (planner output schema, SSE envelope, queue message shape, cancel signal, error envelope) — parallel agents will invent five incompatible schemas.
3. Three items need infrastructure decisions only the team can make (real GKE NetworkPolicy + allowed domains, Sentry account/DSN, queue technology pick).

### Phase 0 — manual, blocks everything else

Lock the shared contracts as Pydantic models + TypeScript types in a single small PR:

- Planner output schema (todo list shape)
- SSE event envelope
- Job queue message shape
- Cancel signal protocol
- Runtime-error envelope
- Approval-gate state machine

This is a half-day of design work that unblocks ~2 weeks of parallel implementation.

### Phase 1 — parallel-safe, fire at Factory

Disjoint files, no integration risk between agents:

- NetworkPolicy YAML + egress proxy config (#6)
- Sentry SDK wiring, BE + FE (#9)
- Job TTL fields + live janitor deploy (#7)
- Mobile preview iframe emulation (#16)
- Test-generation step in verifier (#19)
- npm/pip package allowlist (#15)
- Prewarmed pod pool (#18)

### Phase 1 — Status (shipped 2026-05-19)

- **NetworkPolicy on preview pods** — PR #347
- **Sentry SDK + request-ID middleware** — PR #348
- **Job TTL + live janitor** — PR #349
- **Mobile preview iframe emulation** — PR #350
- **Test-generation step in verifier** — PR #351
- **npm/pip package allowlist** — PR #352 (npm wrapped at runtime; pip branch forward-looking)
- **Prewarmed preview pod pool** — PR #353
- Phase 0 shared contracts also shipped (PRs #334–#338).
- Post-Phase-1 catalog patch (`STEP_VERIFICATION_FAILED`) landed on `main` as a direct commit.

### Phase 2 — serialize, review each PR

These edit the hot files and need end-to-end integration testing:

- Planner step → activity feed (#1)
- Approval gate (#1)
- SSE replacing polling (#3)
- Cancel button + signal handling (#4)
- Runtime errors → chat (#5)
- LLM-generated scaffolds replacing template generation (#2)

### Standing instructions for every Factory prompt

Every prompt MUST include HAM's conventions:

> Minimal diff per slice. No second harness. No new abstractions until the second use. Do not redesign the bridge contract. Match existing patterns in `src/ham/builder_*` and `src/api/builder_*`. Preserve Hermes/Bridge/Droid separation.

Without these, cloud agents will over-build.

### Realistic timeline

- **Phase 0**: Completed in one working session (contracts locked; PRs #334–#338 merged 2026-05-18).
- **Phase 1**: Completed in ~1–2 days wall-clock with parallel Factory agents (PRs #347–#353 merged 2026-05-18 / 2026-05-19).
- **Phase 2**: Completed with human review per PR (planner, approval gate, SSE, cancel, runtime errors → chat, LLM scaffolds, queue) via PRs #363–#370 on 2026-05-19.
- **Tier 1 complete**: All Tier 1 items (#1–#9) are now marked shipped on `main`.

## Skills toolkit

Installed at [.claude/skills/](../.claude/skills/) via commit `1a22d9d5`. Skills derived from [mattpocock/skills](https://github.com/mattpocock/skills):

| Skill | Use |
|---|---|
| `setup-matt-pocock-skills` | One-time config (issue tracker, label vocab, doc layout) |
| `grill-with-docs` | Phase 0 contract design — builds CONTEXT.md alongside |
| `to-prd` | Convert this conversation into a PRD |
| `to-issues` | Split PRD into independently-grabbable GitHub issues for Factory |
| `diagnose` | Stuck-job and snapshot-alignment debugging |
| `tdd` | Red-green-refactor for Phase 2 serialized work |
| `improve-codebase-architecture` | Periodic entropy reduction (e.g. consolidating the four credential stores) |
| `grill-me` | Non-code planning grilling |
| `zoom-out` | Navigating the 2400-LoC [builder_sources.py](../src/api/builder_sources.py) and similar |
| `handoff` | Compacting a session for the next agent or human |
| `prototype` | Trying workbench UI variations before committing |
| `write-a-skill` | Creating HAM-specific skills next (planner protocol, SSE schema, etc.) |

Recommended first-run sequence in a fresh session:

1. `/setup-matt-pocock-skills` — pick GitHub for issue tracker
2. `/grill-with-docs` on the Tier 1 Phase 0 contracts
3. `/to-prd` — turn the resulting design into a PRD
4. `/to-issues` — split the PRD into GitHub issues
5. Hand issues to Factory for Phase 1 parallel work
