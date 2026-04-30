# Cursor provider feed projection

When the Ham API serves **`GET /api/cursor/managed/missions/{mission_registry_id}/feed`**, it may **enrich** the mission timeline with events derived from Cursor’s **agent conversation** API. That path is intentionally **not** a verbatim relay of provider JSON: it is a **safe projection** into Ham’s bounded mission-feed shape.

## Why projection exists

- **Cursor** remains the source of truth for execution and full conversation content upstream.
- **Ham** stores a **durable, operator-safe** mission feed (checkpoints, follow-ups, and short status lines) suitable for list/detail APIs and UI without exposing secrets or unbounded provider payloads.

## What the server does (high level)

1. **Refresh** the latest Cursor agent payload (status) and **observe** the managed mission row (`observe_mission_from_cursor_payload`).
2. **Fetch** the Cursor agent conversation payload for the same `cursor_agent_id`.
3. **Map** that payload through `map_cursor_conversation_to_feed_events` in `src/ham/cursor_provider_adapter.py`, producing normalized feed events with stable synthetic `event_id`s.
4. **Merge** only **new** projected events into `mission_feed_events` (deduped by `event_id`) and persist when something changed.

Implementation references: `_sync_provider_projection` and `get_managed_mission_feed` in `src/api/cursor_managed_missions.py`.

## Safety and bounds

- **Redaction:** Known secret patterns (for example Cursor-style and bearer token shapes) are replaced before text is stored or returned.
- **Truncation:** Per-event message text is capped (short preview, not full thread).
- **Volume:** Projection keeps only the **tail** of mapped events from a single conversation fetch; the feed response also caps how many events are returned. These limits are **defense in depth** against oversized provider responses.

## Fallback when provider conversation is unavailable

The feed endpoint **always** returns a normal response body when the mission exists; projection is **best-effort**. If the Cursor **conversation** call fails (HTTP error from Cursor, network, etc.), the server skips merging new projected events and sets **`provider_projection_state`** to **`fallback`** with **`provider_projection_reason`** like `provider_conversation_unavailable:<status>`.

In that case:

- **Persisted feed rows** (`mission_feed_events` already on disk) are still returned unchanged.
- If there are **no** persisted rows, **`events`** falls back to **HAM-built** lines: mission started, then checkpoint entries from the managed mission record (same path as when projection never ran).

Related fallbacks from the same sync: missing API key → `provider_key_missing`; failure on the **agent status** GET before conversation is attempted → `provider_status_unavailable:...` (conversation is not fetched). When projection completes with no error, **`provider_projection_state`** is **`ok`** and **`provider_projection_reason`** is null.

## Capability matrix

`provider_capability_matrix()` in the same adapter module documents how Ham advertises **conversation_state** and related capabilities relative to Cursor (for example `implemented_now: "safe_feed_projection"` vs future session-resume work). Treat that structure as **declared intent**, not a guarantee of real-time parity with Cursor’s own UI.

## Related

- `docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md` — managed mission scope and roadmap.
- `docs/CONTROL_PLANE_RUN.md` — control-plane runs are a **separate** substrate from managed mission feed rows.
