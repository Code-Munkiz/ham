# 0005 — v1.x runtime job status aliasing (`succeeded` ↔ `completed`, `unsupported` retained)

Phase 0 locks `CloudRuntimeJobStatus = Literal["queued","running","cancelling","cancelled","completed","failed"]` (per Contract 6). The deployed v1.x runtime emits wire statuses `succeeded` and `unsupported` that don't exist in that Literal. PR #337 resolved this by aliasing at the store boundary rather than expanding the Phase 0 Literal or breaking v1.x audit consumers.

## Resolution

- **On load:** `succeeded` (legacy) → `completed` (Phase 0).
- **On wire serialization to legacy consumers:** `completed` (Phase 0) → `succeeded` (legacy).
- **`unsupported`** is retained as a v1.x-only value accessible through a broader `CloudRuntimeJobStoreStatus` union, never produced by Phase 0 Workers. It signals "this runtime can't execute the job for a reason that isn't a failure" — kept for forensic value in audit logs.

The Phase 0 `CloudRuntimeJobStatus` Literal stays minimal; v1.x consumers see no behavioral change.

## Why aliasing instead of expanding the Literal

Adding `succeeded` and `unsupported` to the Phase 0 Literal would force every downstream consumer (the SSE envelope, the Worker behavior contract, the cancel protocol) to handle two terminal-success values and a non-failure-non-success status. That's contract pollution to accommodate transient legacy wire vocabulary. Aliasing isolates the cost to the store layer.

## Consequences

- Worker code, SSE event producers, and frontend consumers see only the six Phase 0 status values
- The store layer (`src/persistence/builder_runtime_job_store.py`) is the single place that must understand the alias
- Removing the alias is a v2.0 concern, tracked alongside the deprecated `error_code`/`error_message` removal (ADR-equivalent decision from Contract 5)
- Future writers introducing v1.x-incompatible Worker behavior must remember that `succeeded` is what hits audit storage on the wire, not `completed`
