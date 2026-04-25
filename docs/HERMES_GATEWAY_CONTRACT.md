# Hermes API Server — HAM adapter contract

This document pins how the **HAM server-side adapter** talks to the upstream **Hermes Agent API server**. The browser **never** uses these URLs or terms.

**Canonical upstream documentation:** [API Server | Hermes Agent](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server) (verify before upgrading gateway versions).

## Pinned upstream surface (chat completions)

| Item | Value |
|------|--------|
| Default base URL | `http://127.0.0.1:8642` (configurable via `HERMES_GATEWAY_BASE_URL`) |
| Chat completions path | `POST {base}/v1/chat/completions` |
| Auth | `Authorization: Bearer <API_SERVER_KEY>` (HAM env: `HERMES_GATEWAY_API_KEY`) |
| Request body (HAM `http` mode) | OpenAI-compatible JSON: `model`, `messages`, **`stream: true`** |
| Response (HAM `http` mode) | **Server-Sent Events**: lines `data: {json}` with OpenAI-style **`choices[0].delta.content`** chunks until `data: [DONE]` |

HAM’s implementation lives in [`src/integrations/nous_gateway_client.py`](../src/integrations/nous_gateway_client.py): it POSTs with **`stream: true`**, reads the SSE stream, and yields text deltas. Non-streaming (`stream: false`) **one-shot** JSON responses (`choices[0].message.content`) are **not** what the current adapter expects for `http` mode.

### Example upstream request (HAM behavior)

```http
POST /v1/chat/completions
Authorization: Bearer <secret>
Content-Type: application/json
```

```json
{
  "model": "hermes-agent",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "stream": true
}
```

### Example streamed event line (conceptual)

```text
data: {"choices":[{"delta":{"content":"Hi"}}]}
```

If a given Hermes build does not support **`stream: true`** on this path, the adapter will need a follow-up change or you must use a compatible Hermes version.

## HAM adapter modes

| Mode | Env | Behavior |
|------|-----|----------|
| `mock` | `HERMES_GATEWAY_MODE=mock` | No HTTP; deterministic local reply for UI/dev (body contains **`Mock assistant reply`**). |
| `openrouter` | `HERMES_GATEWAY_MODE=openrouter` | LiteLLM streaming to [OpenRouter](https://openrouter.ai/) (`OPENROUTER_API_KEY`, `DEFAULT_MODEL` or `HERMES_GATEWAY_MODEL` as OpenRouter slug). Browser still only talks to Ham; keys stay server-side. |
| `http` | `HERMES_GATEWAY_MODE=http` (or unset with `HERMES_GATEWAY_BASE_URL` set) | `httpx` streaming POST to `/v1/chat/completions` as above. |

### HTTP mode: model id and fallback (HAM)

| Env | Role |
|-----|------|
| `HERMES_GATEWAY_MODEL` | `model` field on `POST /v1/chat/completions`. OpenRouter-style slugs (e.g. `minimax/minimax-m2.5:free`) are valid **only if** your Hermes (or its LiteLLM layer) accepts them. The placeholder `hermes-agent` usually means **routing is defined inside Hermes** (profile / agent config on the Hermes host — not in this repo). |
| `HAM_CHAT_FALLBACK_MODEL` | Optional alternate `model` for **one retry** of the same request. Retry runs only if **no assistant token has been yielded yet** (HAM does not switch models mid-stream). See [`src/integrations/nous_gateway_client.py`](../src/integrations/nous_gateway_client.py). |

**When fallback retry is eligible** (primary failed before any streamed content):

- **HTTP status** on the gateway response: **429**, **502**, **503**, or **504** (mapped to `UPSTREAM_REJECTED` with `http_status` set).
- **Adapter abort codes** (no successful HTTP body, or stream ended early): **`UPSTREAM_TIMEOUT`**, **`UPSTREAM_UNAVAILABLE`**, **`STREAM_STALLED`**, **`STREAM_MAX_DURATION`**.

**Stream guard tunables** (optional; HTTP streaming path only):

| Env | Role |
|-----|------|
| `HAM_CHAT_HTTP_STALL_SEC` | Seconds without **SSE progress** (new `data:` lines / content deltas) before raising **`STREAM_STALLED`**. Default **45** if unset or invalid. |
| `HAM_CHAT_HTTP_STREAM_MAX_SEC` | Wall-clock cap on a single streaming read. If set and valid, used as a **minimum of 30** seconds; if unset, HAM derives a default from the request timeout (at least **300** seconds in typical configs). Breach raises **`STREAM_MAX_DURATION`**. |

Validate model strings against your Hermes deployment before rolling out on Cloud Run.

**Note:** If `HERMES_GATEWAY_MODE` is unset, the adapter uses **`http`** when `HERMES_GATEWAY_BASE_URL` is non-empty, otherwise **`mock`**. Set `HERMES_GATEWAY_MODE=mock` explicitly to force mock even when a base URL is present.

### HAM dashboard chat stream (`POST /api/chat/stream`, NDJSON)

The browser calls **Ham** only; Ham may proxy to the gateway modes above. NDJSON lines use `type`: `session`, optional `delta`, then a terminal `done` (or `error` for non-gateway/session failures).

When the **model gateway** raises after fallback is exhausted (or in modes without retry), Ham **does not** end the stream with a terminal `error` line for that case. It appends a **safe, user-facing** assistant `content` to the session, then emits **`done`** with:

- `messages` — includes the new assistant turn (no raw upstream text).
- `gateway_error` — optional object `{ "code": "<GatewayCallError code>" }` so clients can detect failure without scraping copy.

Other failures (e.g. missing session during streaming) may still use a terminal **`error`** line. See [`src/api/chat.py`](../src/api/chat.py).

## Out of scope for this contract revision

- `POST /v1/responses` and `previous_response_id`
- Runs API, Jobs API

## Security

Upstream often binds to loopback in dev docs. In production, place the gateway on a **private network** reachable only from the HAM API (e.g. **private GCE VM** + **Cloud Run VPC egress**); never expose an unauthenticated gateway to the public internet. Store **`HERMES_GATEWAY_API_KEY`** in **Secret Manager** (or equivalent) on Cloud Run, not in tracked files.
