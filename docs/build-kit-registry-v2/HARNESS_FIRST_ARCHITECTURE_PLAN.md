# Harness-First Architecture Audit & Implementation Plan

Status:
- **Phase 1 (docs) shipped** — this plan (`a6176aea`).
- **Phase 2 (availability guard) shipped** — `1a085c50`: the chat hook stops
  silently scaffolding when a premium harness is *available* (transitional,
  availability-based — see the model correction below).
- **This revision corrects the model** from a "fallback hierarchy" to a
  **user-selected builder** model. No further code changed in this revision.

Baseline: `main`, repo `Code-Munkiz/ham`. All file/line references below were
read directly from the working tree (no assumed contents).

> ## Model correction (read first)
>
> **Product law: HAM uses the builder/harness selected by the user. There is no
> hidden fallback chain for normal builds.**
>
> Earlier drafts of this plan framed OpenCode and Hermes Agent as automatic
> "fallback rungs" below the premium harnesses. **That framing is wrong and is
> retired.** The corrected model:
>
> - Valid **user-selectable builders**: Cursor, Claude, OpenCode, Factory Droid,
>   **Hermes Agent** (a HAM-native builder).
> - A normal build prompt uses the **user-selected builder**.
> - If the user has **not** selected one, HAM may **default-select OpenCode only
>   if the product explicitly configures OpenCode as the default builder**;
>   otherwise HAM **asks the user to choose**.
> - The **internal scaffold is not a builder.** It is an **explicit Quick
>   Preview tool only** — never a silent default and never an automatic fallback.
>
> Sections below are written against this corrected model. The shipped Phase 2
> guard is an *availability-based* transitional step (it still allows the
> internal scaffold when no harness is available); converging it onto the
> selection-based model is the work described in §8 and the phases.

Scope: define how normal "build me X" prompts route to the **user-selected**
builder (Cursor / Claude / OpenCode / Factory Droid / Hermes Agent), how a
configured OpenCode default and an "ask the user to choose" path work, and how
the internal scaffold is confined to an explicit Quick Preview tool.

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

**Net (pre-Phase-2):** normal build requests silently used the internal scaffold
generator as the primary builder, violating the product law.

**Net (now, post-Phase-2 + corrected model):** Phase 2 stops the *silent
scaffold* when a premium harness is available, but it is availability-based, not
**selection**-based. Under the corrected product law the target is: a normal
build prompt routes to the **user-selected builder**; with no selection HAM
applies a configured OpenCode default or asks the user to choose; the internal
scaffold runs only on an explicit Quick Preview request. Selection-based routing
(§8) and Hermes-Agent-as-a-selectable-builder (§9) are not yet implemented.

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

## 3. Why the original default violates the product law

The product law is **user-selected builder** (no fallback chain):

- A normal build uses the **builder the user selected**: Cursor / Claude /
  OpenCode / Factory Droid / **Hermes Agent** (peers, not ranked rungs).
- No selection → a configured **OpenCode default** (if the product enables it),
  otherwise **ask the user to choose**.
- The internal scaffold is **not a builder** — Quick Preview only.

The original behavior violated this:

- **Internal scaffold ran unconditionally** for `build_or_create`, with no read
  of any selected builder and no "ask the user to choose" path.
- **The selectable builders were unreachable** from a plain "build me X" prompt —
  reachable only via the separate `CodingPlanCard` / managed-approval surface.
- **Hermes Agent was not a selectable new-build builder at all** (edit-only).

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
  over the Hermes gateway. It is a HAM-native builder **option** but is not yet
  wired as a selectable new-build builder and is not represented as a provider.

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

## 7. Required target architecture (user-selected builder)

A normal `build_or_create` turn resolves the **selected builder** — it does not
walk a fallback chain. Introduce a **builder-selection seam** that runs before
the internal scaffold is ever considered. It reads the workspace's selected
builder (a persisted preference), validates it against existing readiness, and
routes to that builder's existing launch path.

```
build_or_create intent (not an explicit Quick Preview request)
  └─ resolve_selected_builder(workspace_policy, readiness)
       ├─ a builder is selected  -> route to THAT builder's launch path
       │     {cursor | claude | opencode | factory_droid | hermes_agent}
       │     (existing preview/launch routes; existing approval/digest gates)
       │     if the selected builder is not ready -> tell the user how to enable it
       ├─ no builder selected, OpenCode configured as product default
       │                          -> select OpenCode
       └─ no builder selected, no configured default
                                  -> ASK the user to choose a builder
internal scaffold = ONLY reachable via an explicit Quick Preview request
```

There is **no** automatic "premium → OpenCode → Hermes → scaffold" cascade.
OpenCode and Hermes Agent are **peer selectable builders**, not fallback rungs.

Design constraints (must hold):

- Reuse the **existing** readiness/policy plumbing (`collate_readiness`,
  `WorkspaceAgentPolicy`). Persist the *selected builder* alongside the existing
  workspace coding-agent settings. Do not add a new orchestration framework
  (architecture contract: Hermes is sole supervisory orchestrator; no
  CrewAI/LangGraph).
- Reuse existing builder **preview/launch** routes and their approval/digest/
  token gates verbatim. Selection changes *who is chosen*, not *how a builder
  executes*. Do not fake a builder that is not wired (Hermes Agent new-build).
- The internal scaffold is **not a builder**. It is reachable only on an
  explicit Quick Preview request — never as a silent default and never as an
  automatic fallback when a selected/configured builder is missing.
- Preserve all safety invariants (kill switch, armed local control, deny-by-
  default, no build-kit internals in user copy, no secrets/env names in copy).

---

## 8. Builder selection resolution (no fallback chain)

For a normal build prompt, resolve in this order. This is **selection**
resolution, not a quality/fallback cascade:

1. **Explicit Quick Preview request** (e.g. "quick preview", "mockup",
   "wireframe") → run the **internal scaffold** (the only path that does).
2. **A builder is selected for this workspace** → route to that builder's
   existing launch path:
   - Cursor → `cursor_agent_workflow` / Cursor mission routes
   - Claude → `/api/claude-agent/build/*`
   - OpenCode → `/api/opencode/build/*`
   - Factory Droid → `/api/droid/build/*`
   - **Hermes Agent** → HAM-native builder (needs wiring — §9)
   If the selected builder is **not ready** (missing key/SDK/token/policy),
   HAM does **not** silently substitute another builder or the scaffold — it
   tells the user the selected builder needs enabling (safe, no internals) and
   how to fix or re-select.
3. **No builder selected, OpenCode configured as the product default builder**
   → select OpenCode (only when the product explicitly enables this default;
   see §"OpenCode default" in CURRENT_STATE.md).
4. **No builder selected, no configured default** → **ask the user to choose**
   a builder. Do **not** fall through to the internal scaffold.

The internal scaffold is never reached by (2)–(4); it is reached only by (1).
There is no "premium first, then OpenCode, then Hermes, then scaffold" ranking —
`WorkspaceAgentPolicy.preference_mode` remains a conductor-surface hint, not the
normal-build selector.

---

## 9. Hermes Agent as a selectable HAM-native builder

Hermes Agent is a **peer selectable builder** (alongside Cursor / Claude /
OpenCode / Factory Droid), **not** a fallback rung. Today it is only an
**edit-only** worker (`builder_edit_worker.py`, gateway) and is **not** a
coding-router provider, so it is **not yet selectable for new builds**. To make
it a real selectable builder:

1. **Represent it as a selectable builder.** Add a `hermes_agent` `ProviderKind`
   (or an explicit HAM-native builder id) in `src/ham/coding_router/types.py`,
   with a readiness probe in `coding_router/readiness.py` that reports available
   only when the Hermes gateway is live (mirror
   `builder_edit_worker._gateway_mode_allows_live_edit`). Keep it out of
   operator-secret signals; add an `allow_hermes_agent` policy flag.
2. **Add a new-build entry point.** Generalize `builder_edit_worker` (or add a
   thin sibling) so Hermes can produce a *new-build* file set, not only patches
   over an existing snapshot. Reuse the existing snapshot/import-job
   materialization and verifier so output is shaped like every other build.
3. **Make it selectable** in the same place the other builders are selected
   (the workspace coding-agent settings / `WorkspaceAgentPolicy` — see §7 and
   `CURRENT_STATE.md`). When chosen, the build routes to this Hermes builder
   path — exactly like choosing Cursor or OpenCode.
4. **Respect boundaries.** Hermes remains supervisory/critique elsewhere; this
   builder is a bounded execution path invoked through HAM, consistent with
   "CLI-first execution surface, one supervision vocabulary, many CLIs". Do not
   turn Hermes into a second general orchestrator.

Until (1)–(2) land, Hermes Agent must be presented honestly: a HAM-native
builder option that is **not yet wired for new builds**. Do **not** route
new-build prompts to it or imply it works before the entry point exists.

---

## 10. Internal scaffold = Quick Preview tool only (not a builder, not a fallback)

- The internal scaffold is **not a builder** and is **not an automatic
  fallback**. It runs **only** when the user explicitly asks for a Quick Preview
  / mockup.
- Gate `maybe_chat_scaffold_for_turn` so it is invoked only when the turn is an
  explicit Quick Preview request (e.g. a `operation="quick_preview"` / explicit
  preview flag threaded from `run_builder_happy_path_hook`). It must **not** run
  for a normal `build_or_create` turn, even when no builder is selected/ready —
  in that case HAM asks the user to choose (or applies a configured OpenCode
  default), it does not scaffold.
- Keep the retired deterministic template code dormant (do not revive); keep the
  scaffold's bounded-size + verifier guarantees.
- Do **not** delete the scaffold path — it remains the legitimate Quick Preview
  engine. (Consistent with the deprecation audit: "old deterministic scaffold
  runtime is retired" but the LLM scaffold is kept.)

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

**Phase 1 — Docs / model correction.** *(done — `a6176aea` + this revision)*
This plan + `CURRENT_STATE.md` state the corrected **user-selected builder**
model and the honest current state. No runtime change.

**Phase 2 — Stop the silent scaffold.** *(done — `1a085c50`)*
`run_builder_happy_path_hook` no longer silently scaffolds when a premium
harness is *available* (availability-based transitional guard via
`collate_readiness` + `WorkspaceAgentPolicy`). This is a stepping stone toward —
not the final shape of — selection-based routing.

**Phase 3 — Selected-builder preference + resolution (the corrected model).**
Add a persisted **selected builder** to the workspace coding-agent settings
(`WorkspaceAgentPolicy` + `coding_agent_access_settings` store). In the chat
hook, resolve per §8: selected builder → its launch path; no selection →
configured OpenCode default or **ask the user to choose**. No fallback chain.

**Phase 4 — OpenCode default switch.**
Add an explicit product config that makes OpenCode the default *selected*
builder when no user selection exists (off unless the product enables it). When
off, "no selection" → ask the user.

**Phase 5 — Wire Hermes Agent as a selectable builder.**
Add the `hermes_agent` builder id + readiness probe + new-build entry point
(§9), an `allow_hermes_agent` policy flag, and make it selectable like the
others. Until wired, present it honestly as "not yet available for new builds".

**Phase 6 — Confine the internal scaffold to Quick Preview.**
Thread an explicit Quick Preview operation/flag so `maybe_chat_scaffold_for_turn`
runs **only** on an explicit preview request, never as a normal-build default or
fallback. Apply the copy changes in §11.

**Phase 7 — Smoke-test each selectable builder.**
Per-builder smoke (preview→launch) for Cursor, Claude, OpenCode, Factory Droid,
Hermes Agent, plus the "ask to choose" path and Quick Preview.

---

## 13. Test plan

New / updated tests (no test is claimed to pass until actually run):

- **Selection-resolution unit tests** (`tests/` new): given a persisted
  selected builder + `WorkspaceAgentPolicy` + readiness, resolution returns:
  - a selected, ready builder → that builder's launch path;
  - a selected builder that is **not** ready → "enable it" prompt (no substitute);
  - no selection + OpenCode default configured → OpenCode;
  - no selection + no default → **ask the user to choose** (no scaffold);
  - explicit Quick Preview → internal scaffold even when a builder is selected.
- **Build-prompt routing tests**: a `build_or_create` prompt with a builder
  selected does **not** call `maybe_chat_scaffold_for_turn`; with no selection
  and no configured default it **asks the user** and still does **not** scaffold.
- **Hermes selection tests**: selecting Hermes Agent routes to the Hermes
  new-build entry point once wired; until then it is presented as not-yet-ready
  and never silently substituted.
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
- **"No selection" must not silently scaffold.** Under the corrected model, a
  user with no selected builder and no configured OpenCode default must be
  **asked to choose** — not handed a silent internal-scaffold preview. (The
  shipped Phase 2 guard is availability-based and still allows the scaffold when
  no harness is available; Phase 3/6 converge it onto ask-to-choose.)
- **Hermes scope creep.** Making Hermes a selectable builder risks blurring the
  supervisory/execution boundary. Keep it a bounded execution builder; do not
  add a second orchestrator (architecture + role-boundary rules).
- **Approval-lane coupling.** Droid/OpenCode share a managed approval lane;
  Claude/Cursor are separate. Routing a build to a builder must respect these
  existing surfaces, not bypass approval/digest gates.
- **Copy drift / internals leakage.** Builder names shown to users use approved
  product labels; never expose build-kit internals, provider ids, or env names
  (locked by existing token guards).
- **Minimal-diff rule.** Changes spanning >3 files need an impact map first
  (workspace rule). Selection resolution touches settings/policy + chat hook;
  sequence by phase to keep diffs reviewable.

Stop conditions:
- Stop if any builder preview/launch/approval/digest test would change behavior —
  selection changes *who is chosen*, not how a builder executes.
- Stop and get owner decisions on: (a) **where the selected-builder preference
  lives** (recommended: `WorkspaceAgentPolicy` + coding-agent-access-settings),
  (b) whether the **OpenCode default** is enabled, and (c) whether
  `update_existing_project` also becomes selection-routed.
- Stop before deleting the internal scaffold or the retired deterministic
  template code (deprecation audit: keep until owner OK).
- Do not route new-build prompts to Hermes Agent until §9 (1)–(2) are wired.

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
