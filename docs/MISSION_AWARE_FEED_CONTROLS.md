# Mission-aware feed controls

In Ham, **mission-aware** means the **live mission feed** and **operator controls** are always tied to a **single managed mission row** identified by `mission_registry_id`. The UI and APIs do not mix timelines or actions across missions.

## Behavior

- **Selection drives the feed** — After you pick a mission (for example in **Live Cloud Agent missions** on Operations or Conductor), the client loads **`GET /api/cursor/managed/missions/{mission_registry_id}/feed`**. That response is scoped to that mission only: bounded `events`, lifecycle, checkpoint summary, and optional artifacts (such as a PR link when observed).
- **Controls apply to the selected mission** — Sync-by-agent, cancel, and follow-up instructions are issued against the **currently selected** `mission_registry_id` (or the agent id derived from that row for sync). Changing the selection changes which feed and which mission receive the next action.
- **HAM vs Cursor** — Ham stores the managed record and feed events on the server; Cursor remains **upstream** for actual agent execution. The feed is a **HAM-side** view (persisted events plus synthesis when no stored feed exists yet — see `src/api/cursor_managed_missions.py`).

## Live feed transcript (Hermes Workspace)

The **Live Cloud Agent missions** panel does not only show a raw event list: it builds a **read-only transcript** from the bounded feed `events` so operators see a single thread (assistant turns, optional thinking blocks, user follow-ups, tool/status lines) with streaming hints when the bridge supplies partial turns. Logic lives in `frontend/src/features/hermes-workspace/utils/missionFeedTranscript.ts` (`buildMissionFeedTranscript`, `applyTranscriptStreamingHints`); **`WorkspaceManagedMissionsLivePanel`** renders it and can surface a short digest for the Outputs tab via `onMissionTranscriptDigest`.

## API surface (scoped by mission)

| Route | Role |
|-------|------|
| `GET /api/cursor/managed/missions` | List missions; pick one `mission_registry_id` for detail/feed. |
| `GET /api/cursor/managed/missions/{mission_registry_id}` | Detail for one mission. |
| `GET /api/cursor/managed/missions/{mission_registry_id}/feed` | **Feed** for that mission only (capped event list). |
| `POST /api/cursor/managed/missions/{mission_registry_id}/messages` | Follow-up instruction for **that** mission (when supported). |
| `POST /api/cursor/managed/missions/{mission_registry_id}/cancel` | Stop request for **that** mission (when supported). |

Frontend wiring lives in `frontend/src/features/hermes-workspace/adapters/managedMissionsAdapter.ts`, **`WorkspaceManagedMissionsLivePanel`**, and `frontend/src/features/hermes-workspace/utils/missionFeedTranscript.ts` (transcript merge from feed events).

## Backend smoke (follow-up events)

Automated checks for **`POST .../messages`** and the resulting **feed** timeline live in `tests/test_managed_mission.py`:

- **`pytest tests/test_managed_mission.py -k followup -v`** — runs cases that assert `followup_instruction` is persisted, plus **`followup_forwarded`** when the Cursor client succeeds (mocked) and **`followup_rejected`** with `mission_followup_not_supported` when the provider returns 404-class errors (mocked).

## Related docs

- `docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md` — shipped vs partial managed mission behavior.
- `docs/CONTROL_PLANE_RUN.md` — control-plane runs vs managed mission records (separate substrates).
