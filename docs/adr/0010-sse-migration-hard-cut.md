# 0010 — Activity feed migrates from polling to SSE in a single hard-cut PR

Phase 1 #3 framed the goal: replace today's activity-feed polling (the workbench polls a feed endpoint every ~2s) with SSE consumption of the per-job stream defined in ADR-0002 (`GET /api/jobs/<id>/stream`). We had to choose between a single hard-cut PR (replace polling with SSE end-to-end, delete polling code), a feature flag with side-by-side fallback, or a gradual per-surface rollout. We chose **hard cut**: one PR replaces the polling consumer with a custom `useJobStream(jobId)` React hook, deletes the polling path, and ships.

## Why hard cut

A feature flag would scaffold a second consumer code path that consumes the same backend data, plus the flag-rotation overhead to remove the polling path later. ADR-0002 already locks server-side full-event replay via `Last-Event-ID`, so a reconnect on flaky network behaves correctly — the rollback story SSE was supposed to need is already in place. Net: one consumer, one mental model, one mid-sized PR diff.

A gradual per-surface rollout would have spread the work across multiple PRs, each leaving the workbench in a temporary mixed state (some panels SSE, others polling) — harder to reason about for a 3-5 person team.

## Why no library

The frontend already uses SSE for `POST /api/chat/stream`. Adding a third-party SSE library (e.g. `@microsoft/fetch-event-source`) for the job stream would mean two SSE consumer styles in one codebase. A custom `useJobStream` hook is ~150 LoC, vitest-testable with a fake EventSource, and consistent with the existing in-house chat-stream consumer.

## Consequences

- One PR ships the migration; rollback is `git revert`
- Polling-related backend endpoints (whatever the workbench was hitting every 2s) can be deleted in the same PR, reducing the API surface
- `Last-Event-ID` reconnect is the safety net; the front end MUST honor it on disconnect rather than re-rendering as if the connection was lost
- New panels added in Phase 2b (approval card, in-flight card progress, cancel UX, error rendering) consume `useJobStream` from day one — no polling-era code paths need to be added for them
- If we ever need to roll back to polling (e.g. for a customer environment that proxy-blocks SSE), reversing this ADR means restoring the deleted polling consumer plus its endpoints — keep the deleted code one revert away
