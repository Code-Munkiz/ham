# 0012 — Worker events flow to the browser via API polling against Firestore

The Worker (a GKE pod) writes `SSEEvent` records to a Firestore subcollection. The API's per-job SSE handler (`GET /api/jobs/{job_id}/stream` in `src/api/jobs.py`) polls that subcollection every 500ms, pushing new events out to the browser. We picked polling over Firestore snapshot listeners and over a Worker→API push channel.

## Why polling

The browser-facing contract (ADR-0002) is already SSE with `Last-Event-ID` replay. The API already implements polling against the `BuilderRunEventsStoreProtocol.read_from(job_id, since_seq)` interface — every 500ms with a 15s heartbeat, drained on terminal status. Swapping the underlying store from file to Firestore is transparent at the API layer; the polling code does not change.

Trade-off: 500ms latency floor on event delivery. For chat-driven builder UX where Step durations are measured in seconds to minutes, this is invisible.

## Why not Firestore snapshot listeners

A snapshot listener would push near-real-time, but it puts long-lived stateful connections inside Cloud Run instances. Instance recycling kills the listener; the client reconnects to a different instance (works because `Last-Event-ID` replay covers the gap, but it's more moving parts). It also forces async/threading code into FastAPI routes that are otherwise synchronous.

## Why not Worker→API push

A Worker→API push channel (Pub/Sub topic per job, or direct HTTP callback) would be lowest latency but adds a second transport beside Cloud Tasks. ADR-0007 already rejected Pub/Sub for the main queue; using it just for events would be inconsistent and pay infrastructure cost we don't need at 3-5 user scope.

## Consequences

- One Firestore read per active SSE connection per 500ms. Cost is bounded by `active_streams × 2/sec`. At 3-5 user scope this is rounding error.
- API code in `src/api/jobs.py` is unchanged — the swap happens at the store factory.
- Switching to listeners or Pub/Sub later requires only `BuilderRunEventsStoreProtocol` to grow a `watch()` method; the API would add a branch but the contract stays valid.
- The 500ms latency floor is documented in CONTEXT.md so future readers don't try to "optimise" it without revisiting the trade-off.
