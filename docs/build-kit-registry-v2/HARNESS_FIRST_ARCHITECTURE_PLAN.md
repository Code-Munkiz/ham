# Harness-First Architecture Audit & Implementation Plan

Status: **Audit + plan only. No code changed. No commit. No push.**

Baseline: `main`, repo `Code-Munkiz/ham`. All file/line references below were
read directly from the working tree during this audit (no assumed contents).

Scope: verify whether normal "build me X" prompts route to enabled premium
harnesses (Cursor / Claude / OpenCode / Factory Droid), fall back to **Hermes
Agent through HAM** when no premium harness is available, and demote the
internal scaffold generator to an explicit Quick Preview / fallback role.

---

## 1. Executive summary

**HAM is not harness-first today.** A normal build prompt
("build me a tetris game", "make a calculator app") does **not** consult the
enabled coding harnesses at all. It is intercepted by the **Builder Happy Path**
chat hook and turned into an **internal HAM scaffold** (a single OpenRouter LLM
call that emits files), materialized as a workspace snapshot, and shown as a
preview. The premium harness routes (Cursor, Claude Agent, OpenCode, Factory
Droid) exist and are well-gated, but they are reached only through **separate,
frontend-driven approval surfaces** — never from the default build prompt path.

Key facts established by this audit:

- The default build path is `run_builder_happy_path_hook` →
  `maybe_chat_scaffold_for_turn` → `_maybe_llm_scaffold_replace` →
  `generate_scaffold` (internal LLM scaffold). It runs **first** in both
  `POST /api/chat` and `POST /api/chat/stream` and short-circuits the rest of
  the dispatcher when intent is `build_or_create`.
- The legacy *deterministic* templates (calculator/tetris) are retired at
  runtime; the scaffold is now an **internal LLM scaffold generator**. That is
  still **internal scaffold generation**, not a harness, and not Hermes Agent.
- The harness routes are real and gated, but they are **not** invoked by the
  build prompt path. They are invoked by `CodingPlanCard` / the right-pane
  managed approval mount (Droid + OpenCode only) and by operator/Cursor flows.
- The conductor (`POST /api/coding/conductor/preview`) is **preview-only**
  (it explicitly never launches) and is **not consulted** by the scaffold path.
- **Hermes Agent is not a build harness today.** It is used only as an *edit*
  worker for `update_existing_project` follow-ups via the Hermes gateway
  (`builder_edit_worker.py`), and it is **absent from the coding-router
  provider set** entirely (no `hermes` `ProviderKind`).

**Net:** the product invariant — "normal build requests must not silently use
the internal scaffold generator as the primary builder" — is currently
violated. The internal scaffold *is* the primary builder for new builds.

---

## 2. Current actual default build path

For a new "build me X" prompt with a resolved workspace + project:

```
POST /api/chat  (or /api/chat/stream)
  src/api/chat.py:1841 / :2054
    run_builder_happy_path_hook(...)                 src/ham/builder_chat_hooks.py:376
      classify_builder_chat_intent -> "build_or_create"
      maybe_chat_scaffold_for_turn(...)              src/ham/builder_chat_scaffold.py:1739
        _bounded_files(...) -> placeholder_fallback (deterministic templates retired)
        _maybe_llm_scaffold_replace(...)             src/ham/builder_chat_scaffold.py:1604
          generate_scaffold(synthetic_plan, ...)     src/ham/builder_llm_scaffold.py:342
            complete_chat_messages_openrouter(...)    # ONE internal LLM call (BYO OpenRouter)
        verify_builder_scaffold_artifact(...)
        materialize_inline_files_as_zip_artifact(...) # snapshot + ProjectSource + ImportJob
      maybe_enqueue_chat_scaffold_cloud_runtime_job(...)  # preview env
  -> chat replies "I'll create ... and prepare the Workbench"
  -> right-pane preview shows the scaffolded app
```

When `build_or_create` fires, the dispatcher gates **off** the operator path
(`chat.py:1913-1917`: operator turn only runs when `builder_intent != "build_or_create"`),
so no harness selection or conductor consultation happens on that turn.

Failure modes the path already emits (none of which are "use a harness"):
- `model_access_required` → "Connect OpenRouter in Settings" (no OpenRouter key).
- `llm_scaffold_failed` → "selected scaffold model is unavailable / call failed".
- `artifact_verification_failed` → "I couldn't build that yet".

So even the *fallback* of the internal scaffold is "ask for an OpenRouter key",
not "escalate to a premium harness or Hermes Agent".

---

## 3. Why the current default violates the product invariant

The product hierarchy is:

1. premium harness (Cursor / Claude / OpenCode / Factory Droid)
2. Hermes Agent through HAM (fallback builder)
3. internal scaffold (quick preview / mockup / explicit / emergency only)

Current behavior inverts this:

- **Internal scaffold is rung 1** for new builds. It is selected
  unconditionally for `build_or_create`, with no check of which harnesses are
  enabled, no `preferred_harness`, and no escalation rule.
- **Premium harnesses are effectively rung 3** — reachable only if the user
  navigates the separate `CodingPlanCard` / managed-approval surface, which is
  not what a plain "build me X" prompt triggers.
- **Hermes Agent is not in the build hierarchy at all** for new builds (it only
  edits existing project sources).

The internal scaffold being an LLM call rather than a deterministic template
does **not** satisfy the invariant — it is still HAM's internal generator, not a
harness and not Hermes Agent.

---

## 4. Harness inventory

| Harness | Detection (host/workspace) | Real build route(s) | Invoked by build prompt today? | Notes |
|---|---|---|---|---|
| **Cursor** | `get_effective_cursor_api_key()` (UI or `CURSOR_API_KEY`); `coding_router/readiness.py:_cursor_team_key_configured` | `src/ham/cursor_agent_workflow.py` (`build_cursor_agent_preview` / `run_cursor_agent_launch`) + Cursor mission routes / SDK bridge | **No** | Repo/PR + managed-mission flows. Separate surface. |
| **Claude** | `claude_code` is **always blocked** (`readiness.py:_build_claude_readiness`, status "planned"). `claude_agent` = SDK installed + Anthropic/Bedrock/Vertex auth (`worker_adapters/claude_agent_adapter`) | `src/api/claude_agent_build.py` (`/api/claude-agent/build/preview|launch`), gated by `CLAUDE_AGENT_ENABLED` + SDK + auth + exec token | **No** | Managed-workspace snapshot edits. Not on `CodingPlanCard`. |
| **OpenCode** | `HAM_OPENCODE_ENABLED` + `HAM_OPENCODE_EXECUTION_ENABLED` + readiness `CONFIGURED` + managed-workspace + `HAM_OPENCODE_EXEC_TOKEN` | `src/api/opencode_build.py` (`/api/opencode/build/preview|launch`) | **No** (reachable via `CodingPlanCard` managed approval) | Managed snapshot. Shares approval lane with Droid. |
| **Factory Droid** | `_droid_runner_kind()` (remote URL+token or local `droid`) + `safe_edit_low` workflow registered + `HAM_DROID_EXEC_TOKEN` | `src/api/droid_build.py` (`/api/droid/build/preview|launch`) | **No** (reachable via `CodingPlanCard` managed approval) | github_pr or managed snapshot. |
| **Hermes Agent** | **Not a coding-router provider.** Only the Hermes *gateway* mode (`builder_edit_worker._gateway_mode_allows_live_edit`, not `mock`) | None for *new builds*. `builder_edit_worker.run_builder_edit_worker_maybe` (edits to existing snapshots only) | **No** | Edit-only worker; no `ProviderKind`, no build-fallback wiring. |
| **Internal scaffold** | Always "available" when an OpenRouter key resolves | `builder_chat_scaffold.maybe_chat_scaffold_for_turn` → `builder_llm_scaffold.generate_scaffold` | **Yes — default** | The current de-facto primary builder. |

---

## 5. Which paths are real build harnesses

Real external/agentic build harnesses (execute against a workspace/repo, gated,
auditable, produce a reviewable result):

- **Cursor** — `src/ham/cursor_agent_workflow.py` (+ Cursor mission / SDK bridge).
- **Claude Agent** — `src/api/claude_agent_build.py` + `src/ham/claude_agent_runner.py`.
- **OpenCode** — `src/api/opencode_build.py` + `src/ham/opencode_runner.py`.
- **Factory Droid** — `src/api/droid_build.py` + `src/ham/droid_workflows/*`,
  `src/ham/droid_runner/*`.

Conditional / partial:

- **Hermes Agent** — only as an **edit** worker (`src/ham/builder_edit_worker.py`)
  over the Hermes gateway. It is a candidate fallback *builder* but is not wired
  as one and is not represented as a harness.

---

## 6. Which paths are only preview / scaffold generation

- **Internal scaffold** — `src/ham/builder_chat_scaffold.py` +
  `src/ham/builder_llm_scaffold.py`. Emits files via one LLM call, snapshots
  them, and renders a preview. No repo execution, no agent loop, no approval.
- **`builder_chat_scaffold.py` deterministic template helpers**
  (`_build_tetris_scaffold_files`, `_calculator_app_tsx`, etc.) — **retired at
  runtime** (guarded by `use_tetris_template = False` /
  `use_calculator_template = False`), retained only as dormant code + utilities.
- **Conductor preview** — `src/api/coding_conductor.py` is explicitly
  preview/recommendation-only ("It does not launch any provider").

---

## 7. Required target architecture

Introduce an explicit **harness resolution seam** that runs for
`build_or_create` (and ideally `update_existing_project`) **before** the
internal scaffold is selected. The seam consumes the existing readiness snapshot
(`coding_router.collate_readiness`) plus workspace policy, and returns the
build executor to use.

```
build_or_create intent
  └─ resolve_build_harness(prompt, project, workspace_policy, readiness)
       ├─ premium harness enabled & eligible?  -> route to that harness
       │     order: Cursor | Claude | OpenCode | Factory Droid
       │     (existing preview/launch routes; existing approval/digest gates)
       ├─ else Hermes Agent available (gateway live)?  -> Hermes build fallback
       └─ else  -> internal scaffold  (explicit Quick Preview / emergency)
```

Design constraints (must hold):

- Reuse the **existing** provider readiness + policy plumbing
  (`collate_readiness`, `WorkspaceAgentPolicy`, `recommend`). Do not add a new
  orchestration framework (architecture contract: Hermes is sole supervisory
  orchestrator; no CrewAI/LangGraph).
- Reuse existing harness **preview/launch** routes and their approval/digest/
  token gates verbatim. Harness-first changes *who is chosen*, not *how a
  harness executes*.
- Keep the internal scaffold reachable on an **explicit** path (Quick Preview
  toggle / `preview` operation) and as the **last-resort** fallback.
- Preserve all safety invariants (kill switch, armed local control, deny-by-
  default, no build-kit internals in user copy, no secrets/env names in copy).

---

## 8. Proposed routing order

For a normal build prompt:

1. **Explicit user override** — if the user selected a specific harness or
   "Quick Preview", honor it (Quick Preview → internal scaffold; named harness →
   that harness if eligible, else surface its blocker).
2. **Premium harness, in priority order, first eligible wins:**
   1. **Cursor** (`cursor_cloud` available + repo/target satisfied)
   2. **Claude** (`claude_agent` enabled + SDK + auth + managed-workspace)
   3. **OpenCode** (`opencode_cli` enabled + execution + token + managed-workspace)
   4. **Factory Droid** (`factory_droid_build` runner + token + target satisfied)
   - Exact order is a product decision; default to the list above and allow
     `WorkspaceAgentPolicy.preference_mode` to reorder among **eligible**
     harnesses (it already boosts `cursor_cloud` / `claude_agent` / `opencode_cli`).
3. **Hermes Agent fallback** — if no premium harness is eligible but the Hermes
   gateway is live (non-mock), route the build to a Hermes Agent builder.
4. **Internal scaffold** — only if (2) and (3) are unavailable, or the user
   explicitly chose Quick Preview. Treated as emergency/preview, with copy that
   says "preview", not "build".

Eligibility never bypasses a harness's own blockers — a blocked harness is
skipped (and may be surfaced as "blocked because…"), exactly like the conductor
already does in `recommend` / `_pick_chosen`.

---

## 9. Hermes Agent fallback design

Today Hermes Agent is an **edit-only** worker and is not a coding-router
provider. To make it a true fallback **builder**:

1. **Represent it as a provider.** Add a `hermes_agent` `ProviderKind` (or an
   explicit "hermes build fallback" capability) in
   `src/ham/coding_router/types.py`, with a readiness probe in
   `coding_router/readiness.py` that returns available only when the Hermes
   gateway is live (mirror `builder_edit_worker._gateway_mode_allows_live_edit`).
   Keep it **out** of operator-secret signals.
2. **Add a build entry point.** Generalize `builder_edit_worker` (or add a thin
   sibling) so Hermes can produce a *new-build* file set, not only patches over
   an existing snapshot. Reuse the existing snapshot/import-job materialization
   and verifier so the output is shaped like every other build.
3. **Wire it as the fallback rung** in `resolve_build_harness` (step 3 of §8):
   chosen only when no premium harness is eligible and the gateway is live.
4. **Respect boundaries.** Hermes remains supervisory/critique elsewhere; this
   fallback is a bounded execution path invoked through HAM, consistent with
   "CLI-first execution surface, one supervision vocabulary, many CLIs". Do not
   turn Hermes into a second general orchestrator.

Until (1)–(3) land, the honest fallback is: premium harness → (no Hermes build)
→ internal scaffold. The plan should not claim Hermes fallback exists before it
is wired.

---

## 10. Internal scaffold demotion plan

- Gate `maybe_chat_scaffold_for_turn` so it is selected only when:
  (a) the resolver chose `internal_scaffold`, **or**
  (b) the user explicitly requested Quick Preview / mockup, **or**
  (c) emergency fallback (no premium harness, no Hermes gateway).
- Add an explicit **operation/mode** (e.g. `operation="quick_preview"` or a
  `preview_mode` flag threaded from `run_builder_happy_path_hook`) so the
  scaffold path is opt-in, not the silent default for `build_or_create`.
- Keep the retired deterministic template code dormant (do not revive); keep the
  scaffold's bounded-size + verifier guarantees.
- Do **not** delete the scaffold path — it remains the legitimate Quick Preview
  engine and the emergency fallback. (Consistent with the deprecation audit:
  "old deterministic scaffold runtime is retired" but the LLM scaffold is kept.)

---

## 11. User-facing copy changes required

Today copy says "build" / "create … project" for what is a scaffold preview.
When the work is internal-scaffold-only, copy should say "preview" / "mockup".

Backend copy (`src/ham/builder_chat_hooks.py`):
- `_builder_ack_prefix` — "I'll create a … project and prepare the Workbench."
  → for Quick Preview: "I'll generate a quick preview …".
- `_model_access_required_message` — "I cannot build this without model access" →
  scope to preview when on the scaffold rung.

Frontend copy (`.../coding-plan/codingPlanCardCopy.ts`):
- `BUILD_GENERATION_GENERATING_POINTER` "I'm generating the first version …" and
  related `BUILD_GENERATION_*` pointers — relabel as "preview" when the work is
  internal scaffold, not a harness build.
- `BUILD_GENERATION_INTERRUPTED_TOAST` "HAM is still building your app …" →
  "HAM is still preparing your preview …" on the scaffold rung.
- Harness builds keep "build" language (they are real builds).

The line between "build" and "preview" copy must be driven by the chosen rung
(harness/Hermes = "build"; internal scaffold = "preview"), not hardcoded.

---

## 12. Implementation phases

**Phase 1 — Docs / current-state correction.**
Update `docs/build-kit-registry-v2/CURRENT_STATE.md` and the deprecation audit
to state plainly that the Builder Happy Path internal scaffold is the *current
default builder for new build prompts*, that this violates the harness-first
invariant, and that harness selection is not yet wired into the build prompt
path. (This file is part of Phase 1.) No runtime change.

**Phase 2 — Block silent scaffold default when harnesses are enabled.**
In `run_builder_happy_path_hook` / `maybe_chat_scaffold_for_turn`, when
`build_or_create` and at least one premium harness is eligible (via
`collate_readiness` + policy), do **not** auto-run the internal scaffold.
Instead surface the harness-first decision (route to harness or present the
harness as the build path). Smallest correct change: add the resolver gate
before `maybe_chat_scaffold_for_turn` is called.

**Phase 3 — Harness selection / default-harness resolution.**
Add `resolve_build_harness(...)` consuming the existing readiness snapshot +
`WorkspaceAgentPolicy` and returning the chosen rung (premium harness → Hermes →
internal). Reuse `recommend`/`_pick_chosen` ordering semantics; add
`preferred_harness` / Quick Preview override handling.

**Phase 4 — Wire Hermes Agent fallback.**
Add the `hermes_agent` provider + readiness probe + new-build entry point
(§9) and slot it as rung 3.

**Phase 5 — Relabel scaffold as Quick Preview only.**
Add the explicit Quick Preview operation/flag, demote
`maybe_chat_scaffold_for_turn` to that mode + emergency fallback, and apply the
copy changes in §11.

**Phase 6 — Smoke-test each harness.**
Per-harness smoke (preview→launch) for Cursor, Claude Agent, OpenCode, Factory
Droid, plus Hermes fallback and Quick Preview, asserting the resolver picks the
right rung given enabled/disabled states.

---

## 13. Test plan

New / updated tests (no test is claimed to pass until actually run):

- **Resolver unit tests** (`tests/` new): given a `WorkspaceReadiness` +
  `WorkspaceAgentPolicy`, `resolve_build_harness` returns the correct rung:
  - premium enabled → that harness (and respects priority/preference order);
  - none premium + gateway live → `hermes_agent`;
  - nothing available → `internal_scaffold`;
  - explicit Quick Preview → `internal_scaffold` even when harnesses enabled.
- **Build-prompt routing tests**: a `build_or_create` prompt with a harness
  enabled does **not** call `maybe_chat_scaffold_for_turn` (assert via patch/
  spy on `src/ham/builder_chat_scaffold.maybe_chat_scaffold_for_turn`); with no
  harness + no gateway, it **does** (emergency fallback).
- **Hermes fallback tests**: gateway live + no premium harness → Hermes build
  entry point invoked; gateway mock → falls through to internal scaffold.
- **Copy tests** (frontend Vitest + backend): scaffold rung renders "preview"
  copy; harness rung renders "build" copy; `FORBIDDEN_CARD_TOKENS` /
  build-registry-v2 forbidden tokens still never leak.
- **Regression guard**: existing harness preview/launch + approval/digest tests
  (`tests/test_*droid*`, opencode, claude_agent, cursor) stay green —
  harness-first must not change harness execution mechanics.
- Run scoped: `python -m pytest tests/ -q` for touched areas, plus
  `npm run lint && npm test` in `frontend/` for copy/card changes.

---

## 14. Risks and stop conditions

Risks:
- **Behavioral regression for users with no harness configured.** If Phase 2
  lands before Phase 4/5, users with no premium harness and a mock gateway must
  still get *something* — keep the internal scaffold as emergency fallback so we
  don't strand them.
- **Hermes scope creep.** Wiring Hermes as a builder risks blurring the
  supervisory/execution boundary. Keep it a bounded execution fallback; do not
  add a second orchestrator (architecture + role-boundary rules).
- **Approval-lane coupling.** Droid/OpenCode share a managed approval lane;
  Claude/Cursor are separate. Routing a build prompt to a harness must respect
  these existing surfaces, not bypass approval/digest gates.
- **Copy drift / internals leakage.** Relabeling must not expose build-kit
  internals, provider ids, or env names (locked by existing token guards).
- **Minimal-diff rule.** Changes spanning >3 files need an impact map first
  (workspace rule). The resolver touches chat hooks + scaffold + coding_router +
  copy; sequence by phase to keep diffs reviewable.

Stop conditions:
- Stop if any harness preview/launch/approval/digest test would change behavior —
  harness-first must not alter harness execution contracts.
- Stop and get owner decision on the **priority order** among premium harnesses
  and on whether `update_existing_project` should also become harness-first.
- Stop before deleting the internal scaffold or the retired deterministic
  template code (deprecation audit: keep until replacement coverage + owner OK).
- Do not claim Hermes fallback is live until §9 (1)–(3) are actually wired.

---

## Appendix — primary evidence (files read)

- `src/ham/builder_chat_scaffold.py` (scaffold entry, `maybe_chat_scaffold_for_turn`, `_maybe_llm_scaffold_replace`)
- `src/ham/builder_llm_scaffold.py` (`generate_scaffold`, single OpenRouter call)
- `src/ham/builder_chat_hooks.py` (`run_builder_happy_path_hook`, build/edit branching, ack copy)
- `src/ham/builder_edit_worker.py` (Hermes gateway edit worker — edits only)
- `src/api/chat.py` (dispatch order; build_or_create gates off operator path)
- `src/api/coding_conductor.py` (preview-only; no launch)
- `src/ham/coding_router/readiness.py` (harness detection)
- `src/ham/coding_router/recommend.py` (provider ordering/preference; no `hermes`)
- `src/api/droid_build.py`, `src/api/opencode_build.py`, `src/api/claude_agent_build.py`, `src/ham/cursor_agent_workflow.py` (real harness routes, gated, not invoked by build prompt)
- `frontend/.../coding-plan/codingPlanCardCopy.ts` (build-vs-preview copy; two lanes)
- `docs/build-kit-registry-v2/CURRENT_STATE.md`, `HAM_LEGACY_DEPRECATION_AUDIT.md`, `RIGHT_PANE_APPROVAL_STATUS_COMPLETION_CHECKPOINT.md`
