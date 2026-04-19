# Hermes API Server — HAM adapter contract

This document pins how the **HAM server-side adapter** talks to the upstream **Hermes Agent API server**. The browser **never** uses these URLs or terms.

**Canonical upstream documentation:** [API Server | Hermes Agent](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server) (verify before upgrading gateway versions).

## Pinned upstream surface (non-streaming MVP)

| Item | Value |
|------|--------|
| Default base URL | `http://127.0.0.1:8642` (configurable via `HERMES_GATEWAY_BASE_URL`) |
| Chat completions path | `POST {base}/v1/chat/completions` |
| Auth | `Authorization: Bearer <API_SERVER_KEY>` (HAM env: `HERMES_GATEWAY_API_KEY`) |
| Request body (MVP) | OpenAI-compatible JSON: `model`, `messages`, **`stream: false`** |
| Response (success) | `choices[0].message.content` — assistant text |

### Example upstream request

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
  "stream": false
}
```

### Example upstream response (success)

```json
{
  "choices": [
    {
      "index": 0,
      "message": {"role": "assistant", "content": "..."},
      "finish_reason": "stop"
    }
  ]
}
```

## HAM adapter modes

| Mode | Env | Behavior |
|------|-----|----------|
| `mock` | `HERMES_GATEWAY_MODE=mock` | No HTTP; deterministic local reply for UI/dev. |
| `openrouter` | `HERMES_GATEWAY_MODE=openrouter` | LiteLLM completion to [OpenRouter](https://openrouter.ai/) (`OPENROUTER_API_KEY`, `DEFAULT_MODEL` or `HERMES_GATEWAY_MODEL` as OpenRouter slug). Browser still only talks to Ham; keys stay server-side. |
| `http` | `HERMES_GATEWAY_MODE=http` (default when unset for production intent) | `httpx` POST to `/v1/chat/completions` as above. |

**Note:** If `HERMES_GATEWAY_MODE` is unset, the adapter uses **`http`** when `HERMES_GATEWAY_BASE_URL` is non-empty, otherwise **`mock`** (safe local default). Set `HERMES_GATEWAY_MODE=mock` explicitly to force mock even when a base URL is present.

## Out of scope for this contract revision

- SSE / `stream: true`
- `POST /v1/responses` and `previous_response_id`
- Runs API, Jobs API

## Security

Upstream binds to loopback by default. In production, place the gateway on a **private network** reachable only from the HAM API; never expose unauthenticated gateway to the public internet (see upstream security notes).
