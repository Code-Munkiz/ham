# 0013 — Worker assigns event `seq` from an in-memory counter, guarded by create-only writes

`SSEEvent.seq` is a monotonic integer per `job_id` starting at 1 (locked by ADR-0002 + Phase 0 Contract 4). For the file-backed `BuilderRunEventsStore`, `seq` is assigned by load-max-then-`+1` under a process lock. For Firestore we considered three options:

| Option | Round trips per append | Concurrent-writer safety |
|---|---|---|
| In-memory counter in the Worker | 0 | Relies on contract: one Worker per `job_id` |
| Firestore counter doc with `Increment(1)` | 2 | Storage-layer safe |
| Firestore transaction (read max → write) | 2+ | Storage-layer safe |

We picked **in-memory counter, guarded by `create()`-only writes plus a startup assertion**.

## Why in-memory is safe given current invariants

Two locked invariants already ensure at most one Worker writes events for a given `job_id` at any time:

- ADR-0001: one Worker per Plan, no mid-flight resume.
- ADR-0007: Cloud Tasks redelivery uses `job_id` as the idempotency key; on pop, the Worker checks `CloudRuntimeJob.status` — if `running/scheduled`/terminal, it exits without writing.
- Phase 2.5 Dispatcher transitions `queued → scheduled` before calling the K8s scheduler (3e guardrail), and the scheduler's get-before-create on Job name (`ham-worker-{job_id_short}`) is the second line of defence.

Given those, a fresh Worker for a given `job_id` is guaranteed to be the only writer, so an in-process counter starting at 1 produces the correct monotonic sequence with zero Firestore round trips.

## Why we still need a storage-layer guard

The contract that makes in-memory safe is invariant-driven, not storage-enforced. If some future change accidentally permits Worker takeover (a Manus-style feature explicitly out of scope per ADR-0001), the in-memory counter would silently produce duplicate `seq` values and break replay. The mitigation is cheap:

- **Create-only writes.** Firestore documents written with `create()` (not `set()` / `upsert()`) fail with `AlreadyExists` if the document already exists. The event doc ID is the zero-padded `seq`, so a duplicate `seq` raises immediately rather than corrupting data.
- **Startup assertion.** On Worker startup, query the latest event for the `job_id`. If any events exist for a Job whose status is `queued` or freshly transitioned to `running`, fail loudly: someone else already wrote events for this job.

These together turn the "duplicate Worker" failure mode from silent corruption into a noisy crash before any new events are written.

## Consequences

- Event append on Firestore is one round trip (the `create()` call). No counter-doc read, no transaction.
- If we ever add mid-flight Worker resume or parallel sub-Workers, this ADR must be revisited — we'd need to switch to a counter doc or transactions. The startup guard would catch the violation before silent corruption.
- The file-backed `BuilderRunEventsStore` keeps its load-max-then-`+1` semantics under a process lock. The two implementations have different concurrency models but produce the same monotonic `seq` per `job_id`; the Protocol contract is unchanged.
- A new `latest_seq(job_id)` method is added to `BuilderRunEventsStoreProtocol` to support the startup guard. Both backends implement it.
