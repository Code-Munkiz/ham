# Invisible Orchestration Implementation Plan

Implementation plan for making Build Registry v2 improve HAM's current conversation-first build flow invisibly. This plan documents the smallest safe path only. It does **not** authorize code, recipes, routing, UI changes, Builder Studio surfacing, default v2 enablement, or any normal-user exposure of build-kit internals.

**Baseline:** `origin/main` at `8e245d53` — `docs(builder): add invisible build kit orchestration plan`.

---

## 1. Executive summary

- **Build kits should improve chat-built outputs invisibly.**
- The current scaffold path already supports Build Registry v2 playbook context: `builder_chat_scaffold.py` enriches plan metadata and `builder_llm_scaffold._append_scaffold_context()` resolves v2/v1 scaffold context.
- The current coding conductor / provider preview and launch lane needs an **internal-only orchestration bridge** if it is going to benefit from the same kit selection.
- Normal users must not see kit names, route details, gate reports, YAML mechanics, scaffold-quality issue codes, or registry metadata.
- **This doc authorizes no code by itself.**

---

## 2. Current flow summary

Current conversation-first build flow:

```text
User chat
→ WorkspaceChatScreen
→ coding conductor preview
→ provider preview/approval
→ provider launch
→ right-side WorkspaceWorkbench preview/results
```

Current scaffold path:

```text
builder_chat_scaffold
→ enrich_plan_metadata_with_registry_v2
→ generate_scaffold
→ resolve_scaffold_context
→ v2 playbook context appended silently when flag + metadata match
```

The first flow is the product-facing path. The second flow is the proven internal scaffold path. The implementation should connect them only at backend/scaffold seams and must keep registry details out of normal frontend payloads and copy.

---

## 3. Gap statement

Build Registry v2 is already wired into scaffold generation. When `HAM_BUILD_REGISTRY_V2_ENABLED` is truthy and plan metadata includes `registry_v2_app_type`, `generate_scaffold()` can append the matching v2 playbook context. When the flag is off or metadata is missing, the resolver falls back to v1/default context.

That is not yet consistently wired into the current coding conductor / provider preview and launch lane. The goal is **not** to expose kits, ask users to pick recipes, or explain routing. The goal is to improve generated output quality quietly by ensuring chat-origin build/scaffold work gets the same internal playbook context when it is safe and opt-in enabled.

---

## 4. Design principles

- **Server-side / internal-only:** build-kit selection and metadata live on the backend or scaffold side, not in normal browser payloads.
- **v2 remains opt-in:** `HAM_BUILD_REGISTRY_V2_ENABLED` continues to gate Build Registry v2.
- **v1 fallback preserved:** flag off, no match, or registry errors keep the existing v1/default behavior.
- **No client-controlled route/app-type selection:** clients send user intent, not recipe IDs or app-type overrides.
- **No normal UI exposure of registry metadata:** no `registry_v2_app_type`, recipe IDs, pack IDs, fallback reasons, render lengths, route confidence, or playbook headers.
- **No Builder Studio task-launch surface:** build initiation stays in chat; Settings → Builders remains config-only/internal.
- **Provider/conductor outputs remain user-friendly:** users see outcomes, previews, approvals, and retry/revise options.
- **Tests prevent accidental exposure:** implementation must include backend/frontend assertions that normal payloads and rendered UI do not leak kit internals.

---

## 5. Minimal implementation phases

### Phase 1: Internal metadata enrichment seam

- Identify the server-side build/scaffold boundary for chat-origin build work.
- Enrich internal plan metadata with `enrich_plan_metadata_with_registry_v2(...)`.
- Keep selected app type, pack id, fallback reason, route confidence, and any gate outcome internal.
- Do not add fields to the normal frontend payload unless they are redacted and gated behind a future explicit debug/operator mode.

### Phase 2: Reuse existing scaffold context seam

- Reuse `generate_scaffold()` / `_append_scaffold_context()` / `resolve_scaffold_context()`.
- Avoid duplicating playbook rendering or loading logic in conductor/provider code.
- Preserve v1 fallback behavior exactly: flag off, no metadata, no match, bad app type, or registry error must not break normal builds.

### Phase 3: User-copy guardrails

- Normal chat and right-pane copy describes outcomes only.
- Do not show recipe IDs, pack IDs, route explanations, gate reports, issue codes, YAML paths, render lengths, or playbook headers.
- Do not use phrases like "route matched", "selected kit", "registry v2", or "gate failed" in normal UX copy.

### Phase 4: Tests

- **Backend tests:** normal conductor/build preview responses do not expose build-kit fields or values.
- **Frontend tests:** `CodingPlanCard` and right-pane result/preview copy do not expose recipe IDs, pack IDs, registry metadata, issue codes, YAML paths, or gate language.
- **Scaffold tests:** v2 context can be applied internally when flag + metadata match.
- **Fallback tests:** flag off still uses v1/default behavior.
- **Regression tests:** Builder Studio remains non-launching and no task-launch route/nav resurfaces.

### Phase 5: Optional operator/debug mode later

- Expose selected app type, fallback reason, route confidence, gate outcome, and repair-loop details only behind an explicit flag/role.
- Keep it off by default.
- Treat it as troubleshooting/QA/operator-only, not part of normal UX.

---

## 6. Candidate files likely involved

Likely future implementation files:

- `src/api/coding_conductor.py`
- `src/api/droid_build.py`
- `src/api/opencode_build.py`
- `src/ham/builder_chat_scaffold.py`
- `src/ham/builder_llm_scaffold.py`
- `src/ham/build_registry/scaffold_context.py`
- `frontend/src/features/hermes-workspace/screens/chat/coding-plan/CodingPlanCard.tsx`
- `frontend/src/features/hermes-workspace/workbench/WorkspaceWorkbench.tsx`
- Relevant backend/frontend tests around conductor preview, build preview/launch, scaffold context, chat cards, and workbench results.

This plan does **not** modify those files. They are listed only to identify likely future touch points.

---

## 7. What should remain invisible

Normal users should not see:

- `registry_v2_app_type`
- Recipe IDs like `site.dashboard-ui-core`
- Pack IDs like `pack.site`
- Route confidence
- Fallback reason
- Gate review details
- Scaffold quality issue codes
- YAML paths / render lengths
- Playbook headers such as `Build Registry v2 playbook context:`

---

## 8. What users may see

Normal users may see:

- Concise natural-language plan
- Preview / result summary
- Saved version / change count
- Retry / revise options
- Plain-language failure messages
- Approval prompt when needed

The principle is: **surface results, not machinery**.

---

## 9. Failure handling

- Do not say "no route matched".
- Do not show gate report details.
- Fall back gracefully to the existing v1/default path.
- Ask clarification only when needed.
- Offer revise, simplify, or retry options in plain language.
- Treat registry failures as internal fallback events, not user-facing errors.

---

## 10. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Accidental payload exposure | Keep registry metadata out of normal conductor/build preview responses; add response-shape tests. |
| UI copy leaking recipe IDs | Add frontend assertions against recipe IDs, pack IDs, registry headers, gate terms, and issue codes. |
| Client-controlled app type | Never accept recipe/app-type selection from normal browser requests; derive internally from prompt + flag. |
| Default v2 enablement too early | Preserve `HAM_BUILD_REGISTRY_V2_ENABLED`; flag off remains v1/default. |
| Builder Studio resurfacing | Keep build initiation in chat; Settings → Builders stays config-only; test route/nav posture if touched. |
| Provider-brand overexposure | Treat as separate UX polish; do not conflate provider labels with build-kit internals. |
| Drift between conductor lane and scaffold lane | Reuse `enrich_plan_metadata_with_registry_v2()` and `resolve_scaffold_context()` instead of implementing a parallel registry path. |

---

## 11. Recommended first implementation PR

Start with a small PR:

- Add internal-only enrichment at a backend build/scaffold boundary **only if the seam is clear**.
- Reuse existing scaffold context functions; do not duplicate registry rendering.
- Add tests proving no build-kit internals appear in normal conductor/build preview payloads or normal frontend copy.
- Do not alter the frontend UX except possibly adding test coverage.
- Do not enable Build Registry v2 by default.

If the seam is not clear enough, the first implementation PR should be a focused **test-only / seam-discovery PR** that locks current behavior and identifies the precise backend boundary before runtime changes land.

---

## 12. Non-goals

This plan does **not** authorize:

- Code from this document
- Recipe or routing changes
- Default v2 enablement
- User-facing build-kit catalog
- Builder Studio surfacing
- Debug/operator mode implementation
- CI changes
- Runtime/API/frontend/scaffold behavior changes without a separate implementation task

---

## 13. References

- [INVISIBLE_BUILD_KIT_ORCHESTRATION_PLAN.md](./INVISIBLE_BUILD_KIT_ORCHESTRATION_PLAN.md)
- [NEXT_WAVE_DECISION.md](./NEXT_WAVE_DECISION.md)
- [WEBSITE_PACK_STAGE_CHECKPOINT.md](./WEBSITE_PACK_STAGE_CHECKPOINT.md)
- [STATUS.md](./STATUS.md)
