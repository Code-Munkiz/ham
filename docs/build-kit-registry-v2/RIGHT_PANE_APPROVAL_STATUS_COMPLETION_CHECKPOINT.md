# Right-Pane Approval / Status / Result Relocation — Completion Checkpoint

Status: **Complete** (Droid/Factory + OpenCode shared managed lane). Frontend-only.

This checkpoint closes the mission that moved the build **approval / status / result**
experience out of the chat surface and into the workbench **right pane**, keeping chat
conversation-first and build-kit internals hidden. It complements the planning and audit
docs in this directory:

- `RIGHT_PANE_APPROVAL_STATUS_RELOCATION_PLAN.md` — the original phased plan.
- `RIGHT_PANE_APPROVAL_STATUS_PHASE_0_AUDIT.md` — the "Ready with cautions" audit.

---

## What shipped (summary of required points)

### 1. Status shell added
A small presentational **status shell** was added to the right pane:
`frontend/src/features/hermes-workspace/workbench/WorkbenchBuildStatusPanel.tsx`, mounted
inside `WorkbenchPreviewPanel` (test id `hww-build-status-shell`) directly above
`hww-preview-status-pills`. It renders only plain-language lifecycle copy — "Preview ready",
"Ready to build", "Building…", "Preview updated", "Build completed", "Something needs
attention" — routed through the existing `workbenchPreviewMessages.ts` sanitizers. It is
purely presentational: no approval controls, no launch logic, no nested approval panel.

### 2. Approval relocated
The managed build **approval** engine was **approval relocated** from the chat card into the
right-pane host `WorkbenchManagedApprovalMount.tsx`. The mount gates on the SAME exported
pure predicates (`shouldShowManagedBuildApproval` / `shouldShowOpencodeBuildApproval`), picks
the Droid (`ManagedBuildApprovalPanel`) vs OpenCode (`ManagedOpencodeBuildApprovalPanel`)
wrapper, and passes `projectId` + `userPrompt` into the **unmodified**
`ManagedProviderBuildApprovalPanel`. The panel is mounted at a stable location that does not
unmount on workbench tab switch or mobile right-pane collapse, so a running build's polling
state survives.

### 3. Result / actions consolidated
The completed and failed surfaces were **actions consolidated** into the right pane, reusing
the panel's existing `SuccessSummary` + `startOver`. The succeeded state exposes the open
(preview link), view-changes, changed-count, collapsed technical details, and "Keep building"
revise/retry affordances; the failed state exposes the plain-language error plus "Start over".
No new **result** mechanics were invented beyond what `SuccessSummary` already supports.

### 4. Chat cleaned up
The chat surface was **chat cleaned up**: `CodingPlanCard` is now a minimal pointer
("Preview is ready on the right — review and approve the build in the workbench"). It no
longer mounts the approval engine and no longer duplicates any running/success/failure result
UI. There is no approve checkbox and no launch CTA in chat — a single source of launch truth
lives only in the right-pane panel.

### 5. Approval / digest / launch mechanics preserved
All hard mechanics were **preserved** exactly — the relocation moved *where* the panel mounts,
never *what* it does:

- `proposal_digest` and `base_revision` are passed verbatim from preview into launch.
- `confirmed: true` is still hardcoded in the launch payload.
- Droid sends `accept_pr: true`; OpenCode omits `accept_pr`.
- Server-side digest verification and the launch calls (`launchDroidBuild` /
  `launchOpencodeBuild`) are unchanged.
- Running-phase polling via `fetchControlPlaneRun` (running → succeeded/failed) is intact, and
  synchronous `ok:true` launches never poll.
- `SmokePreflightError` still surfaces a user-friendly `${code}: ${message}`, and
  `startOver`/reset semantics are unchanged.

### 6. No Builder Studio surfacing
**Builder Studio** was NOT reintroduced as a primary task-launch surface. The relocated flow
exposes only preview + slim approval + status + result actions — no Builder Studio launch
control.

### 7. No build-kit internals exposed
No **build-kit internals** leak in either chat or the right pane: build-kit names, recipe/pack
IDs, `registry_v2*`, routing confidence, fallback reasons, gate reports, scaffold issue codes,
render budgets, playbook headers, provider candidate matrices, repair-loop details, raw logs,
or provider keys. This is locked by `FORBIDDEN_CARD_TOKENS`, `FORBIDDEN_BUILD_REGISTRY_TOKENS`
(architecture §6), and `FORBIDDEN_USER_COPY_PATTERN` guards across the relocated surface.

### 8. Tests run
The validation gate is component **tests** (Vitest + @testing-library + jsdom) plus
whole-frontend lint (`tsc --noEmit`). The following stayed/were made green:

- `WorkbenchBuildStatusPanel.test.tsx`, `WorkbenchManagedApprovalMount.test.tsx`,
  `WorkbenchManagedApprovalMount.result.test.tsx`, `WorkspaceWorkbench.relocation.test.tsx`.
- The six gated files: `WorkspaceWorkbench.test.tsx`, `CodingPlanCard.test.tsx`,
  `ManagedBuildApprovalPanel.test.tsx`, `ManagedOpencodeBuildApprovalPanel.test.tsx`,
  `ManagedOpencodeBuildApprovalPanel.polling.test.tsx`,
  `WorkspaceChatScreen.codingIntent.test.tsx`.
- New cleanup guards: `RightPaneCleanupGuards.test.tsx` (VAL-CLEAN-001/002/003/005).
- `npm run lint` (`tsc --noEmit`) exits 0; the diff is frontend-only plus this doc — no
  backend / API / Python files changed.

---

## Documented follow-up: Claude and Cursor left unchanged

This relocation covered only the shared managed lane (Droid/Factory + OpenCode), which are the
only providers mounted via `CodingPlanCard`. **Claude** and **Cursor** use separate launch
surfaces and were intentionally **left unchanged**. Extending the same right-pane
approval/status/result lifecycle to Claude/Cursor would require a separate lifecycle design and
is recorded here as a **follow-up** — no new provider mechanics were invented and no controls
were faked to imply support.
