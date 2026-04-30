# Ham pre-launch smoke checklist

Operational checklist adapted from orphaned `demo-checklist.md` on `rescue/bad-origin-main-1ffcb7b` (which targeted a different Hermes-agent layout). **Paths and bullets here refer to _this_ repository** (`Code-Munkiz/ham`). Use alongside `AGENTS.md`, `.cursor/rules/`, and subsystem docs—not as a substitute for CI.

---

## ✅ 1. Context / Memory (Context Engine)

**Primary:** [`src/memory_heist.py`](../src/memory_heist.py)

- [ ] **Repo scan & git state** — workspace truth assembly runs without exploding paths/config.
- [ ] **Session compaction / budgets** — no unbounded growth; caps honored where implemented.
- [ ] **Cross-platform paths** — `pathlib`-style paths in touched code; Windows + Linux clones behave.
- [ ] **Error handling** — Context Engine degrades cleanly on malformed sessions/config.

Focused tests: `python -m pytest tests/test_memory_heist.py -q`

---

## ✅ 2. Hermes supervision loop

**Primary:** [`src/hermes_feedback.py`](../src/hermes_feedback.py), [`src/swarm_agency.py`](../src/swarm_agency.py)

- [ ] **`HermesReviewer` / critique path** still wired where product expects it (see roadmap/gaps docs).
- [ ] **Per-role prompts** receive bounded `ProjectContext` (token discipline).
- [ ] **No CrewAI-style parallel orchestrators** pretending to replace Hermes supervision for this codebase.

Focused tests: `python -m pytest tests/test_hermes_feedback.py -q`

---

## ✅ 3. Execution safety (tools / missions)

**Primary:** [`src/tools/droid_executor.py`](../src/tools/droid_executor.py), mission & bridge docs under [`docs/`](../docs/)

- [ ] **Tool allowlists / policy limits** intact for delegated execution surfaces you ship.
- [ ] **Managed missions / Cursor cloud paths** gated by documented tokens and routing (see `docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`).
- [ ] **Timeouts / resource cleanup** for long-running adapters (browser, bridges) per recent changes.

Use targeted tests touching the subsystem you modified (registry, missions, router, etc.).

---

## ✅ 4. Constants & prompt budgets

- [ ] **Search for budgets / caps:** e.g. `rg "MAX_" src/ham src/api src --glob "*.py"` — large prompt paths should cite shared limits/skills (`docs/` + `.cursor/skills/` as applicable).
- [ ] **`memory_heist` / swarm** trimming behavior unchanged or intentionally updated with tests/docs.

Budget audit skill (when changing prompts): `.cursor/skills/prompt-budget-audit/SKILL.md`

---

## ✅ 5. Workspace UI (`frontend`)

**Primary:** [`frontend/`](../frontend/)

- [ ] **`npm run lint --prefix frontend`** (or `npm run lint` from `frontend/`) passes before release.
- [ ] **`npm run build --prefix frontend`** succeeds for production bundles.
- [ ] Smoke: dashboard loads, `/api/status` reachable from dev proxy (`AGENTS.md` § Cursor Cloud quick start).

---

## 🚀 Quick grep-based spot checks

From repo root (POSIX Shell; adapt for PowerShell):

```bash
rg -n "compact" src/memory_heist.py | head
rg -n "HermesReviewer|critique" src/hermes_feedback.py | head
rg -n "MAX_" src/ham src/api --glob "*.py" | head
```

Windows PowerShell equivalents:

```powershell
Select-String -Path src/memory_heist.py -Pattern "compact" | Select-Object -First 5
Select-String -Path src/hermes_feedback.py -Pattern "HermesReviewer","critique" | Select-Object -First 5
```

---

## 📝 Notes

- **Hermes naming** — this codebase shares Hermes *concepts* (supervision, reviewer) but file layout differs from upstream Hermes-Agent monoliths.
- **`rescue/bad-origin-main-1ffcb7b`** carried a **`ham` git submodule pointer** (`0ff29177…`) pointing at unrelated history—**do not** add that submodule to `main`; it belongs to the mistaken force-push lineage only.

**Last updated:** April 2026 (recovery port)
