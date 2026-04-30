# Cloud Agent routing smoke note (Workspace Chat)

This note is for **manual smoke** and orientation: how **Hermes Workspace Chat** gets **Cursor Cloud Agent** preview/launch/status intents to the server **through the same stream** the UI already uses for chat.

## Transport

- **Workspace Chat** (`WorkspaceChatScreen`) talks to the API **only** via **`POST /api/chat/stream`** (NDJSON: `session` → optional `delta` lines → `done` or `error`). The browser helper defaults `enable_operator: true` on that request so the server may run the chat **operator** path before calling the LLM.

## Routing (server, before streaming tokens)

On each turn, when the last message is from the user and the request has `enable_operator` enabled, `post_chat_stream` in `src/api/chat.py` invokes `process_operator_turn` (full operator) or, when **`HAM_CHAT_OPERATOR`** is off (`false` / `0` / … per `operator_enabled()` in `src/ham/chat_operator.py`), `process_agent_router_turn` (Cloud Agent router intents only). Both paths share `try_heuristic_intent` in `src/ham/chat_operator.py`, which calls `route_agent_intent` (`src/ham/agent_router.py`) and maps results such as **`agent_launch`** to operator phases like **`cursor_agent_preview`** / **`cursor_agent_launch`** / **`cursor_agent_status`**.

If that step **fully handles** the turn (preview text, block, or other operator-only reply), the response is **short-circuited**: the stream emits **`session`** then **`done`** with **`operator_result`** populated and **no** `delta` token chunks.

If the turn is **not** handled by the operator/router, the handler continues into the normal **LLM streaming** path (`delta` lines then `done`).

## Confirm launch and tokens

Structured **preview → confirm → launch** uses the **`operator`** field on the chat body (e.g. `phase=cursor_agent_launch`, `confirmed=true`, digest fields) plus the **HAM operator** bearer where required. See **`docs/HAM_CHAT_CONTROL_PLANE.md`** and **`docs/HARNESS_PROVIDER_CONTRACT.md`** for the full contract; direct **`POST /api/cursor/agents/launch`** remains available for CI/scripts outside chat.

## Mission-scoped Workspace Chat

From **Hermes Workspace** managed-mission rows, the UI links to **`/workspace/chat?mission_id=<mission_registry_id>`** (UUID). That query parameter keeps the chat surface tied to the selected managed mission (deep links and panel actions use the same shape). Read-only mission timeline and operator actions use **`GET /api/cursor/managed/missions/{id}/feed`** and related routes under **`/api/cursor/managed/missions/*`** — see **`docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`**.

## Optional curl smoke

Send a user message that matches an agent intent (with `project_id` set if needed) to **`POST /api/chat/stream`** with `Content-Type: application/json` and `Accept: application/x-ndjson`. Inspect the final **`done`** line for **`operator_result`** when the operator path fires.
