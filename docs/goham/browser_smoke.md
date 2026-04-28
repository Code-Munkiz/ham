# GoHAM managed browser — smoke checklist (historical / future)

**Current repo state (2026):** HAM Desktop **no longer** ships Electron IPC for managed Chromium, CDP observe flows, or workspace **GoHAM Mode** chat execution. The dedicated planning API **`POST /api/goham/planner`** remains on the Ham API as an optional, future-safe substrate (not tied to Desktop).

Use **server-side** **`/api/browser*`** ([`src/api/browser_runtime.py`](../../src/api/browser_runtime.py)) for Playwright-backed automation on the API host.

Below is a **retained checklist** for any future retargeted GoHAM surface (not shipped in this tree).

## Reference scenarios (not executed in-tree)

- Bounded page observe from a dedicated profile (no default browser cookies).
- Pause / resume / take-over style controls during long research (if reintroduced outside Electron local-control).
- Evidence honesty: `insufficient_evidence` / bounded snippets only.

## Planner API (may stay enabled)

Optional LLM-assisted proposals may use **`POST /api/goham/planner/next-action`** when gated by server env — independent of Desktop.
