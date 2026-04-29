# Hermes upstream contract audit (Phase 0)

**Scope:** Read-only verification of what Hermes exposes for discovery and control, as installed on the audit machine and as documented upstream. **No HAM product code was changed** for this audit (this file only).

**Audit date:** 2026-04-24  
**Hermes install path:** `~/.local/bin/hermes` → project root reported as `~/.hermes/hermes-agent`

---

## 1. Hermes version detected

| Source | Output |
|--------|--------|
| `hermes --version` | **Hermes Agent v0.8.0 (2026.4.8)** |
| Python (bundled) | 3.11.15 |
| Self-reported update | “2266 commits behind — run `hermes update`” (local tree may lag published docs) |

---

## 2. Commands run (exact)

All read-only / informational:

```bash
which hermes
hermes --version
hermes -h
hermes gateway -h
hermes acp -h
hermes sessions -h
hermes tools -h
curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1:8642/health
```

**Note:** `curl` to `127.0.0.1:8642/health` did not succeed (no HTTP response / connection failed), indicating the **API server was not listening** at audit time (typical if `API_SERVER_ENABLED` is false or `hermes gateway` is not running).

---

## 3. Files and docs inspected (exact)

### Local Hermes source (installed tree)

Paths are relative to the Hermes project root reported by `hermes --version` (typically `~/.hermes/hermes-agent`).

| Path | Purpose |
|------|---------|
| `gateway/platforms/api_server.py` | **Canonical implementation** of the OpenAI-compatible HTTP API (aiohttp routes, auth, chat, responses, runs SSE, jobs) |
| `gateway/config.py` | `Platform.API_SERVER`, env wiring (`API_SERVER_*`, `API_SERVER_CORS_ORIGINS`) |
| `hermes_cli/config.py` | User-facing env catalog entries for `API_SERVER_ENABLED`, `API_SERVER_KEY`, `API_SERVER_PORT`, `API_SERVER_HOST` |
| `hermes_cli/tools_config.py` | **curses**-based interactive tool menus (not HTTP) |
| `tests/gateway/test_api_server.py` | Tests and defaults (e.g. port 8642) |

### HAM repository (reference only)

| Path | Purpose |
|------|---------|
| [docs/HERMES_GATEWAY_CONTRACT.md](HERMES_GATEWAY_CONTRACT.md) | HAM’s pinned **chat** adapter: `POST /v1/chat/completions` + SSE |
| [docs/reference/hermes-agent-reference.md](reference/hermes-agent-reference.md) | Pointer to optional Repomix dump (not required for this audit) |

### Published upstream documentation (fetched)

| URL | Notes |
|-----|--------|
| https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server | **Official** API server description: OpenAI-compatible REST + SSE; lists `/v1/responses`, `/v1/runs`, `/api/jobs`, `/health/detailed`, env vars |

---

## 4. JSON-RPC, WebSocket, and “gateway” naming

| Surface | Finding |
|---------|---------|
| **JSON-RPC (Hermes API server)** | **Not present.** The shipped API server is **aiohttp + REST** (`add_get` / `add_post`). No JSON-RPC dispatcher was found in `api_server.py`. |
| **WebSocket (API server)** | **Not present** on the HTTP API server router inspected. |
| **SSE** | **Yes**, for `POST /v1/chat/completions` with `"stream": true` and for **`GET /v1/runs/{run_id}/events`** (structured run lifecycle). |
| **`hermes gateway` CLI** | Manages the **messaging gateway** (Telegram, Discord, WhatsApp, etc.) via `run/start/stop/...` — **not** the same thing as “JSON-RPC gateway” in the user brief. When the API server platform is enabled, **that** HTTP server is what HAM’s `HERMES_GATEWAY_BASE_URL` targets. |

Unrelated “JSON-RPC” mentions exist in **third-party messaging docs** (e.g. Signal + signal-cli) inside the Hermes repo; those are **not** HAM’s Hermes control plane.

---

## 5. Confirmed HTTP API (installed v0.8.0 code)

Source: `gateway/platforms/api_server.py` route registration (lines ~1610–1628).

| Method | Path | Role |
|--------|------|------|
| GET | `/health` | JSON `{"status":"ok","platform":"hermes-agent"}` |
| GET | `/v1/health` | Same as `/health` |
| GET | `/v1/models` | OpenAI-style model list; **local v0.8.0 code returns a single model id `hermes-agent`** (cosmetic; real LLM is server-side config) |
| POST | `/v1/chat/completions` | OpenAI Chat Completions; optional streaming (SSE); tool progress via custom stream events per upstream docs |
| POST | `/v1/responses` | OpenAI Responses API; stateful `previous_response_id`; streaming per docs |
| GET | `/v1/responses/{response_id}` | Fetch stored response |
| DELETE | `/v1/responses/{response_id}` | Delete stored response |
| POST | `/v1/runs` | Start run; returns `run_id` (202 in docs; implementation should be verified against running server) |
| GET | `/v1/runs/{run_id}/events` | **SSE** stream: e.g. `tool.started`, `tool.completed`, `reasoning.available`, `message.delta` (from callback wiring in source) |
| GET | `/api/jobs` | List scheduled jobs |
| POST | `/api/jobs` | Create job |
| GET | `/api/jobs/{job_id}` | Get job |
| PATCH | `/api/jobs/{job_id}` | Update job |
| DELETE | `/api/jobs/{job_id}` | Delete job |
| POST | `/api/jobs/{job_id}/pause` | Pause |
| POST | `/api/jobs/{job_id}/resume` | Resume |
| POST | `/api/jobs/{job_id}/run` | Run now |

### Documentation vs installed code (drift)

- Published docs describe **`GET /health/detailed`** (sessions, agents, resource usage).  
- **Installed v0.8.0 `api_server.py` only registers `/health` and `/v1/health`** — **no `/health/detailed` route** in the inspected file. Treat **detailed health** as **doc-ahead or version-ahead** until confirmed after `hermes update` or on a matching commit.

### Request/response examples (official; no secrets)

**Health (no auth if `API_SERVER_KEY` unset locally — production must use a key):**

```http
GET /health
```

```json
{"status": "ok", "platform": "hermes-agent"}
```

**Chat completion (non-streaming):**

```http
POST /v1/chat/completions
Authorization: Bearer <API_SERVER_KEY>
Content-Type: application/json
```

```json
{
  "model": "hermes-agent",
  "messages": [{"role": "user", "content": "Hello"}],
  "stream": false
}
```

**Bearer auth:** `Authorization: Bearer <token>` when `API_SERVER_KEY` is set (see upstream “Authentication” section).

---

## 6. Live data matrix (menu, providers, tools, skills, …)

| Data | Via Hermes HTTP API (official) | Via Hermes CLI (v0.8.0) | Usable for HAM “live dashboard” today |
|------|-------------------------------|---------------------------|----------------------------------------|
| **Menu / slash commands / autocomplete** | **No** dedicated discovery endpoint found | Interactive **curses** UIs (`hermes tools`, chat UI); **`hermes completion`** prints shell completion script | **Not API-exposed**; would require CLI parsing or future upstream API |
| **Providers** | **No** provider registry HTTP API in `api_server.py` | `hermes login`, `hermes auth`, `hermes model`, `hermes config` | **CLI / config** only for discovery |
| **Models (LLM routing)** | `GET /v1/models` returns **agent-as-model** stub | Actual model in `config.yaml` / env | **Partial**: HTTP gives frontend compatibility id only |
| **Tools** | Indirectly via **agent execution** in chat/responses/runs | `hermes tools list`, `hermes tools --summary` | **CLI** (HAM already uses `--summary` in allowlisted inventory) |
| **Skills** | **No** skills catalog HTTP in api_server | `hermes skills ...` | **CLI** + HAM vendored catalog |
| **Plugins** | **No** plugins HTTP in api_server | `hermes plugins list` | **CLI** |
| **MCP** | **No** MCP HTTP in api_server | `hermes mcp list` | **CLI** |
| **Sessions** | **Responses** API + storage; **Runs** API | `hermes sessions list`, `export`, etc. | **Mixed**: HTTP for API-driven sessions; **richer listing** via CLI |
| **Live activity / events** | **SSE**: chat stream; **`GET /v1/runs/.../events`** | Logs: `hermes logs` | **Yes (HTTP)** when gateway + API server enabled |
| **Dashboard / plugin extensions** | **No** separate “extension discovery” HTTP surface in inspected server | Plugin model is CLI-managed | **Not found** as reusable REST |

---

## 7. React/Ink TUI vs reusable APIs

- **Installed Hermes v0.8.0:** Interactive menus in the inspected CLI path use **Python `curses`** (e.g. tool configuration), not React/Ink.
- **No `ink` / React TUI dependencies** were found in a quick repo search of `~/.hermes/hermes-agent`.
- **Conclusion:** The **durable, reusable integration surface for HAM is the HTTP API server** (`api_server.py`) plus **documented CLI** — not a shared JSON-RPC layer tied to the TUI.

---

## 8. Auth, host, port, env, startup

| Item | Detail |
|------|--------|
| **Enable API server** | `API_SERVER_ENABLED=true` (typically in `~/.hermes/.env` per upstream docs) |
| **Auth** | `API_SERVER_KEY` → required `Authorization: Bearer ...` for clients; if empty, upstream notes local-only risk |
| **Bind** | `API_SERVER_HOST` (default `127.0.0.1`), `API_SERVER_PORT` (default **8642**) |
| **CORS** | `API_SERVER_CORS_ORIGINS` (comma-separated); wired in `gateway/config.py` |
| **Start** | Upstream: run **`hermes gateway`** after enabling — log line like `[API Server] API server listening on http://127.0.0.1:8642` |
| **Security note (upstream)** | API exposes **full agent toolset** including terminal; non-loopback bind requires key; HAM must **not** forward unauthenticated browser access to this surface |

---

## 9. Can HAM connect safely from the backend?

**Yes, with constraints:**

- HAM should use **server-side** `HERMES_GATEWAY_BASE_URL` + `HERMES_GATEWAY_API_KEY` (already aligned with `API_SERVER_KEY` conceptually).
- Traffic should stay **private** (loopback or VPC), matching [docs/DEPLOY_CLOUD_RUN.md](DEPLOY_CLOUD_RUN.md) patterns.
- **No** arbitrary user-controlled URLs from the browser; **allowlisted** HTTP paths and methods only.
- **Chat/completions** already equates to **invoking the full agent** (tools/terminal on the Hermes host) — that is **officially supported power**, not a separate “safe read-only RPC.”

---

## 10. Officially supported control actions (HTTP)

From the audited surface, **supported remote control** includes:

- **Agent turns:** `POST /v1/chat/completions`, `POST /v1/responses` (and streaming variants).
- **Long-running observability:** `POST /v1/runs` + `GET /v1/runs/{id}/events` (SSE).
- **Scheduled work:** `/api/jobs` CRUD + pause/resume/run.
- **Response store:** get/delete `/v1/responses/{id}`.

These are **high-trust** operations: they trigger Hermes’ agent core, not a read-only inventory.

**Read-only HTTP** suitable for dashboards without invoking the agent:

- `GET /health`, `GET /v1/health`
- `GET /v1/models` (limited semantics)
- Optionally **`GET /health/detailed`** if/when present on the deployed Hermes version (verify after upgrade)

---

## 11. CLI-only vs API-accessible today (summary)

| Category | CLI-only | API-accessible (when gateway + API server running) |
|----------|----------|-----------------------------------------------------|
| Tools / MCP / plugins / skills listing | Yes (`hermes tools`, `mcp`, `plugins`, `skills`) | No first-class REST list in v0.8.0 `api_server.py` |
| Provider / model configuration | Yes | Stub model list only |
| Session **history** management | Yes (`hermes sessions ...`) | Responses/runs/session semantics via HTTP where used |
| **Live event stream** | Logs CLI | **SSE** (chat stream, run events) |
| **Cron / jobs** | `hermes cron` family | **`/api/jobs`** REST |
| Interactive menus / autocomplete | curses / chat UI | **Not exposed** as REST |

---

## 12. Recommended implementation path (for later phases)

| Option | Fit |
|--------|-----|
| **A — Full live Hermes API integration** | Use **official REST + SSE** for everything Hermes exposes: chat, responses, runs, jobs, health. **Still** no JSON-RPC. **Does not** replace CLI for tools/MCP/plugins/skills **until** upstream adds read-only REST or HAM negotiates a supported extension. |
| **B — Broker over CLI + OpenAI chat + polling** | **Strong match to today’s facts:** keep allowlisted CLI for inventory; use existing HAM `http` chat adapter; poll `GET /health` and optionally **`GET /v1/runs/.../events`** when HAM orchestrates runs. Lowest risk. |
| **C — Hybrid with RPC stubs** | **Not recommended as “RPC”** — no Hermes JSON-RPC server found. **Hybrid** *is* appropriate: **HTTP** where official + **CLI** for discovery gaps + **typed stubs** for future endpoints (e.g. `/health/detailed`). |

**Recommendation:** **C relabeled as “Hybrid (HTTP + CLI)”** — implement **B** first, then widen HTTP usage along **A** per officially documented endpoints only.

---

## 13. Updated implementation checklist (fact-based)

1. **Version pin:** Record Hermes version in HAM docs (`v0.8.0` audited); re-run this audit after `hermes update` or when deploying next to a private Hermes VM.
2. **Confirm routes on target:** Hit `GET /health`, `GET /openapi.json` if exposed (not seen in v0.8.0 snippet — **no OpenAPI** in inspected adapter), and verify whether **`/health/detailed`** exists on the **deployed** build.
3. **HAM read path:** Extend **server-side** polling/SSE consumers only for **documented** paths; never pass through arbitrary paths from the browser.
4. **Inventory gap:** Continue **allowlisted CLI** for `tools --summary`, `plugins list`, `mcp list`, `status --all` until Hermes ships equivalent REST (or document a single supported extension).
5. **Runs/events:** Evaluate `POST /v1/runs` + SSE for “live activity” **instead of** mocking — subject to auth and resource limits (`_MAX_CONCURRENT_RUNS` in source).
6. **Jobs:** If HAM needs scheduled agent work, **`/api/jobs`** is the official remote surface (still high-trust).
7. **TUI:** Do not plan on React/Ink coupling; plan on **HTTP + CLI** only for v0.8.0 lineage.
8. **Doc drift:** Track published nousresearch.com docs vs installed commit; treat extra doc endpoints as **candidates** until verified in code.

---

## 14. Risks / unknowns

- **Local install is thousands of commits behind** — production Hermes on a pinned newer commit may add/remove routes (e.g. `/health/detailed`).
- **`GET /v1/models`** is intentionally **not** a full provider model matrix.
- **Enabling the API server** exposes powerful agent capabilities; HAM must keep **backend mediation** and **secrets off the frontend** (already HAM policy).
- **Audit machine:** API server not running — runtime behavior (exact SSE event shapes, job schemas) should be validated against a **live** `hermes gateway` with `API_SERVER_ENABLED=true` in a non-production environment.

---

## 15. Acceptance of Phase 0 constraints

- No HAM broker, dashboard, SSE layer, or action endpoints were added.
- No secrets were recorded in this document.
- No arbitrary shell was introduced beyond documented Hermes CLI invocations for inspection.

**End of Phase 0 audit.**
