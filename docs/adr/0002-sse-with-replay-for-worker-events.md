# 0002 — SSE with per-job streams and Last-Event-ID replay for Worker events

For the Manus/Replit parity work we had to choose a transport between Workers (executing approved Plans) and browser consumers (the workbench). We picked **Server-Sent Events** over WebSocket, with one stream per `CloudRuntimeJob` (`GET /api/jobs/<job_id>/stream`) and full event replay via the standard SSE `Last-Event-ID` header. Each event carries a monotonic `seq` per `job_id` starting at 1; the API persists every emitted event for the lifetime of the job to support replay.

## Why SSE over WebSocket

The traffic pattern is one-way (Worker → browser). Cancel goes over a separate REST call, not the stream. SSE has built-in reconnect, `Last-Event-ID` resumption, and trivial proxy/load-balancer support (just HTTP). WebSocket buys full-duplex we don't need and adds operational complexity (separate keep-alive, separate auth, separate CDN handling).

## Why full replay (not forward-only)

Workers run minutes-to-hours per ADR-0001. Network blips are inevitable. Forward-only means the consumer must reconcile via REST refetch and risks "completed" UI states that beat the live `job_completed` event. Full replay makes the consumer dumb — it just reads the stream — at the cost of one storage write per event. The event log per job is bounded by Plan duration, so storage cost is small.

## Consequences

- One storage write per emitted event (Firestore / Redis stream / similar) — sized by event volume, not user count
- API can serve the same stream to multiple tabs of the same user without diverging — replay handles late joiners
- Heartbeat every 15s when idle keeps proxies from dropping the connection; heartbeats are in-band with their own event type so consumers filter them trivially
- Swapping to WebSocket later requires re-implementing replay semantics — the contract assumes SSE conventions
