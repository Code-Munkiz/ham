# HAM Legacy / Deprecation Audit

Baseline: `main` at `f1a11c10` (`fix(workbench): soften builder stream recovery`).

Scope: read-only audit for deprecated, legacy, stale, confusing, previous-direction, or no-longer-relevant code/docs/config in HAM. This report does **not** delete or change runtime code. It distinguishes required fallbacks from obsolete cruft.

## 1. Executive summary

This audit found **22 findings**:

- **6 keep/current** items that are intentionally live.
- **5 fallback/compatibility** items that must stay until replacement coverage exists.
- **7 stale/confusing** items that should be renamed, documented, hidden, or archived.
- **4 local-noise / deployment-hygiene** items that need owner approval before cleanup.

Highest-confidence conclusions:

- **Build Kit v1 cannot be removed now.** It is still the active fallback context when Build Registry v2 is disabled, has missing metadata, or fails validation/composition/rendering.
- **The old deterministic scaffold runtime is retired**, but the naming "v1 Builder Kit" now ambiguously means "fallback prompt context," not "old runtime engine."
- **Build Registry v2 is current and live**, but some module docstrings still say "unwired."
- **Builder Studio task launch is not active**, but redirected route/screen code and Coding Agents labels/adapters still create product ambiguity.
- **Right-pane managed approval/status/result ownership is mostly correct**, and chat is clean for the managed lane, but there are still parallel task/conductor/operations concepts that need product IA decisions.
- **Deployment docs/config still allow stale-image confusion**, especially mutable `:staging`, `SKIP_BUILD=1`, mock-default env examples, and hardcoded Cloud Run URLs.

## 2. What is intentionally current

| Finding | Evidence | Recommendation | Risk | Suggested next step |
|---|---|---|---|---|
| Build Registry v2 app routing and scaffold context | `src/ham/build_registry/intent.py`, `src/ham/build_registry/scaffold_context.py`, `src/ham/builder_llm_scaffold.py` | **Keep** | Low | Treat v2 registry and playbook context as current scaffold guidance. |
| Builder Happy Path LLM scaffold | `src/ham/builder_chat_scaffold.py` calls `generate_scaffold()`; `src/ham/builder_llm_scaffold.py` applies context and quality repair | **Keep** | Low | Keep this as the app/site/dashboard generation path; continue hardening observability. |
| Scaffold quality / repair / deterministic fallbacks | `src/ham/scaffold_quality.py`; tests include `tests/test_scaffold_quality.py` Sales Ops/SaaS/Admin gate cases | **Keep** | Low | Keep repair/fallback tests as release gates for scaffold changes. |
| Right-pane managed approval relocation | `frontend/src/features/hermes-workspace/workbench/WorkbenchManagedApprovalMount.tsx`, `WorkbenchBuildStatusPanel.tsx`, `WorkspaceWorkbench.tsx`; tests under `workbench/__tests__/` | **Keep** | Low | Keep right pane as approval/status/result owner. |
| Chat-side minimal lifecycle pointers | `WorkspaceChatScreen.tsx`, `CodingPlanCard.tsx`, `codingPlanCardCopy.ts` | **Keep** | Low | Keep chat clean; use lifecycle pointers only, not action dashboards. |
| Cloud Run backend + Vercel frontend split | `docs/DEPLOY_CLOUD_RUN.md`, `scripts/deploy_ham_api_cloud_run.sh`, `vercel.json`, `frontend/vercel.json` | **Keep with cleanup** | Medium | Clarify deploy truth and immutable-image policy. |

## 3. What is intentionally fallback

| Finding | Evidence | Recommendation | Risk | Suggested next step |
|---|---|---|---|---|
| v1 Builder Kit prompt context | `src/ham/builder_kits.py`, `src/ham/data/builder_kits/*.json`, `src/ham/build_registry/scaffold_context.py` returns `source="v1"` when flag off / metadata missing / v2 error | **Keep** | High if removed | Rename/document as **"v1 Builder Kit fallback context"**. |
| v1 template-kind router | `src/ham/builder_kit_router.py`; used in `builder_chat_scaffold.py`, `droid_build.py`, `opencode_build.py`, `claude_agent_build.py`, `cursor_agent_workflow.py` before v2 enrichment | **Keep** | Medium | Document as baseline classifier, not a deterministic scaffold engine. |
| Silent v2-to-v1 fallback | `src/ham/build_registry/scaffold_context.py`; tests in `tests/test_build_registry_scaffold_context.py` assert `registry_v2_disabled`, metadata missing, bad app type | **Keep** | High if removed | Preserve until every live app type has non-v1 fallback coverage and owner approves behavior change. |
| Managed approval mechanics for Droid/OpenCode | `ManagedProviderBuildApprovalPanel.tsx` sends `proposal_digest`, `base_revision`, `confirmed: true`; provider wrappers bind endpoints | **Keep** | High if changed | Do not refactor until all provider lifecycle tests remain green. |
| Claude/Cursor separate flows | `src/api/claude_agent_build.py`, `src/ham/cursor_agent_workflow.py`, Cursor mission/control-plane docs | **Keep / investigate scope** | Medium | Keep separate until product defines shared right-pane lifecycle for Claude/Cursor. |

## 4. What appears deprecated or stale

| Finding | Evidence | Recommendation | Risk | Suggested next step |
|---|---|---|---|---|
| Build Registry module docstrings say "unwired" | `src/ham/build_registry/__init__.py` says "unwired loader/composer" and "Not imported by chat, scaffold, or API paths"; `src/ham/build_registry/scaffold_context.py` says "Not called by chat, scaffold, or API paths until Phase 2C" | **Deprecate wording** | Medium confusion | Update docstrings to "internally wired for scaffold prompt context; no public API." |
| Builder Studio route stack | `WorkspaceApp.tsx` redirects `/workspace/builder-studio` to `/workspace/settings?section=builders`; `BuilderStudioScreen.tsx` and route tests remain | **Investigate / staged removal** | Medium | Decide whether to archive/remove the unrouted screen stack or keep as future design asset. |
| Coding Agents route/labels/adapters | `/workspace/coding-agents` redirects to Builder Studio; `screens/coding-agents/codingAgentLabels.ts`, `adapters/codingAgentsAdapter.ts` remain | **Investigate** | Medium-high | Confirm if dedicated Coding Agents route is retired; prune launch/audit helpers if no active screen consumes them. |
| Voice MVP standalone deploy doc | `docs/VOICE_MVP_README.md` contains standalone legacy deploy flow (`ham-audio`, `gcr.io`, `vercel deploy`) and is not surfaced as active deploy SOT | **Archive/remove** | Medium | Move to `docs/archive/` or mark historical at top. |
| Historical checkpoint docs look active by filename | Many `docs/build-kit-registry-v2/*CHECKPOINT*.md` files | **Keep as history; label/index** | Low | Add index table with "current vs historical" and latest status pointer. |

## 5. What appears risky/confusing

| Finding | Evidence | Recommendation | Risk | Suggested next step |
|---|---|---|---|---|
| Mutable `:staging` image and `SKIP_BUILD=1` can redeploy stale code | `scripts/deploy_ham_api_cloud_run.sh`; recent incident required redeploy from commit tag | **Investigate / harden** | High | Prefer commit-specific tags/digests by default; require explicit stale-image override. |
| Env example defaults to mock gateway | `docs/examples/ham-api-cloud-run-env.yaml` has `HERMES_GATEWAY_MODE: mock`; deploy docs warn full env-file replacement can drop real vars | **Harden docs/script** | High | Add a deploy guard for staging/prod: block `mock` unless `ALLOW_MOCK_DEPLOY=1`. |
| Hardcoded Cloud Run URL in Vercel configs | `vercel.json`, `frontend/vercel.json` rewrite `/api/*` to `https://ham-api-13856606312.us-central1.run.app` | **Investigate** | Medium | Decide if single staging origin is intended; otherwise externalize or document as staging-only. |
| Deploy docs mention `VITE_HAM_API_BASE`, but Vercel path now uses same-origin rewrites | `docs/DEPLOY_CLOUD_RUN.md`, `docs/DEPLOY_HANDOFF.md`, `frontend/src/lib/ham/api.ts`, Vercel rewrite configs | **Update docs** | Medium | Clarify: Vercel production uses same-origin `/api` rewrite; `VITE_HAM_API_BASE` is local/alternate host path. |
| Parallel product surfaces can confuse agents/users | `WorkspaceTasksScreen.tsx`, `WorkspaceConductorScreen.tsx`, `WorkspaceOperationsScreen.tsx`, `PlanCard.tsx`, `WorkspaceBuilderPlanCards.tsx` | **Investigate** | Medium | Product IA decision: keep distinct lanes or consolidate around chat + workbench. |

## 6. What can be removed now

No runtime code should be removed immediately from this audit alone.

Lower-risk cleanup candidates after owner approval:

| Candidate | Evidence | Recommendation | Risk | Suggested next step |
|---|---|---|---|---|
| Empty stray file `=2.8.0` | Untracked, empty-looking local artifact consistent with shell redirection typo from `PyJWT>=2.8.0` commands | **Remove local file** | Low | Owner-approved delete; quote version specs in docs/commands. |
| Local browser/session exports `ham-default*` | Untracked files; local-noise audit indicates cookie/session-shaped content | **Remove securely** | High if committed/shared | Owner-approved secure delete; consider session rotation/log-out if ever shared. |
| Unrouted Builder Studio screen stack | Route redirects; active config lives in settings | **Remove only after product decision** | Medium | Confirm no near-term plan to revive route; then remove screen/tests. |
| Voice MVP legacy doc | Stale standalone deploy flow | **Archive/remove docs** | Medium | Move to `docs/archive/` or mark historical. |

## 7. What needs staged removal

| Item | Why staged | Recommendation | Stop condition |
|---|---|---|---|
| v1 Builder Kit fallback context | Still used whenever v2 flag/metadata/registry resolution fails | Stage a future migration: add non-v1 fallback for each app type, prove all live prompts route to v2 or safe default, then remove | Any failing flag-off or bad-registry tests |
| Coding Agents legacy adapters/labels | Possible unused launch/audit helpers, but need route/consumer proof | First run type-aware unused export/dependency check or remove behind small PRs | Any active settings/detail screen depends on labels/helpers |
| Builder Studio screen code | Route is redirected, but tests still assert screen route behavior | First decide product posture, then remove route tests/screen or mark historical | Owner wants future Builder Studio route |
| Old docs/checkpoints | Historical value but confusing as active state | Add index/current-state doc first; then archive/move misleading docs | A doc is referenced as canonical by AGENTS.md or STATUS.md |

## 8. What must stay until replacement coverage exists

| Item | Evidence | Why it must stay |
|---|---|---|
| `src/ham/builder_kits.py` + `src/ham/data/builder_kits/*.json` | Fallback path in `resolve_scaffold_context`; tests assert v1 output | Needed for flag-off / metadata-missing / v2-error behavior. |
| `src/ham/builder_kit_router.py` | Used by Builder Happy Path and provider launch enrichers to seed `template_kind` | Still feeds fallback and legacy kit selection. |
| `src/ham/build_registry/scaffold_context.py` fallback branches | Tests assert fallback reasons and v1 context | Needed for safe v2 rollout. |
| `ManagedProviderBuildApprovalPanel.tsx` and Droid/OpenCode wrappers | Tests assert digest/base revision/confirmed mechanics | Shared approval source of truth for managed lane. |
| Claude/Cursor separate provider surfaces | Docs note these are follow-up and not in shared managed approval lane | Removal would orphan active provider paths. |

## 9. Deployment/config cleanup recommendations

| Recommendation | Evidence | Risk | Next step |
|---|---|---|---|
| Make commit-tagged/digest deploy the default | Stale image incident; `scripts/deploy_ham_api_cloud_run.sh` supports mutable `:staging` and `SKIP_BUILD=1` | High | Update deploy script/runbook to default to `IMAGE_TAG=$(git rev-parse --short HEAD)` or digest update. |
| Add "do not deploy mock to staging/prod" guard | `docs/examples/ham-api-cloud-run-env.yaml` defaults to `HERMES_GATEWAY_MODE: mock` | High | Script guard: if project is staging/prod and env says mock, require explicit override. |
| Add pre/post deploy verification checklist | Recent need: verify image build time, flags, traffic, `HERMES_GATEWAY_MODE`, `HAM_BUILD_REGISTRY_V2_ENABLED` | Medium | Document commands in a current deploy state doc. |
| Replace hardcoded run.app URL literals or document staging-only coupling | `vercel.json`, `frontend/vercel.json`, older runbooks | Medium | Prefer lookup pattern via `gcloud run services describe`; if hardcoded, label as staging SOT. |
| Clarify Vercel same-origin rewrite model | Vercel configs proxy `/api/*`; docs still emphasize `VITE_HAM_API_BASE` | Medium | Update deploy docs: Vercel uses rewrites; env base is for local/alternate deployments. |

## 10. Docs cleanup recommendations

| Doc/path | Finding | Recommendation | Risk |
|---|---|---|---|
| `docs/build-kit-registry-v2/STATUS.md` | Useful current-ish status, but many historical docs nearby compete | Keep as current status; link to a new audit/current-state index | Low |
| `docs/build-kit-registry-v2/*CHECKPOINT*.md` | Historical snapshots can look actionable | Add `docs/build-kit-registry-v2/INDEX.md` or `CURRENT_STATE.md` marking historical vs active | Medium |
| `docs/DEPLOY_CLOUD_RUN.md` / `docs/DEPLOY_HANDOFF.md` | Valuable but needs stale-image and same-origin rewrite clarifications | Update | Medium |
| `docs/VOICE_MVP_README.md` | Legacy standalone deploy flow | Archive or mark historical | Medium |
| `src/ham/build_registry/__init__.py` and `scaffold_context.py` docstrings | "unwired" is now false | Update code comments in a small no-runtime-change PR | Medium |

## 11. Untracked local noise recommendations

| Path | Finding | Recommendation | Risk | Suggested next step |
|---|---|---|---|---|
| `.branch-audit/` | Local patch archive snapshots | Ignore or move outside repo | Low-medium | Add `.branch-audit/` to `.gitignore` after owner approval. |
| `.mission-notes/` | Local mission audit scratch docs | Investigate/promote useful notes; ignore scratch | Medium | Triage once, then add `.mission-notes/` to `.gitignore`. |
| `=2.8.0` | Stray empty artifact | Remove | Low | Owner-approved delete; add ignore if recurring. |
| `browser-harness/` | Local browser/runtime harness; referenced by lint baseline exclusions when present | Ignore local runtime | Medium-high | Add `browser-harness/` to `.gitignore`. |
| `canary/` | Pre-canary readiness artifact includes operational metadata | Investigate/archive sanitized evidence | Medium | Promote sanitized reports if useful; ignore `canary/`. |
| `ham-default`, `ham-default-2026-05-14` | Likely browser/session exports with cookies | Securely remove; ignore pattern | High | Owner-approved secure delete; add `ham-default*` to `.gitignore`. |

## 12. Proposed cleanup sequence

1. **Docs-only truth pass**
   - Add `docs/build-kit-registry-v2/CURRENT_STATE.md` or index.
   - Update deploy docs with immutable image/commit-tagged deploy and same-origin Vercel rewrite truth.
   - Mark historical checkpoints and `VOICE_MVP_README.md`.

2. **No-runtime comment cleanup**
   - Update stale "unwired" docstrings in `src/ham/build_registry/__init__.py` and `src/ham/build_registry/scaffold_context.py`.
   - Rename docs references to **v1 Builder Kit fallback context** where appropriate.

3. **Ignore/local hygiene PR**
   - Add approved local-noise patterns to `.gitignore`.
   - Do not delete high-risk local artifacts without explicit owner approval.

4. **Frontend surface pruning decision**
   - Decide Builder Studio route fate.
   - If retired, remove unrouted `BuilderStudioScreen` stack and route tests in a scoped PR.
   - Audit Coding Agents adapter/labels with type-aware tooling before deleting.

5. **Provider/IA consolidation**
   - Decide whether Tasks / Conductor / Operations / PlanCard remain distinct product lanes.
   - Only then remove or consolidate overlapping surfaces.

6. **Future v1 fallback retirement**
   - Not now.
   - Requires replacement fallback coverage, flag-off behavior decision, test migration, and owner approval.

## 13. Stop conditions / owner decisions needed

- Do not remove v1 Builder Kit fallback until owner approves losing or replacing flag-off / registry-error fallback behavior.
- Do not remove Builder Studio code until owner decides it will not return as a route.
- Do not remove Coding Agents helpers until a consumer/export audit proves they are unused.
- Do not delete local `ham-default*` without owner approval; treat as sensitive until inspected/secured.
- Do not change deploy script defaults without choosing immutable-image policy and mock-mode guard behavior.
- Do not archive checkpoint docs until a current-state/index doc exists.

