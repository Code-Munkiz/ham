# 0003 — Per-project serialization is enforced at the approval gate, not the queue

The preview runtime is one pod per project. Two concurrent Workers for the same project would race on the source snapshot, corrupt builds, and confuse the SSE stream. We had to pick between enforcing serialization at the queue (ordering keys, a per-project coordinator) or at the approval gate (refuse to enqueue if another Plan is in flight). We chose **the gate**: when a user clicks approve, the API rejects the call with `409 project_busy` if any `CloudRuntimeJob` for the project is in {`queued`, `running`, `cancelling`}. The user gets immediate feedback in the chat UI; no second Plan ever reaches the queue while one is in flight.

## Why gate-side, not queue-side

A queue-side coordinator (Cloud Tasks ordering keys, or a custom dispatcher) adds infrastructure and forces a particular queue technology. Gate-side enforcement is one synchronous DB check against the existing `CloudRuntimeJob` store. It's also user-visible — the chat UI can render "another build is running for this project; cancel it first." A coordinator would silently delay, which is worse UX.

## Consequences

- Worker implementations can assume they are the only Worker touching their project at any time
- Cancel protocol can be cooperative without worrying about a queued successor pre-empting the cancelled job
- The contract is queue-technology-agnostic (Cloud Tasks, Pub/Sub, or anything else)
- Multi-project parallelism is unconstrained: different projects can run concurrent Workers
- If we ever want per-step queueing (rejected in ADR-0001), this enforcement point would need to move — but moving it later is a one-place change in the approval handler
