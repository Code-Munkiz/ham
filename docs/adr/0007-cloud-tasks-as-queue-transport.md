# 0007 — Cloud Tasks as the WorkerEnvelope queue transport

Tier 1 #8 calls for a queue between the API and the runtime Worker. Phase 0 deliberately deferred the transport pick (`WorkerEnvelope` per Contract 3 is queue-agnostic). Three candidates were on the table — Google Cloud Tasks, Google Pub/Sub, and self-hosted (Redis Streams or RabbitMQ on GKE). We pick **Cloud Tasks**.

## Why Cloud Tasks

| Property | Cloud Tasks | Pub/Sub | Self-hosted |
|---|---|---|---|
| Maps to existing Cloud Run / GKE patterns | ✓ HTTP target → existing service | Streaming pull pattern (different) | New infra to operate |
| Ack semantics | HTTP 2xx = ack (simple) | Per-subscription ack deadline | Custom |
| Body limit | 100KB | 10MB | Custom |
| Native GCP IAM | ✓ | ✓ | None |
| Per-queue rate limiting | ✓ built-in | Via subscription config | Custom |
| Operational burden | Managed | Managed | 3-5 person team can't absorb |

`WorkerEnvelope` is pointer-only (per ADR-0001 / Contract 3) — `plan_id`, `job_id`, `workspace_id`, `project_id`, `requested_by`, `enqueued_at`, `correlation_id`, `envelope_id`. Well under 1KB. Cloud Tasks' 100KB ceiling is the smallest among candidates but is irrelevant for this payload shape.

## Why not Pub/Sub

Pub/Sub's strengths (high-throughput streaming pull, fan-out subscriptions, 10MB payloads) are not exercised here. We have one consumer per queue, modest throughput, and pointer-sized payloads. Pub/Sub adds streaming-pull complexity for no observable benefit.

## Why not self-hosted

A 3-5 person team can't operate a queue cluster. Redis Streams + Sentinel or RabbitMQ + clustering is a fork in operational maturity HAM doesn't need to take.

## Trade-offs and consequences

- Cloud Tasks task scheduling is **per-target-URL**: one queue, one dispatcher endpoint
- Per-project ordering is enforced at the approval gate (ADR-0003), not at the queue — Cloud Tasks doesn't natively guarantee FIFO across enqueues unless you use a single execution slot
- Retry budgets and backoff are Cloud-Tasks-side configuration; the Worker idempotency from `job_id` (Contract 3) handles redelivery
- Cancel-while-queued is best-effort per the cancel protocol (ADR-0004 / Contract 6): the API can set `CloudRuntimeJob.status = cancelled` before the Worker pops the envelope; on pop, the Worker checks status and exits
- The dispatcher endpoint becomes the only HTTP surface the queue talks to; it must be authenticated (Cloud Tasks → Cloud Run via OIDC token verification per existing patterns)
- Migrating to Pub/Sub later is possible: `WorkerEnvelope` is queue-agnostic, so the swap is the dispatcher endpoint and the enqueue call, not the contract
