# 0001 — A Plan is the unit of work; queue carries one message per Plan

The Manus/Replit parity work introduces a Planner → Executor → Verifier loop. We had to choose whether the queue (Tier 1 gap #8) carries one message per Plan with the Worker iterating Steps in-process, or one message per Step with a coordinator scheduling them. We chose **one message per Plan**: simpler mental model, single SSE source per run, cancel is a cooperative signal to one Worker. The trade-off is that Workers must survive minutes-to-hours, so the runtime is GKE / Cloud Run Job, not request-bound Cloud Run Service — which is already where HAM's preview runtime lives.

## Consequences

- Worker lifetime is per-Plan, not per-Step → suits GKE pods + Cloud Run Jobs
- SSE stream originates from one Worker per Plan → API bridges Worker events to browser (Worker is not publicly addressable)
- Cancel is a side-channel signal (Firestore/Redis/Pub/Sub) to the running Worker, not a queue dequeue
- Per-Step retry is the Worker's responsibility, not the queue's
- Mid-flight re-planning (Manus pattern) is **out of scope for v1** — Plan is immutable once approved
