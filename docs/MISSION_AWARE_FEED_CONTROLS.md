# Mission-aware feed controls

In Ham, **mission-aware** means the **live mission feed** and **operator controls** are always tied to a **single managed mission row** identified by `mission_registry_id`. The UI and APIs do not mix timelines or actions across missions.

## Behavior

- **Selection drives the feed** — After you pick a mission (for example in **Live Cloud Agent missions** on Operations or Conductor), the client loads **`GET /api/cursor/managed/missions/{mission_registry_id}/feed`**. That response is scoped to that mission only: bounded `events`, lifecycle, checkpoint summary, and optional artifacts (such as a PR link when observed).
- **Controls apply to the selected mission** — Sync-by-agent, cancel, and follow-up instructions are issued against the **currently selected** `mission_registry_id` (or the agent id derived from that row for sync). Changing the selection changes which feed and which mission receive the next action.
- **HAM vs Cursor** — Ham stores the managed record and feed events on the server; Cursor remains **upstream** for actual agent execution. The feed is a **HAM-side** view (persisted events plus synthesis when no stored feed exists yet — see `src/api/cursor_managed_missions.py`).

## Live feed transcript (client)

The raw feed is a **bounded, time-ordered list of events** (`assistant_message`, `thinking`, `user_message`, `tool_event`, `status`, and other kinds). Hermes Workspace does **not** render that list verbatim as the primary narrative: it reduces events into a **transcript** of blocks (assistant, thinking, user, tool, status, raw) so the live panel reads like a thread.

- **Builder:** `buildMissionFeedTranscript()` in `frontend/src/features/hermes-workspace/utils/missionFeedTranscript.ts` — sorts by `time` + id, merges consecutive Cursor `assistant_message` chunks that share the same `source`, merges consecutive `thinking` and `user_message` runs, and maps `tool_event` / status-like rows into compact rows. Pass the **full** bounded `events` array from the feed response; apply display caps on the **returned** transcript items, not by pre-slicing `events` (see module docstring).
- **Surfaces:** `WorkspaceManagedMissionsLivePanel` (Operations / Conductor **Live Cloud Agent missions**) and chat-side digest UI that imports the same helpers (`WorkspaceChatScreen.tsx`).

This layer is **presentation only**; authority and persistence remain on the mission feed API and server-side projection (`docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`).

## API surface (scoped by mission)

| Route | Role |
|-------|------|
| `GET /api/cursor/managed/missions` | List missions; pick one `mission_registry_id` for detail/feed. |
| `GET /api/cursor/managed/missions/{mission_registry_id}` | Detail for one mission. |
| `GET /api/cursor/managed/missions/{mission_registry_id}/feed` | **Feed** for that mission only (capped event list). |
| `POST /api/cursor/managed/missions/{mission_registry_id}/messages` | Follow-up instruction for **that** mission (when supported). |
| `POST /api/cursor/managed/missions/{mission_registry_id}/cancel` | Stop request for **that** mission (when supported). |

Frontend wiring lives in `frontend/src/features/hermes-workspace/adapters/managedMissionsAdapter.ts`, **`WorkspaceManagedMissionsLivePanel`**, and **`missionFeedTranscript.ts`** (transcript builder above).

## Backend smoke (follow-up events)

Automated checks for **`POST .../messages`** and the resulting **feed** timeline live in `tests/test_managed_mission.py`:

- **`pytest tests/test_managed_mission.py -k followup -v`** — runs cases that assert `followup_instruction` is persisted, plus **`followup_forwarded`** when the Cursor client succeeds (mocked) and **`followup_rejected`** with `mission_followup_not_supported` when the provider returns 404-class errors (mocked).

## Related docs

- `docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md` — shipped vs partial managed mission behavior.
- `docs/CONTROL_PLANE_RUN.md` — control-plane runs vs managed mission records (separate substrates).
