# Managed mission lifecycle (HAM record)

This note explains how Ham **polishes and persists** Cloud Agent mission state in the `ManagedMission` store. It complements the product roadmap in [`ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md).

## Who owns what

- **Cursor** owns execution: agent status strings and conversation live upstream.
- **HAM** owns a **durable, bounded, server-side record**: one JSON file per `mission_registry_id`, updated when Ham observes Cursor (for example via `observe_mission_from_cursor_payload` on agent GET / proxy paths). The record is **observed truth**, not a second orchestrator.

## Two layers: lifecycle vs checkpoint

The model separates a coarse **lifecycle** from a finer **checkpoint** for UI and audits:

| Field | Role |
|--------|------|
| **`mission_lifecycle`** | `open`, `succeeded`, `failed`, or `archived`. Derived from mapped Cursor status. |
| **`mission_checkpoint_*`** | Steps such as `queued`, `launched`, `running`, `blocked`, `pr_opened`, `completed`, `failed` — derived from status tokens, PR hints, deploy/review context, etc. |

Checkpoints can move through intermediate states while lifecycle stays `open` until a terminal mapping applies.

## Lifecycle polish (terminal stickiness)

`map_cursor_to_mission_lifecycle` in `src/persistence/managed_mission.py` maps raw Cursor status into the four lifecycle values. **Polish** here means:

- **Terminal states are sticky.** Once `mission_lifecycle` is `succeeded`, `failed`, or `archived`, Ham does **not** revert to `open` on noisy or ambiguous provider payloads. That keeps the stored record stable for operators and APIs.
- **Non-terminal** observations keep the mission in `open` with a short `status_reason_last_observed` (for example `mapped:RUNNING`) so debugging stays honest without overwriting a finished outcome.

## Checkpoints and events

`src/ham/managed_mission_wiring.py` derives `mission_checkpoint_latest` (and optional capped `mission_checkpoint_events`) from the same observed fields. When the derived checkpoint changes, Ham can append a bounded history entry — useful for “what did we think happened when?” without storing full transcripts.

## Where to read code

- Lifecycle mapping and types: `src/persistence/managed_mission.py` (`MissionLifecycle`, `map_cursor_to_mission_lifecycle`, `ManagedMission`).
- Create/update on observe: `src/ham/managed_mission_wiring.py` (`observe_mission_from_cursor_payload`, `_with_derived_checkpoint`).
- Read APIs: `src/api/cursor_managed_missions.py` and related `cursor_*` routes.

For gaps and future work (correlation with `ControlPlaneRun`, UI copy, optional Hermes hooks), see the roadmap file linked above.
