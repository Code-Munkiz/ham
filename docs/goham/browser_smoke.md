# GoHAM managed browser — smoke checklist (historical / future)

**Current repo state (2026):** **Workspace chat** no longer drives a **GoHAM Mode** observe/research loop against the Electron shell (**Linux-desktop execution UI was removed**). **HAM Desktop** still implements **main-process** Phase **4A/4B** Local Control browsers where platform policy allows (see [`docs/desktop/local_control_v1.md`](../desktop/local_control_v1.md)) — **separate** from this document’s checklist.

Use **server-side** **`/api/browser*`** ([`src/api/browser_runtime.py`](../../src/api/browser_runtime.py)) for Playwright-backed automation **on the API host**.

The dedicated planning API **`POST /api/goham/planner`** remains on the Ham API as an optional substrate—**not** wired to Desktop browser automation here.

Below is a **retained checklist** for any future retargeted **GoHAM orchestration surface** (not required by current Electron wiring).

## Reference scenarios (not executed in-tree)

- Bounded page observe from a dedicated profile (no default browser cookies).
- Pause / resume / take-over style controls during long research (if reintroduced outside Electron local-control).
- Evidence honesty: `insufficient_evidence` / bounded snippets only.

## Planner API (may stay enabled)

Optional LLM-assisted proposals may use **`POST /api/goham/planner/next-action`** when gated by server env — independent of Desktop.
