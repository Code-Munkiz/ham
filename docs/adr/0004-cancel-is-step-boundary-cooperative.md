# 0004 — Cancel is cooperative at Step boundaries, not mid-Step

The cancel protocol (`POST /api/jobs/<id>/cancel`) signals the Worker; the Worker then winds down. We had to decide whether the Worker abandons its current Step immediately (mid-Step interrupt) or finishes the current Step first (step-boundary interrupt). We chose **step-boundary**: the Worker honors cancel at the next Step boundary. Latency budgets are 5 seconds to emit `cancel_acknowledged` and 30 seconds to reach the terminal `job_cancelled` event. Mid-Step interrupt is explicitly not contracted.

## Why step-boundary

Coarse Steps (per ADR-0001 and Contract 1) can encompass a tool call, a file edit, or a verification — operations that may not be safely interruptable mid-flight (half-written files, partially-applied edits). Step-boundary cancel guarantees that already-applied Step effects are coherent: Steps 1 and 2 are fully done; Step 3 is either fully done or not started. The Worker doesn't need rollback logic for partial Step state.

The trade-off is sluggish cancel during long Steps (e.g. a 60s LLM call inside a Step). The mitigation, when this becomes painful, is making Steps smaller — not retrofitting mid-Step interrupt.

## Consequences

- Worker implementers must check the cancel signal between Steps; they are not required to interrupt mid-tool-call
- File system state is always at a Step boundary when `job_cancelled` is emitted — no half-applied Steps
- Already-completed Step effects are NOT rolled back; UI must surface "cancelled after step N of M"
- If we ever need mid-Step interrupt, it's a Worker-implementation change against a stricter contract, not a wire-format change — the SSE `JobCancelledPayload.cancelled_at_step_id` already accommodates "interrupted partway through this step"
- The janitor (Tier 1 #7) is the backstop for Workers that don't honor cancel within 30s; this is enforcement, not contract
