# Managed Cloud Agent missions — phased API examples

These examples assume the Ham API is listening on `http://127.0.0.1:8000` (see `scripts/run_local_api.py`) and that you have a valid `mission_registry_id` from `GET /api/cursor/managed/missions`.

Replace:

- `MISSION_ID` — UUID from list/detail.
- `TOKEN` — same value as server env `HAM_MANAGED_MISSION_WRITE_TOKEN`.

When Clerk is enabled for the operator session, send the Clerk JWT on `Authorization` and the HAM token on `X-Ham-Operator-Authorization` (see `.env.example` notes for other write flows).

## Phase A — Truth table (read)

```bash
curl -sS "http://127.0.0.1:8000/api/cursor/managed/missions/MISSION_ID/truth" | jq .
```

## Phase B — Control plane correlation (read)

```bash
curl -sS "http://127.0.0.1:8000/api/cursor/managed/missions/MISSION_ID/correlation" | jq .
```

When `control_plane_linked` is true, the response includes `control_plane_run` with the same bounded fields as `GET /api/control-plane-runs/{ham_run_id}`.

## Phase C — Hermes advisory (write)

Runs a capped `HermesReviewer.evaluate()` and stores advisory fields on the mission row only.

```bash
curl -sS -X POST \
  "http://127.0.0.1:8000/api/cursor/managed/missions/MISSION_ID/hermes-advisory" \
  -H "Authorization: Bearer TOKEN" | jq .
```

## Phase D — Board lane (write)

Operator labels only (`backlog` | `active` | `archive`). Not a mission graph.

```bash
curl -sS -X PATCH \
  "http://127.0.0.1:8000/api/cursor/managed/missions/MISSION_ID/board" \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mission_board_state":"archive"}' | jq .
```

## Demo JSON files

Example **responses** (for docs/tests/fixtures) live beside this README:

- `truth.example.json`
- `correlation_linked.example.json`
