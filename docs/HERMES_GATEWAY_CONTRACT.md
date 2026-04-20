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

**Note:** If `HERMES_GATEWAY_MODE` is unset, the adapter uses **`http`** when `HERMES_GATEWAY_BASE_URL` is non-empty, otherwise **`mock`**. Set `HERMES_GATEWAY_MODE=mock` explicitly to force mock even when a base URL is present.

## Out of scope for this contract revision

- `POST /v1/responses` and `previous_response_id`
- Runs API, Jobs API

## Security

Upstream often binds to loopback in dev docs. In production, place the gateway on a **private network** reachable only from the HAM API (e.g. **private GCE VM** + **Cloud Run VPC egress**); never expose an unauthenticated gateway to the public internet. Store **`HERMES_GATEWAY_API_KEY`** in **Secret Manager** (or equivalent) on Cloud Run, not in tracked files.
