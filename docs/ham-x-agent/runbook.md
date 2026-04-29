# HAM-on-X Phase 1 Runbook

## Local Setup

1. Copy `.env.example` to `.env`.
2. Keep `HAM_X_AUTONOMY_ENABLED=false`.
3. Keep `HAM_X_DRY_RUN=true`.
4. Keep `HAM_X_ENABLE_LIVE_SMOKE=false` unless running an explicitly approved live read-only smoke later.
5. Use staging credentials only if credentials are needed for future local testing.

## Smoke Test

Run the focused tests:

```bash
python -m pytest tests/test_ham_x_phase1a.py tests/test_ham_x_smoke.py tests/test_ham_x_xurl_readonly.py tests/test_ham_x_xai_smoke.py -v
```

Phase 1B/1C/1D/1E use the same narrow test target. It covers the non-mutating opportunity pipeline, autonomy decisions, exception queue writes, review queue writes, audit traces, smoke summaries, read-only xurl smoke, and mutating-action blocks.

Run a local smoke from Python:

```bash
python - <<'PY'
from src.ham.ham_x.smoke import run_smoke
print(run_smoke("local").redacted_dump())
PY
```

Run an environment smoke:

```bash
python - <<'PY'
from src.ham.ham_x.smoke import run_smoke
print(run_smoke("env").redacted_dump())
PY
```

## Inspect Review Output

By default, review queue records are written to:

```text
.data/ham-x/review_queue.jsonl
```

Audit events are written to:

```text
.data/ham-x/audit.jsonl
```

Exception queue records are written to:

```text
.data/ham-x/exception_queue.jsonl
```

These files must contain redacted, bounded JSONL records only.

Each record should include platform context for the official HAM PR agent by default:

```text
tenant_id=ham-official
agent_id=ham-pr-rockstar
campaign_id=base-stealth-launch
```

Tenant-created X agents should receive their own tenant, agent, campaign, account, policy, and brand voice values before any production rollout.

## Kill Switch

Set either of these values to keep mutating actions blocked:

```dotenv
HAM_X_AUTONOMY_ENABLED=false
HAM_X_DRY_RUN=true
HAM_X_EMERGENCY_STOP=true
HAM_X_ENABLE_LIVE_SMOKE=false
```

In Phase 1, mutating actions are blocked even if these values are changed.

## Phase 1B Dry-Run Loop

Use `run_supervised_opportunity_loop()` with candidate-like records collected from dry-run search planning or fixtures. The loop writes allowed draft proposals to the review queue and audit trace, but it does not post, quote, like, or call xAI/Grok.

Review queue records are human-review proposals. Audit records are append-only traces. Durable multi-step campaign/control-plane runs are future work.

## Phase 1C Autonomy Decisions

`decide_autonomy()` emits decision states such as `draft_only`, `queue_review`, `queue_exception`, and `auto_approve`. In Phase 1C, `auto_approve` is only an autonomous approval candidate; `execution_allowed` is always `false`, and no xurl mutation is executed.

## Phase 1D Smoke Modes

`run_smoke("local")` uses fixture candidate data and the real dry-run pipeline. `run_smoke("env")` reports redacted environment status and safe-default checks. `x-readonly`, `xai`, and `e2e-dry-run` stay non-mutating; live behavior is disabled unless `HAM_X_ENABLE_LIVE_SMOKE=true`, and smoke results still return `execution_allowed=false`.

## Phase 1E Read-Only X Smoke

`run_smoke("x-readonly")` can validate xurl/X wiring with a search-only command when all gates are set:

```dotenv
HAM_X_ENABLE_LIVE_SMOKE=true
HAM_X_DRY_RUN=true
HAM_X_AUTONOMY_ENABLED=false
HAM_X_READONLY_TRANSPORT=direct
```

Use staging X credentials for this check. Do not use production credentials for first-pass smoke validation, and never paste or print token values. The default read-only smoke uses direct Bearer X Recent Search for `Base ecosystem autonomous agents` with `max_results=10`; `HAM_X_READONLY_TRANSPORT=xurl` remains available as a fallback. Post, quote, like, reply, timeline, mentions, and xAI calls are not part of Phase 1E.

After a run, verify the returned smoke result and `.data/ham-x/audit.jsonl` contain `mutation_attempted=false`, `execution_allowed=false`, and search-only behavior.

If the read-only smoke returns `xurl_returned_401_unauthorized`, check the active xurl profile, bearer token, X app/project permissions, and token freshness. The smoke output should keep that status and diagnostic readable while still redacting secrets.

## Phase 1F xAI Tiny-Call Smoke

`run_smoke("xai")` can validate `XAI_API_KEY` and `HAM_X_MODEL` wiring with one tiny fixed prompt when `HAM_X_ENABLE_LIVE_SMOKE=true` and `XAI_API_KEY` is present.

The smoke prompt is exactly:

```text
Return exactly: HAM_XAI_SMOKE_OK
```

The smoke caps output at 8 tokens and does not feed model output into campaign drafting, review queues, autonomy decisions, or xurl. Use staging xAI credentials first, never paste token values, and verify the returned smoke result preserves `mutation_attempted=false` and `execution_allowed=false`.

## Phase 2A Manual Canary Execution

Phase 2A adds a manual-only canary executor for one `post` or one `quote`. It is not called by scoring, autonomy, the opportunity pipeline, xAI drafting, smoke, review queues, or exception queues.

Live execution remains disabled unless all gates pass:

```dotenv
HAM_X_ENABLE_LIVE_EXECUTION=true
HAM_X_DRY_RUN=false
HAM_X_AUTONOMY_ENABLED=false
HAM_X_EMERGENCY_STOP=false
HAM_X_EXECUTION_PER_RUN_CAP=1
HAM_X_EXECUTION_DAILY_CAP=1
```

The caller must also pass `manual_confirm=true`. Do not run a live canary from this runbook without a separate explicit operator instruction.

Manual canary result semantics:

- `execution_allowed=false` means local gates did not permit a provider call (`blocked` or `dry_run`).
- `execution_allowed=true` means all local gates passed and the provider call was allowed. It does not mean autonomy is enabled.
- `mutation_attempted=true` means the direct OAuth1 provider call was attempted. `failed` results after a provider call still set this to `true`.

## Autonomy Modes

- `draft`: queue draft content only.
- `approval`: future explicit human approval mode.
- `guarded`: future capped execution mode with policy, budget, and rate checks.
- `goham`: future bounded high-autonomy mode with visible controls and audit trails, not reckless automation.
