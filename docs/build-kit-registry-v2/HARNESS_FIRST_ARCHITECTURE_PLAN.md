# Harness-First Architecture Audit & Implementation Plan

Status:
- **Phase 1 (docs) shipped** — this plan (`a6176aea`).
- **Phase 2 (availability guard) shipped** — `1a085c50`.
- **Current:** normal build turns no longer use the old internal scaffold as the
  user-facing builder. No selected external harness routes to HAM Native Builder
  through Hermes, or returns "HAM Native Builder is not ready yet" when the live
  gateway path is unavailable.

Baseline: `main`, repo `Code-Munkiz/ham`. All file/line references below were
read directly from the working tree (no assumed contents).

> ## Model correction (read first)
>
> **Product law: HAM/Hermes is always the agent the user talks to. External
> builder selection chooses only the execution harness HAM routes work through.**
>
> Earlier drafts of this plan framed OpenCode and Hermes Agent as automatic
> "fallback rungs" below the premium harnesses. **That framing is wrong and is
> retired.** The corrected model:
>
> - Valid external builders in Settings → Builders: Cursor, Claude, OpenCode,
>   Factory Droid.
> - A normal build prompt uses HAM/Hermes orchestration and, when selected,
>   routes execution through the chosen external harness.
> - If the user has **not** selected an external builder, the UI represents
>   native HAM/Hermes mode: "No external builder selected — HAM will build
>   natively."
> - OpenCode is an optional free external builder, not the conceptual default.
>   `HAM_DEFAULT_BUILDER=opencode` is a deployment override for OpenCode-first
>   environments, not the product model.
> - The **old internal scaffold is not a builder.** It is not used for normal
>   user builds, and Quick Preview routes through HAM Native/Hermes unless an
>   internal development flag explicitly enables the legacy preview scaffold.
>
> Sections below are written against this corrected model. The shipped Phase 2
> guard is an *availability-based* transitional step (it still allows the
> internal scaffold when no harness is available); converging it onto the
> selection-based model is the work described in §8 and the phases.

Scope: define how normal "build me X" prompts keep HAM/Hermes as the always-on
orchestrator, optionally route execution through an external harness
(Cursor / Claude / OpenCode / Factory Droid), and confine the internal scaffold
to an explicit Quick Preview tool.

---

## 1. Executive summary

HAM/Hermes is now the center of the build conversation. A normal build prompt
resolves an optional external execution harness (Cursor, Claude, OpenCode,
Factory Droid). If none is selected, HAM routes to HAM Native Builder through
Hermes. The old internal scaffold path is no longer the user-facing product
builder.

Key facts established by this audit:

- The default build path is `run_builder_happy_path_hook` →
  selected external harness / explicit deployment default / `run_hermes_native_build`.
  It runs first in both `POST /api/chat` and `POST /api/chat/stream` and
  short-circuits the rest of the dispatcher when intent is `build_or_create`.
- The legacy *deterministic* templates (calculator/tetris) are retired at
  runtime; the scaffold is now an **internal LLM scaffold generator**. That is
  still **internal scaffold generation**, not a harness, and not Hermes Agent.
- The harness routes are real and gated, but they are **not** invoked by the
  build prompt path. They are invoked by `CodingPlanCard` / the right-pane
  managed approval mount (Droid + OpenCode only) and by operator/Cursor flows.
- The conductor (`POST /api/coding/conductor/preview`) is **preview-only**
  (it explicitly never launches) and is **not consulted** by the scaffold path.
- HAM Native Builder now has a bounded Hermes gateway new-build entry point that
  can create Workbench source snapshots when the gateway is live. Hermes remains
  the orchestrator/native path, not a selectable Settings row and not a coding
  router provider.

**Net now:** normal build requests no longer silently use the internal scaffold.
They use the selected external harness, an explicit deployment default such as
temporary `HAM_DEFAULT_BUILDER=opencode`, or HAM Native Builder through Hermes.
If native mode is not ready on a host, HAM says so honestly.

---

## 2. Current actual default build path

For a new "build me X" prompt with a resolved workspace + project:

```
POST /api/chat  (or /api/chat/stream)
  src/api/chat.py:1841 / :2054
    run_builder_happy_path_hook(...)
      classify_builder_chat_intent -> "build_or_create"
      selected external builder?
        OpenCode / Factory Droid -> managed approval handoff
        Cursor / Claude -> separate-flow copy
      no selection/default -> run_hermes_native_build(...)
        complete_chat_turn(...) via Hermes gateway
        validate bounded file bundle
        ProjectSource + SourceSnapshot + ImportJob
        maybe_enqueue_chat_scaffold_cloud_runtime_job(...)
  -> chat replies that HAM is building natively, or honestly says native is not ready
  -> right-pane preview shows the generated snapshot when available
```

When `build_or_create` fires, the dispatcher gates **off** the operator path
(`chat.py:1913-1917`: operator turn only runs when `builder_intent != "build_or_create"`),
so no harness selection or conductor consultation happens on that turn.

Failure modes stay user-safe:
- native gateway unavailable → "HAM Native Builder is not ready yet."
- selected external harness not ready → safe setup copy.
- generated bundle invalid → safe failure metadata, no internal details.

So even the *fallback* of the internal scaffold is "ask for an OpenRouter key",
not "escalate to a premium harness or Hermes Agent".

---

## 3. Why the original default violates the product law

The product law is **HAM/Hermes orchestrates; external selection chooses the
execution harness**:

- A normal build uses HAM/Hermes as the agent and routes through the selected
  external harness when one is selected: Cursor / Claude / OpenCode /
  Factory Droid.
- No external selection → native HAM/Hermes mode. This requires a real native
  HAM/Hermes new-build implementation before it can be the honest default.
- `HAM_DEFAULT_BUILDER=opencode` is an explicit deployment override, not the
  conceptual product default.
- The internal scaffold is **not a builder** — Quick Preview only.

The original behavior violated this:

- **Internal scaffold used to run unconditionally** for `build_or_create`; this
  is now removed from normal user build flow.
- **The external builders used to be unreachable** from plain build prompts;
  OpenCode and Factory Droid now hand off to their managed approval surfaces
  when selected and ready.
- **Native HAM/Hermes new-build mode is now bounded and gateway-backed**, with
  honest unavailable copy when host configuration cannot run it.

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
| **HAM/Hermes native** | Always-on orchestration; live Hermes gateway required for execution | `src/ham/builder_native_hermes.py` new-build snapshot path; `builder_edit_worker.py` for existing snapshot edits | **Yes, when no external builder/default is selected** | Not a Settings builder row. If gateway is unavailable, HAM says native builder is not ready. |
| **Old internal scaffold** | Internal dev flag only for Quick Preview | `builder_chat_scaffold.maybe_chat_scaffold_for_turn` → `builder_llm_scaffold.generate_scaffold` | **No** | Retained for dev/legacy utility only; not the product builder. |

---

## 5. Which paths are real build harnesses

Real external/agentic build harnesses (execute against a workspace/repo, gated,
auditable, produce a reviewable result):

- **Cursor** — `src/ham/cursor_agent_workflow.py` (+ Cursor mission / SDK bridge).
- **Claude Agent** — `src/api/claude_agent_build.py` + `src/ham/claude_agent_runner.py`.
- **OpenCode** — `src/api/opencode_build.py` + `src/ham/opencode_runner.py`.
- **Factory Droid** — `src/api/droid_build.py` + `src/ham/droid_workflows/*`,
  `src/ham/droid_runner/*`.

Native / partial:

- **HAM/Hermes** — always-on orchestration. Hermes gateway support is currently
  only an **edit** worker (`src/ham/builder_edit_worker.py`) over existing
  snapshots. A true native HAM/Hermes new-build path still needs wiring before
  no-external-builder mode can honestly build natively.

---

## 6. Which paths are only preview / scaffold generation

- **Old internal scaffold** — `src/ham/builder_chat_scaffold.py` +
  `src/ham/builder_llm_scaffold.py`. Retained for legacy/dev utility and tests;
  not used for normal user builds and not a substitute for HAM Native Builder.
- **`builder_chat_scaffold.py` deterministic template helpers**
  (`_build_tetris_scaffold_files`, `_calculator_app_tsx`, etc.) — **retired at
  runtime** (guarded by `use_tetris_template = False` /
  `use_calculator_template = False`), retained only as dormant code + utilities.
- **Conductor preview** — `src/api/coding_conductor.py` is explicitly
  preview/recommendation-only ("It does not launch any provider").

---

## 7. Required target architecture (external builder selection)

A normal `build_or_create` turn keeps HAM/Hermes as the orchestrator and
resolves an optional **external execution harness** — it does not walk a fallback
chain. Introduce a harness-selection seam that runs before the internal scaffold
is ever considered. It reads the workspace's selected external builder (a
persisted preference), validates it against existing readiness, and routes to
that harness's existing launch path.

```
build_or_create intent (not an explicit Quick Preview request)
  └─ resolve_external_builder(workspace_policy, readiness)
       ├─ external builder selected -> route through THAT harness
       │     {cursor | claude | opencode | factory_droid}
       │     (existing preview/launch routes; existing approval/digest gates)
       │     if the selected harness is not ready -> tell the user how to enable it
       ├─ no external builder selected + deployment default configured
       │                          -> route through that explicit deployment default
       └─ no external builder selected, no configured default
                                  -> native HAM/Hermes new-build path
internal scaffold = ONLY reachable via an explicit Quick Preview request
```

There is **no** automatic "premium → OpenCode → Hermes → scaffold" cascade.
OpenCode is an external harness, not a fallback rung; HAM/Hermes is the
always-on orchestrator, not a selectable row.

Design constraints (must hold):

- Reuse the **existing** readiness/policy plumbing (`collate_readiness`,
  `WorkspaceAgentPolicy`). Persist the *selected builder* alongside the existing
  workspace coding-agent settings. Do not add a new orchestration framework
  (architecture contract: Hermes is sole supervisory orchestrator; no
  CrewAI/LangGraph).
- Reuse existing builder **preview/launch** routes and their approval/digest/
  token gates verbatim. External selection changes *which harness is chosen*,
  not *how a builder executes*. Do not fake native HAM/Hermes new-build support
  before it is wired.
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
   "wireframe") → route through HAM Native/Hermes or return the honest native
   unavailable copy. The old internal scaffold requires an internal dev flag.
2. **An external builder is selected for this workspace** → route through that
   harness's existing launch path:
   - Cursor → `cursor_agent_workflow` / Cursor mission routes
   - Claude → `/api/claude-agent/build/*`
   - OpenCode → `/api/opencode/build/*`
   - Factory Droid → `/api/droid/build/*`
   If the selected external builder is **not ready** (missing key/SDK/token/policy),
   HAM does **not** silently substitute another builder or the scaffold — it
   tells the user the selected builder needs enabling (safe, no internals) and
   how to fix or re-select.
3. **No external builder selected, deployment default configured** → route
   through that explicit default (for example staging may use
   `HAM_DEFAULT_BUILDER=opencode`). This should be treated as an environment
   override, not the product concept.
4. **No external builder selected, no configured default** → native HAM/Hermes
   new-build path. If the gateway-backed path is unavailable on the host, say
   "HAM Native Builder is not ready yet" and do **not** fall through to the old
   scaffold.

The internal scaffold is never reached by (2)–(4); it is reached only by (1).
There is no "premium first, then OpenCode, then Hermes, then scaffold" ranking —
`WorkspaceAgentPolicy.preference_mode` remains a conductor-surface hint, not the
normal-build selector.

---

## 9. Native HAM/Hermes builder gap

HAM/Hermes is **always** the orchestration layer. It does not appear as a
selectable builder row next to external harnesses. Native new-build support now
exists as a bounded gateway-backed source snapshot path:

1. **Native new-build entry point.** `builder_native_hermes.py` asks the Hermes
   gateway for structured full-file JSON, validates paths/content, writes
   `ProjectSource` + `SourceSnapshot` + `ImportJob`, and enqueues the existing
   Workbench preview job when available.
2. **Readiness and honest copy.** Native mode reports unavailable until a live
   gateway route is configured. User copy does not expose env names or internals.
3. **Boundaries.** Hermes remains the orchestrator/native builder path, not a
   selectable external harness and not a second third-party orchestration
   framework.

Do **not** route native new-build prompts to the old internal scaffold when the
gateway-backed path is unavailable.

---

## 10. Internal scaffold = Quick Preview tool only (not a builder, not a fallback)

- The old internal scaffold is **not a builder** and is **not an automatic
  fallback**. Normal user builds do not invoke it.
- `maybe_chat_scaffold_for_turn` is not invoked for a normal `build_or_create`
  turn, even when no external builder is selected/ready. Quick Preview also
  routes through HAM Native/Hermes by default; the old scaffold requires an
  internal dev flag.
- Keep the retired deterministic template code dormant (do not revive); keep the
  scaffold's bounded-size + verifier guarantees while legacy callers remain.
- Do **not** expose the scaffold path as a product builder.

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

**Phase 3 — External-builder preference + resolution (the corrected model).**
Add a persisted **external builder** to the workspace coding-agent settings
(`WorkspaceAgentPolicy` + `coding_agent_access_settings` store). In the chat
hook, resolve per §8: selected external builder → its harness path; no external
selection → explicit deployment default or native HAM/Hermes mode. No fallback
chain.

**Phase 4 — OpenCode default switch.**
Treat `HAM_DEFAULT_BUILDER=opencode` as an explicit deployment override that
routes no-external-builder work through OpenCode. Remove it from production
deployments where native HAM/Hermes mode is intended.

**Phase 5 — Wire native HAM/Hermes builds.**
Implement the native HAM/Hermes new-build path (§9). Hermes/HAM is not a
selectable row; it is the always-on orchestrator. Until native build is wired,
present the gap honestly and do not substitute the internal scaffold.

**Phase 6 — Confine the internal scaffold to Quick Preview.**
Thread an explicit Quick Preview operation/flag so `maybe_chat_scaffold_for_turn`
runs **only** on an explicit preview request, never as a normal-build default or
fallback. Apply the copy changes in §11.

**Phase 7 — Smoke-test each external builder plus native mode.**
Per-builder smoke (preview→launch) for Cursor, Claude, OpenCode, Factory Droid,
native HAM/Hermes mode, explicit deployment-default behavior, and Quick Preview.

---

## 13. Test plan

New / updated tests (no test is claimed to pass until actually run):

- **Selection-resolution unit tests** (`tests/` new): given a persisted external
  builder + `WorkspaceAgentPolicy` + readiness, resolution returns:
  - a selected, ready external builder → that harness's launch path;
  - a selected external builder that is **not** ready → "enable it" prompt (no substitute);
  - no external selection + OpenCode deployment default configured → OpenCode;
  - no external selection + no default → native HAM/Hermes path (or honest
    native-unavailable copy until wired);
  - explicit Quick Preview → internal scaffold even when an external builder is selected.
- **Build-prompt routing tests**: a `build_or_create` prompt with an external
  builder selected does **not** call `maybe_chat_scaffold_for_turn`; with no
  external selection and no configured default it uses native HAM/Hermes mode
  and still does **not** scaffold.
- **Native HAM/Hermes tests**: no external builder selected routes to the native
  new-build entry point once wired; until then it is presented as a real gap and
  never silently substituted by scaffold.
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
- **"No external selection" must not silently scaffold.** Under the corrected
  model, a user with no selected external builder and no configured OpenCode
  override is in native HAM/Hermes mode — not a silent internal-scaffold preview.
- **Hermes scope creep.** Native HAM/Hermes execution must not blur the
  supervisory/execution boundary. Keep any native build path bounded; do not add
  a second orchestrator (architecture + role-boundary rules).
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
- Stop and get owner decisions on: (a) **where the external-builder preference
  lives** (currently: `WorkspaceAgentPolicy` + coding-agent-access-settings),
  (b) whether the **OpenCode deployment default** remains enabled, and (c)
  whether `update_existing_project` also becomes external-harness-routed.
- Stop before deleting the internal scaffold or the retired deterministic
  template code (deprecation audit: keep until owner OK).
- Do not claim native HAM/Hermes new-build mode is available until §9 is wired.

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
