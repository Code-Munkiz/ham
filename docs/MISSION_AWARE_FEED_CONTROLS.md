# Mission-aware feed controls

In Ham, **mission-aware** means the **live mission feed** and **operator controls** are always tied to a **single managed mission row** identified by `mission_registry_id`. The UI and APIs do not mix timelines or actions across missions.

## Behavior

- **Selection drives the feed** — After you pick a mission (for example in **Live Cloud Agent missions** on Operations or Conductor), the client loads **`GET /api/cursor/managed/missions/{mission_registry_id}/feed`**. That response is scoped to that mission only: bounded `events`, lifecycle, checkpoint summary, and optional artifacts (such as a PR link when observed).
- **Controls apply to the selected mission** — Sync-by-agent, cancel, and follow-up instructions are issued against the **currently selected** `mission_registry_id` (or the agent id derived from that row for sync). Changing the selection changes which feed and which mission receive the next action.
- **HAM vs Cursor** — Ham stores the managed record and feed events on the server; Cursor remains **upstream** for actual agent execution. The feed is a **HAM-side** view (persisted events plus synthesis when no stored feed exists yet — see `src/api/cursor_managed_missions.py`).

## Live feed transcript (Hermes Workspace)

The bounded feed returns time-ordered `events` (`assistant_message`, `thinking`, `user_message`, `tool_event`, `status`, and related kinds). **Live Cloud Agent missions** does not treat that array as the only UI model: **`buildMissionFeedTranscript()`** in `frontend/src/features/hermes-workspace/utils/missionFeedTranscript.ts` folds events into readable transcript blocks—merging consecutive Cursor `assistant_message` chunks per `source`, merging `thinking` and `user_message` runs, and mapping tool/status rows compactly—and **`applyTranscriptStreamingHints()`** can refine partial streaming tails when provider-native chunks arrive via the SDK bridge projection. Prefer display caps on the **returned** transcript lines, **not** by pre-slicing raw `events` (see module docstring).

Rendered in **`WorkspaceManagedMissionsLivePanel`** (Operations / Conductor). Chat flows may reuse the same helpers where a digest is inlined (**`WorkspaceChatScreen`**) and **`onMissionTranscriptDigest`** can summarize for auxiliary tabs.

This stack is **presentation-only**—authority stays on **`GET .../feed`**, persisted events, and server projection semantics (`sdk_stream_bridge` vs `rest_projection`; see **`docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`**). The browser still calls **HAM only**.

## API surface (scoped by mission)


| Route | Role |
|-------|------|
| `GET /api/cursor/managed/missions` | List missions; pick one `mission_registry_id` for detail/feed. |
| `GET /api/cursor/managed/missions/{mission_registry_id}` | Detail for one mission. |
| `GET /api/cursor/managed/missions/{mission_registry_id}/truth` | **Phase A:** screen-level HAM vs Cursor ownership table (JSON; not persisted). |
| `GET /api/cursor/managed/missions/{mission_registry_id}/correlation` | **Phase B:** optional `control_plane_ham_run_id` hint + embedded public control-plane run when linked. |
| `POST /api/cursor/managed/missions/{mission_registry_id}/hermes-advisory` | **Phase C:** operator-triggered `HermesReviewer` snapshot onto advisory fields (`HAM_MANAGED_MISSION_WRITE_TOKEN` + Bearer). |
| `PATCH /api/cursor/managed/missions/{mission_registry_id}/board` | **Phase D:** operator board lane `mission_board_state` ∈ `{backlog,active,archive}` (not a mission graph; token-gated). |
| `GET /api/cursor/managed/missions/{mission_registry_id}/feed` | **Feed** for that mission only (capped event list). |
| `POST /api/cursor/managed/missions/{mission_registry_id}/messages` | Follow-up instruction for **that** mission (when supported). |
| `POST /api/cursor/managed/missions/{mission_registry_id}/cancel` | Stop request for **that** mission (when supported). |

Frontend wiring lives in `frontend/src/features/hermes-workspace/adapters/managedMissionsAdapter.ts`, **`WorkspaceManagedMissionsLivePanel`**, and **`missionFeedTranscript.ts`** (builder + streaming hints above).

## Backend smoke (follow-up events)

Automated checks for **`POST .../messages`** and the resulting **feed** timeline live in `tests/test_managed_mission.py`:

- **`pytest tests/test_managed_mission.py -k followup -v`** — runs cases that assert `followup_instruction` is persisted, plus **`followup_forwarded`** when the Cursor client succeeds (mocked) and **`followup_rejected`** with `mission_followup_not_supported` when the provider returns 404-class errors (mocked).

## Related docs

- `docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md` — shipped vs partial managed mission behavior.
- `docs/CONTROL_PLANE_RUN.md` — control-plane runs vs managed mission records (separate substrates).
- `docs/examples/managed_cloud_agent_phases/README.md` — curl examples for truth, correlation, board, and Hermes advisory routes.
