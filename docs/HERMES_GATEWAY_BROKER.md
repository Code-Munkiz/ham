# Hermes gateway broker (HAM Path B)

**Operator story (team):** see [TEAM_HERMES_STATUS.md](TEAM_HERMES_STATUS.md) for how **API-side** read-only snapshot, **desktop-side** checks, and **HTTP gateway** chat routing relate and differ.

Backend-mediated **command center** data: one normalized snapshot plus optional SSE ticks. Built for **Hermes Agent v0.8.0** facts captured in [HERMES_UPSTREAM_CONTRACT_AUDIT.md](HERMES_UPSTREAM_CONTRACT_AUDIT.md).

## What the broker does

- Aggregates **existing** HAM surfaces:
  - Hermes hub payload (gateway mode, dashboard chat summary, skills capabilities probe) — same semantics as `GET /api/hermes-hub`.
  - Hermes runtime inventory (allowlisted CLI + sanitized config) via `build_runtime_inventory()` — **snapshot strips** `raw_redacted` blobs.
  - Hermes skills installed overlay via `build_skills_installed_overlay()` — **snapshot redacts** `raw_redacted` and may truncate `installations`.
  - Hermes HTTP probe: `GET {HERMES_GATEWAY_BASE_URL}/health` and optional `GET /v1/models` (count hint only), using `HERMES_GATEWAY_API_KEY` when set.
  - Allowlisted `hermes --version` line (no other CLI argv).
  - HAM `RunStore` count (CWD-scoped) and optional `ControlPlaneRun` summaries when `project_id` is a **known** registered project.
- Normalizes **external runner cards** (Cursor Cloud Agents, Factory Droids, honest stubs for OpenCode / Claude Code / Codex).
- Exposes **Path C placeholders** for JSON-RPC / WebSocket / doc-ahead REST — clearly labeled, not production RPC clients.

## What Hermes v0.8.0 supports (dashboard-relevant)

| Area | Supported via broker |
|------|----------------------|
| Chat / SSE (upstream) | Indirect: HAM chat already uses `HERMES_GATEWAY_*`; broker **probes** `/health` only. |
| Tools / plugins / MCP / skills lists | **CLI + config** (inventory + skills overlay), not generic Hermes REST inventory. |
| Live TUI menu / slash discovery | **Not exposed** — UI labels as CLI/TTY-only. |
| JSON-RPC / WebSocket control | **Not available** — placeholders only. |

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/hermes-gateway/snapshot` | Versioned snapshot. Query: `project_id` (optional), `refresh=true` to recompute and **write** all broker fragments (inventory, skills overlay, HTTP probe, version CLI) into the TTL cache so the next `refresh=false` read is not stale. |
| GET | `/api/hermes-gateway/capabilities` | Static manifest + security notes. |
| GET | `/api/hermes-gateway/stream` | SSE: compact ticks (~`HAM_HERMES_GATEWAY_SSE_INTERVAL_S`, default 20s). Full data: use snapshot. |

## Snapshot schema (`schema_version` 1.0)

Top-level keys (see `src/ham/hermes_gateway/broker.py`):

- `kind`: `ham_hermes_gateway_snapshot`
- `schema_version`, `captured_at`, `ttl_seconds`, `freshness` (per-fragment cache hits + build latency)
- **`operator_connection`** (additive): derived **single pane** for the dashboard — summarizes `hermes_version.cli_report` (allowlisted `hermes --version`), `http_gateway` probe, `hermes_hub.gateway_mode` (HAM chat path), plus `captured_at` / TTL / degraded count and a short **guidance** string (CLI vs `HERMES_GATEWAY_*`). No new Hermes argv.
- `hermes_version.cli_report`, `hermes_hub`, `runtime_inventory` (sanitized), `skills_installed` (sanitized), `http_gateway`
- `counts`, `commands_and_menus`, `activity`, `external_runners`, `degraded_capabilities`, `warnings`, `future_adapter_placeholders`

## Read-only vs stubbed

- **Read-only:** snapshot, capabilities, stream ticks; Hermes HTTP GET probes; allowlisted CLI invocations inside existing inventory/version helpers.
- **Stubbed:** OpenCode, Claude Code, Codex runner cards; JSON-RPC / WebSocket adapter rows; `/health/detailed` until verified on a given Hermes build.

## Why JSON-RPC / WebSocket / live menu control is deferred

Phase 0 audit found **no** Hermes JSON-RPC server and **no** WebSocket menu plane on v0.8.0. The durable surfaces are **REST + SSE** (chat, runs) and **CLI/config** for inventory. HAM does not ship clients for rumored protocols.

## Future Hermes versions

When upstream adds verified endpoints:

1. Add an adapter module under `src/ham/hermes_gateway/adapters/` (e.g. `http_health_detailed.py`).
2. Register it in `HermesGatewayBroker.build_snapshot` with TTL and redaction rules.
3. If a real JSON-RPC surface appears, implement `adapters/rpc_live.py` and wire it **only** after audit — replace placeholder dicts; do not fake `production_safe`.

## Security guardrails

- **No** secrets, provider keys, or raw env in snapshot JSON.
- **No** arbitrary shell from browser input; CLI argv remain **allowlisted** in `hermes_runtime_inventory` / `cli_inventory`.
- **No** forwarding of user-controlled URLs to Hermes; probes use **server** `HERMES_GATEWAY_BASE_URL` only.
- Snapshot **replaces** `raw_redacted` fields with an omission message; deep inventory remains on `GET /api/hermes-runtime/inventory` and `GET /api/hermes-skills/installed` (same Clerk/operator gates as before).

## TTL cache and refresh

Per-fragment in-memory cache (`TtlCache`) keys: `inventory`, `skills_installed`, `http_probe`, `hermes_version`. When `GET .../snapshot?refresh=true` runs, the broker recomputes each fragment, returns it, and **repopulates** all four cache entries so a subsequent request without `refresh` reflects the new data. Without that repopulation, a manual refresh would still be followed by stale cache hits until TTL expired.

## Configuration

| Env | Role |
|-----|------|
| `HAM_HERMES_GATEWAY_CACHE_TTL_S` | Broker fragment TTL (default 45, clamped 5–600). |
| `HAM_HERMES_GATEWAY_SSE_INTERVAL_S` | SSE tick interval (default 20, clamped 5–120). |
| `HERMES_GATEWAY_BASE_URL`, `HERMES_GATEWAY_API_KEY` | Hermes HTTP probe (same semantics as chat gateway). |
| `HAM_HERMES_CLI_PATH`, `HAM_HERMES_SKILLS_MODE` | Unchanged; inherited from inventory/skills modules. |

## Frontend

- **Route:** `/command-center` (Diagnostics → Command Center).
- **Activity:** `/activity` polls the snapshot and falls back to demo mocks if the API errors.
