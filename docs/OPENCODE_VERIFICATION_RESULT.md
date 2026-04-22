# OpenCode verification — execution log (automated host)

This file records an **attempt** to run [`OPENCODE_VERIFICATION.md`](OPENCODE_VERIFICATION.md) from the HAM development environment used for this pass.

**Date (reference):** 2026-04-11  
**Host context:** Linux; `opencode` **not** on `PATH` (`command -v opencode` → not found).

**Result:** **No runtime evidence bundle was produced** on this host. Verification **must be re-run** on a machine where OpenCode is installed (see playbook §2–3). Until that evidence exists, treat OpenCode HAM v1 as **not substantiated** by execution.

**Do not delete** this note when adding a real bundle; add a sibling folder or dated result file for the successful pass instead.

---

## Commands not executed (blocked at binary)

The following from the playbook could not run:

- `opencode -v`, `opencode --version`
- `opencode auth list`
- `opencode run --help`
- All `opencode run` probes

**Handoff:** copy the command blocks from [`OPENCODE_VERIFICATION.md`](OPENCODE_VERIFICATION.md) §3 on a host with OpenCode installed, then produce the artifact list in §4 and fill §10.
