# OpenCode real-host verification (pre-harness)

## 1. Purpose / scope

This document is the **authoritative playbook** for collecting **real runtime evidence** for the **OpenCode CLI** *before* any HAM **OpenCode harness** implementation (no `opencode_workflow.py`, no `ControlPlaneProvider` / `ControlPlaneRun` / operator changes).

- **OpenCode in HAM today** is only a **planned** harness (see `registry_status=planned_candidate` and `opencode_cli` in [`docs/HARNESS_PROVIDER_CONTRACT.md`](HARNESS_PROVIDER_CONTRACT.md) and [`src/ham/harness_capabilities.py`](../src/ham/harness_capabilities.py)). **Public docs are not enough** to design an honest v1.
- **Expected HAM v1 direction** (if evidence supports it) is a **single bounded subprocess** using **`opencode run` only** — not TUI, not `opencode serve` / `web`, not `opencode run --attach`, and not `opencode` default interactive mode, not `--continue` / session resume.

Order of work: **harness contract + read-only registry** (done) → **this verification pass on a real host** → **narrowest honest harness design** → **only then** implementation.

---

## 2. Preconditions

Before running the checklist:

| Requirement | Why |
|-------------|-----|
| A **host** where the `opencode` binary is **installed** and on `PATH` (or a documented absolute path) | The CI/sandbox may not have OpenCode; evidence must come from a real install. |
| A **test repository directory** (clone of a small repo or this HAM repo) as `cd` target | `opencode run` is cwd-sensitive; HAM v1 will bind to a project root. |
| **Auth / providers** configured for OpenCode (e.g. `opencode auth login`, keys in env or per OpenCode’s docs) | Smoke runs that call a model will fail without it. |
| **Permission** to save **redacted** stdout/stderr to files for review | No secrets in shared artifacts. |
| Run on the **same or closest** OS image to the **intended HAM API execution environment** (e.g. same Linux base as Cloud Run worker if that is where launch would run) | Reduces “works on my laptop” skew. |

If any precondition fails, record that in the handoff (§10) and treat **go** as **no-go** until unblocked.

---

## 3. Exact verification commands

Set `TEST_REPO` to an absolute path (example: this repo root on your machine).

```bash
export TEST_REPO="/path/to/test/repo"   # edit
```

**Note on timing:** The examples use GNU `time` (`/usr/bin/time` on many Linux distros) with `-f`. On **macOS**, the stock `time` is a shell builtin with different options — use the **wall-clock** method in §3.1 instead, or install GNU time as `gtime`.

### 3.1 Binary / version

```bash
command -v opencode
opencode -v
opencode --version
```

### 3.2 Auth / readiness

```bash
opencode auth list
opencode auth ls || true
```

### 3.3 CLI surface

```bash
opencode run --help
```

### 3.4 Success probe (plain output)

```bash
cd "$TEST_REPO"
/usr/bin/time -f 'ELAPSED=%E EXIT=%x' -o /tmp/opencode-success.time \
  opencode run "Say only: OPENCODE_SMOKE_OK" \
  > /tmp/opencode-success.stdout \
  2> /tmp/opencode-success.stderr
echo "EXIT_CODE=$?" | tee -a /tmp/opencode-success.time
```

### 3.5 Success probe (JSON format)

```bash
cd "$TEST_REPO"
/usr/bin/time -f 'ELAPSED=%E EXIT=%x' -o /tmp/opencode-json.time \
  opencode run --format json "Say only: OPENCODE_SMOKE_OK" \
  > /tmp/opencode-json.stdout \
  2> /tmp/opencode-json.stderr
echo "EXIT_CODE=$?" | tee -a /tmp/opencode-json.time
```

**Portable fallback (no GNU time):** wrap with `date` before/after and compute elapsed manually, and always record `$?` after the command.

```bash
cd "$TEST_REPO"
date -Iseconds; opencode run "Say only: OPENCODE_SMOKE_OK" > /tmp/opencode-success.stdout 2> /tmp/opencode-success.stderr; echo EXIT_CODE=$?; date -Iseconds
```

### 3.6 Failure probe

The `--model definitely/fake` probe forces a model resolution failure if the flag is accepted. If your install rejects the flag or behaves differently, document the actual error and use an alternative (e.g. empty auth + cloud model) that still yields a **non-zero** exit without leaking secrets.

```bash
cd "$TEST_REPO"
/usr/bin/time -f 'ELAPSED=%E EXIT=%x' -o /tmp/opencode-fail.time \
  opencode run --model definitely/fake "test" \
  > /tmp/opencode-fail.stdout \
  2> /tmp/opencode-fail.stderr || true
echo "EXIT_CODE=$?" | tee -a /tmp/opencode-fail.time
```

---

## 4. Evidence bundle layout

Create a **single folder** (e.g. `opencode-evidence-YYYYMMDD/`) and copy or rename files so reviewers get **at least** these **artifact names** (copy from `/tmp/…` or redirect directly to these names):

- `opencode-version.txt` — output of §3.1
- `opencode-auth.txt` — **redacted** output of §3.2 (§5)
- `opencode-run-help.txt` — output of `opencode run --help`
- `opencode-success.stdout` / `opencode-success.stderr` — from §3.4
- `opencode-json.stdout` / `opencode-json.stderr` — from §3.5
- `opencode-fail.stdout` / `opencode-fail.stderr` — from §3.6
- `opencode-summary.md` — fill with §10 after recording exit codes and times

**Optional** sidecars: `opencode-*.time` (GNU time output), or notes if you used portable timing instead of `/usr/bin/time`.

| File | Content |
|------|---------|
| `opencode-version.txt` | `command -v` + `opencode -v` + `opencode --version` |
| `opencode-auth.txt` | **Redacted** `auth list` / `ls` (§5) |
| `opencode-run-help.txt` | `opencode run --help` |
| `opencode-*.stdout` / `.stderr` | Probe outputs; share **excerpts** in PRs (§4 below) |
| `opencode-summary.md` | §10 handoff + exit/elapsed for each probe |

**Excerpt size for design review:** first **2KB** and last **2KB** of each `.stdout` / `.stderr` are usually enough, unless the team needs full files **locally** (never commit secrets). Note **exit code** and **elapsed** for **each** probe in `opencode-summary.md`.

---

## 5. Redaction rules

- **Do not** paste or commit: API keys, tokens, `auth.json` (or `~/.local/share/opencode/auth.json`) contents, full `.env` files, or cloud credentials.
- **Do not** include raw provider account emails if sensitive; use `user@REDACTED`.
- If stdout/stderr **unexpectedly** contains key-like strings, **replace** with `REDACTED`.
- **Paths** may be shortened (e.g. `/home/USER/.../ham`) as long as **cwd role** (test repo) stays clear.
- If in doubt, **redact** and say “redacted for policy” in the summary.

---

## 6. What to inspect in the outputs

Use this as a **reviewer checklist** after the probes:

1. **One-shot** — Does `opencode run` **return** to the shell without requiring TUI interaction? If it blocks or opens TUI, v1 is **not** a clean subprocess.
2. **stdout** — Mostly **final answer text**, or **interleaved** logs, progress, or tool traces?
3. **stderr** — Quiet on success, or **noisy** (logs, dep warnings)? Noisy stderr can still be OK if mappable to `error_summary` with caps.
4. **`--format json`** — Is it:
   - a **single** JSON object,
   - **ndjson** / event **stream** (multiple JSON lines),
   - **mixed** text + JSON,
   - or **unstable** line-to-line? **Do not assume** a schema until you see these files.
5. **Identifiers** — Do you see a **run id**, **session id**, or UUID that appears **reliably** on every success run? If not, HAM v1 should keep **`external_id = null`**.
6. **Exit codes** — Does `0` mean unambiguous success and non-zero map to a recoverable class of errors for the failure probe?
7. **Terminal-only v1** — Is behavior consistent with **no** long-running background session **owned** by HAM? (Attach/serve/continue are out of scope for v1 — see §9.)

---

## 7. Go / no-go rubric

| Outcome | When |
|---------|------|
| **Go** | `opencode run` is **one-shot and bounded**; exit codes **predictable**; stdout/stderr are **cappable**; JSON is **useful** *or* safely **ignored**; no dependency on TUI/session/server for basic success. |
| **Conditional go** | One-shots work but **one** of: JSON shape still unclear, stderr very noisy, or **no** external id (plan **`null`**). **List** the exact follow-up question in the summary. |
| **No-go (for now)** | Non-interactive behavior is **unstable**; output **cannot** be mapped to `succeeded`/`failed`/`unknown` honestly; or **v1** would require `serve`/`attach`/session **supervision** in HAM. |

---

## 8. Expected HAM v1 design assumptions (if go)

These are **not implemented** here — they are the **target** only if verification passes and maintainers accept the scope.

- **`external_id`:** `null` **unless** evidence shows a **stable** id in every one-shot (unlikely).
- **Lifecycle:** **Terminal-first** (subprocess join); optional brief `running` only if you explicitly record in-flight state.
- **No** follow-up, **no** status **poll** against a long-lived session API for v1.
- **No** TUI / `serve` / `web` / `--attach` / `--continue` in v1.
- **Subprocess** + **timeout** + **append-only JSONL audit** + **`ControlPlaneRun` only on committed operator launch** (same pattern as other harnesses — see contract docs).

---

## 9. Explicitly out of scope for HAM OpenCode v1

- TUI orchestration, interactive menus
- `opencode serve` / `opencode web` as something HAM **starts** or **supervises**
- `opencode run --attach …`
- `--continue` / `--session` / `session list` as **required** for basic launch
- Any claim of **stable external id** without proof from §6
- Background or long-running “agent supervision” in HAM core

---

## 10. Final handoff template

Paste into `opencode-summary.md` (or a PR / ticket) after running the spikes:

```markdown
## OpenCode verification handoff

- **OpenCode version** (from `opencode -v` / `--version`):
- **Host OS / image** (e.g. Ubuntu 24.04, local laptop):
- **Test repo path** (role only if sensitive: e.g. “small clone of HAM”):
- **Auth ready** (yes/no, without secrets):
- **Success probe (plain) exit code:**
- **Success probe (JSON) exit code:**
- **Failure probe exit code:**
- **Elapsed time** (each probe, roughly):
- **Stable external / session id observed?** (yes/no; quote format if yes, redacted):
- **JSON mode shape** (single object / ndjson / mixed / unstable / not used):
- **Recommendation:** go / conditional go / no-go
- **Notes** (noise level, blockers, alternative failure probe if used):
```

---

## 11. Cross-references

| Document / module | Role |
|-------------------|------|
| [`docs/HARNESS_PROVIDER_CONTRACT.md`](HARNESS_PROVIDER_CONTRACT.md) | Harness contract + `opencode_cli` **planned** row. |
| [`src/ham/harness_capabilities.py`](../src/ham/harness_capabilities.py) | Read-only registry; OpenCode **not** `implemented` until this verification + design pass. |
| [`docs/CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md) | Factual `ControlPlaneRun` substrate (no OpenCode until implemented). |
| [`docs/OPENCODE_VERIFICATION_RESULT.md`](OPENCODE_VERIFICATION_RESULT.md) | Optional log when a host attempt produces **no** bundle (e.g. binary missing). |

---

*After evidence is attached and a go/conditional-go decision is made, update the contract doc and registry in a **separate** change that still does not add the harness by itself if the decision is no-go.*
