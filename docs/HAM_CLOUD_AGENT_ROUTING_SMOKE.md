# Workspace Chat → Cursor Cloud Agent routing (smoke note)

**Scope:** How **Hermes Workspace Chat** routes **Cursor Cloud Agent** preview and launch intents through **`POST /api/chat/stream`**. For full operator semantics, tokens, and NDJSON shapes, see [`HAM_CHAT_CONTROL_PLANE.md`](HAM_CHAT_CONTROL_PLANE.md) and [`HERMES_GATEWAY_CONTRACT.md`](HERMES_GATEWAY_CONTRACT.md) § dashboard chat stream.

## Path

1. **Browser:** Hermes Workspace chat (`WorkspaceChatScreen`) sends turns only via **`postChatStream`** in `frontend/src/lib/ham/api.ts` (adapter: `frontend/src/features/hermes-workspace/workspaceAdapters.ts`). There is no separate VM route for streaming chat.

2. **API:** `post_chat_stream` in `src/api/chat.py` handles **`POST /api/chat/stream`**. When the last message is from the user and **`enable_operator`** is on (default), the server runs **`process_operator_turn`** or **`process_agent_router_turn`** from `src/ham/chat_operator.py` **before** invoking the LLM gateway.

3. **Cloud agent intents:** Natural language or structured **`operator`** payloads map to **`cursor_agent_preview`**, **`cursor_agent_launch`**, and **`cursor_agent_status`**. Preview returns structured fields (including digest / base revision) and may set **`pending_cursor_agent`** on the **`operator_result`** in the stream **`done`** line. Launch requires confirmation, matching digest/revision, and **`HAM_CURSOR_AGENT_LAUNCH_TOKEN`** (often via **`X-Ham-Operator-Authorization`** when the session uses Clerk). See [`HARNESS_PROVIDER_CONTRACT.md`](HARNESS_PROVIDER_CONTRACT.md) for the commit gate and audit story.

4. **Stream shape:** NDJSON lines: **`session`** → optional token **`delta`** lines (or an operator-only short stream) → **`done`** with **`messages`**, **`actions`**, and **`operator_result`** (or **`error`**).

## Quick smoke idea

With a valid dashboard session (or dev auth as your environment documents), POST a user message to **`/api/chat/stream`** with **`Content-Type: application/json`**, body matching **`ChatRequest`** (see `src/api/chat.py`), including **`project_id`** when testing preview. Inspect the final **`done`** object for **`operator_result.intent`** and any **`pending_cursor_agent`** block—no separate “launch chat” endpoint is required for Workspace Chat routing.
