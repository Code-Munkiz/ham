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

## Phase 2B Live Read/Model Dry-Run

Phase 2B lets Ham run a live X read-only search, select bounded candidates, draft with xAI, apply deterministic safety policy, run autonomy decisioning, and write review/exception/audit records. It stops there: it does not call `manual_canary`, `x_executor`, xurl mutations, or posting APIs.

Required gates:

```dotenv
HAM_X_ENABLE_LIVE_READ_MODEL_DRY_RUN=true
HAM_X_DRY_RUN=true
HAM_X_AUTONOMY_ENABLED=false
HAM_X_ENABLE_LIVE_EXECUTION=false
HAM_X_EMERGENCY_STOP=false
HAM_X_ENABLE_LIVE_SMOKE=false
HAM_X_READONLY_TRANSPORT=direct
HAM_X_MODEL=grok-4.20
```

`X_BEARER_TOKEN` and `XAI_API_KEY` must be present locally, but never printed. Every Phase 2B result, draft envelope, autonomy decision, queue record, and audit record must preserve `execution_allowed=false` and `mutation_attempted=false`.

## Phase 2C Guarded GoHAM Bridge

Phase 2C introduces a separate guarded bridge for autonomous original posts only. It is not called by Phase 2B dry-run, smoke, pipeline, or autonomy modules. It supports no quotes, replies, likes, follows, DMs, links, bulk actions, scheduling, or arbitrary model output.

Safe defaults keep it off:

```dotenv
HAM_X_ENABLE_GOHAM_EXECUTION=false
HAM_X_GOHAM_AUTONOMOUS_DAILY_CAP=1
HAM_X_GOHAM_AUTONOMOUS_PER_RUN_CAP=1
HAM_X_GOHAM_MIN_SCORE=0.90
HAM_X_GOHAM_MIN_CONFIDENCE=0.90
HAM_X_GOHAM_ALLOWED_ACTIONS=post
HAM_X_GOHAM_BLOCK_LINKS=true
```

Live GoHAM execution additionally requires `HAM_X_AUTONOMY_ENABLED=true`, `HAM_X_DRY_RUN=false`, `HAM_X_ENABLE_LIVE_EXECUTION=true`, and `HAM_X_EMERGENCY_STOP=false`. Do not run live GoHAM execution without a separate explicit operator instruction.

## GoHAM v0 Ops/Status

`src.ham.ham_x.goham_ops` provides read-only operator helpers for daily GoHAM checks before any future autonomous action. These helpers summarize the execution journal, report today's GoHAM autonomous cap usage, expose the current gate state, and run dry candidate preflight through `evaluate_goham_eligibility()` only.

Daily operator flow:

1. Inspect `show_goham_status()` for `last_autonomous_post`, `provider_post_id`, cap used/remaining, journal/audit paths, emergency stop, and gate state.
2. Use `check_goham_cap()` to confirm only `execution_kind="goham_autonomous"` rows count against the GoHAM autonomous cap. Manual canary rows do not count.
3. Use `dry_preflight_goham_candidate()` on a prepared candidate to see deterministic block reasons before any scheduled or repeated GoHAM run.
4. Treat all ops/status output as non-mutating: `mutation_attempted=false`; these helpers do not call `x_executor`, `manual_canary`, `goham_bridge`, `pipeline`, `smoke`, or `live_dry_run`.

## GoHAM v0 Daily Runner

`src.ham.ham_x.goham_daily.run_goham_daily_once()` is the one-shot operator runner for a single prepared GoHAM candidate. It composes status, dry preflight, the guarded bridge, and status again:

`show_goham_status()` -> `dry_preflight_goham_candidate()` -> `run_goham_guarded_post()` at most once -> `show_goham_status()`

It accepts exactly one `GohamExecutionRequest` and one `AutonomyDecisionResult`. It does not generate candidates, run Phase 2B, schedule future work, retry failures, or accept arbitrary live model output for execution. If dry preflight blocks, it returns without calling the bridge. If the bridge is called, the runner stops immediately after that single result.

First live daily run checklist:

1. Confirm `show_goham_status()` reports `daily_cap_used=0`, `daily_cap_remaining=1`, safe gates, and `HAM_X_EMERGENCY_STOP=false`.
2. Prepare one manual safe original post candidate with no links, no target ids, and a unique idempotency key.
3. Confirm dry preflight allows it.
4. Run `run_goham_daily_once()` once.
5. Stop immediately and verify the post, audit row, journal row, and cap status before considering any future run.

## Phase 3A Firehose Controller Dry-Run

Phase 3A adds a dry-run-only controller foundation: `goham_campaign.py`, `goham_governor.py`, and `goham_controller.py`. It accepts a bounded candidate bank, asks the governor for each candidate, audits every decision, and returns allowed/blocked dry-run summaries. It does not call `goham_bridge`, `manual_canary`, `x_executor`, Phase 2B, xurl mutations, or provider APIs.

Safe defaults keep it disabled and non-mutating:

```dotenv
HAM_X_ENABLE_GOHAM_CONTROLLER=false
HAM_X_GOHAM_CONTROLLER_DRY_RUN=true
HAM_X_GOHAM_MAX_TOTAL_ACTIONS_PER_DAY=1
HAM_X_GOHAM_MAX_ORIGINAL_POSTS_PER_DAY=1
HAM_X_GOHAM_MAX_QUOTES_PER_DAY=0
HAM_X_GOHAM_MIN_SPACING_MINUTES=120
HAM_X_GOHAM_MAX_ACTIONS_PER_RUN=1
HAM_X_GOHAM_MAX_CANDIDATES_PER_RUN=5
HAM_X_GOHAM_CONSECUTIVE_FAILURE_STOP=2
HAM_X_GOHAM_POLICY_REJECTION_STOP=5
HAM_X_GOHAM_MODEL_TIMEOUT_STOP=3
```

## Phase 3B Live Governed Controller

Phase 3B adds `src.ham.ham_x.goham_live_controller.run_live_controller_once()` as a separate live controller. It accepts prepared bounded candidates only, asks the Phase 3A governor, selects at most one `auto_original_post`, converts it into the existing guarded GoHAM bridge request, calls the bridge through `run_post` at most once, then stops.

It does not extend `goham_controller.py`; Phase 3A remains dry-run-only. It does not run Phase 2B, xAI drafting, live X read acquisition, xurl mutations, quotes, replies, likes, follows, DMs, scheduling, daemons, infinite loops, or multi-action live runs.

Additional safe defaults keep Phase 3B off:

```dotenv
HAM_X_ENABLE_GOHAM_LIVE_CONTROLLER=false
HAM_X_GOHAM_LIVE_CONTROLLER_ORIGINAL_POSTS_ONLY=true
HAM_X_GOHAM_LIVE_MAX_ACTIONS_PER_RUN=1
```

Live governed execution still requires all existing GoHAM live gates (`HAM_X_ENABLE_GOHAM_EXECUTION=true`, `HAM_X_AUTONOMY_ENABLED=true`, `HAM_X_DRY_RUN=false`, `HAM_X_ENABLE_LIVE_EXECUTION=true`, `HAM_X_EMERGENCY_STOP=false`) plus `HAM_X_ENABLE_GOHAM_CONTROLLER=true` and `HAM_X_GOHAM_CONTROLLER_DRY_RUN=false`. The live controller derives a deterministic idempotency key from `campaign_id + source_action_id + text_key`, checks the shared execution journal before the bridge call, passes that same journal to the bridge, and does not retry failed provider attempts.

## Phase 4A Reactive Engine Dry-Run

Phase 4A adds a separate dry-run-only reactive lane for inbound engagement: `inbound_client.py`, `reactive_policy.py`, `reactive_governor.py`, and `goham_reactive.py`. It accepts prepared/read-only inbound records for mentions or comments, classifies them, applies reactive policy, asks a separate governor, and routes safe reply candidates to review records or unsafe/ambiguous items to exception records.

Reactive is not governed by the broadcast original-post daily cap. It uses separate reply budgets, per-user/thread cooldowns, duplicate inbound and duplicate response checks, rolling 15-minute/hour caps, emergency stop, and policy circuit breakers. Phase 4A never calls providers and always returns `execution_allowed=false` and `mutation_attempted=false`.

Safe defaults keep it disabled and dry-run-only:

```dotenv
HAM_X_ENABLE_GOHAM_REACTIVE=false
HAM_X_GOHAM_REACTIVE_DRY_RUN=true
HAM_X_GOHAM_REACTIVE_LIVE_CANARY=false
HAM_X_GOHAM_REACTIVE_MAX_REPLIES_PER_15M=5
HAM_X_GOHAM_REACTIVE_MAX_REPLIES_PER_HOUR=20
HAM_X_GOHAM_REACTIVE_MAX_REPLIES_PER_USER_PER_DAY=3
HAM_X_GOHAM_REACTIVE_MAX_REPLIES_PER_THREAD_PER_DAY=5
HAM_X_GOHAM_REACTIVE_MIN_SECONDS_BETWEEN_REPLIES=60
HAM_X_GOHAM_REACTIVE_MIN_RELEVANCE=0.75
HAM_X_GOHAM_REACTIVE_BLOCK_LINKS=true
HAM_X_GOHAM_REACTIVE_FAILURE_STOP=2
HAM_X_GOHAM_REACTIVE_POLICY_REJECTION_STOP=10
HAM_X_GOHAM_REACTIVE_MAX_INBOUND_PER_RUN=25
HAM_X_GOHAM_REACTIVE_MAX_REPLIES_PER_RUN=1
```

## Phase 4B Reactive Live Reply Canary

Phase 4B adds a separate one-shot live reply canary lane: `reactive_reply_executor.py` and `goham_reactive_live.py`. It accepts exactly one prepared inbound record, or one Phase 4A `ReactiveItemResult` whose status is `reply_candidate`, re-checks reactive policy and the reactive governor, sends at most one reply through `POST /2/tweets` with `reply: { in_reply_to_tweet_id }`, then stops.

This lane is reply-only. It does not support original posts, quotes, likes, follows, DMs, xurl mutation, manual canary execution, broadcast `XCanaryExecutor`, scheduling, daemons, loops, batches, or second replies. Reactive replies write execution journal rows with `execution_kind="goham_reactive_reply"` and do not count against GoHAM original-post or broadcast controller caps.

Required live canary gates:

```dotenv
HAM_X_ENABLE_GOHAM_REACTIVE=true
HAM_X_GOHAM_REACTIVE_DRY_RUN=false
HAM_X_GOHAM_REACTIVE_LIVE_CANARY=true
HAM_X_EMERGENCY_STOP=false
HAM_X_GOHAM_REACTIVE_MAX_REPLIES_PER_RUN=1
HAM_X_GOHAM_REACTIVE_BLOCK_LINKS=true
```

The prepared inbound must have a valid reply target id, bounded safe reply text, policy route `reply_candidate`, and an allowed reactive governor decision. Provider failures are not retried; 401/403 responses update reactive stop state so later canary attempts fail closed.

## Phase 4B.1 Reactive Inbox Discovery

Phase 4B.1 adds `goham_reactive_inbox.py` as a read-only one-shot discovery controller. It uses direct Bearer X recent search through `InboundClient`, normalizes mentions/comments into `ReactiveInboundItem` records, marks known handled inbound ids from `execution_kind="goham_reactive_reply"` journal rows, applies reactive policy and governor checks, and returns at most one selected candidate with an automatic `reply_target_id`.

This phase does not execute replies and does not call `reactive_reply_executor.py` or `goham_reactive_live.py`. It is target acquisition only; live reply execution still requires a separate explicit operator instruction.

Safe defaults:

```dotenv
HAM_X_ENABLE_REACTIVE_INBOX_DISCOVERY=false
HAM_X_REACTIVE_INBOX_QUERY=
HAM_X_REACTIVE_INBOX_MAX_RESULTS=25
HAM_X_REACTIVE_INBOX_MAX_THREADS=5
HAM_X_REACTIVE_INBOX_LOOKBACK_HOURS=24
HAM_X_REACTIVE_HANDLE=
HAM_X_REACTIVE_INBOX_INCLUDE_REPLIES_TO_OWN_POSTS=true
```

If `HAM_X_REACTIVE_INBOX_QUERY` is empty, discovery uses `@{HAM_X_REACTIVE_HANDLE} -is:retweet`. X search responses request tweet fields, author expansion, referenced tweet ids, and usernames so replies can be normalized with `conversation_id`, `post_id`, `in_reply_to_post_id`, and author handle.

## Phase 4C Reactive Batch Mode

Phase 4C adds `goham_reactive_batch.py` as an opt-in, dry-run-first one-command runner for multiple already-discovered reactive candidates. It consumes `ReactiveInboundItem` or inbox candidate records, re-checks reactive policy and governor per item, respects the existing reactive rolling caps and cooldowns, and in dry-run mode records per-item outcomes without calling the provider.

Live batch mode remains explicitly gated and bounded. When enabled later, it calls `ReactiveReplyExecutor.execute()` at most `HAM_X_GOHAM_REACTIVE_BATCH_MAX_REPLIES_PER_RUN` times, journals each executed reply as `execution_kind="goham_reactive_reply"`, updates in-memory duplicate/cooldown state after each success, stops on configured auth/provider failures, and never retries the same inbound item in the same run. It is not a scheduler, daemon, infinite loop, uncontrolled runner, or discovery replacement.

Safe defaults:

```dotenv
HAM_X_ENABLE_GOHAM_REACTIVE_BATCH=false
HAM_X_GOHAM_REACTIVE_BATCH_DRY_RUN=true
HAM_X_GOHAM_REACTIVE_BATCH_MAX_REPLIES_PER_RUN=3
HAM_X_GOHAM_REACTIVE_BATCH_STOP_ON_AUTH_FAILURE=true
HAM_X_GOHAM_REACTIVE_BATCH_STOP_ON_PROVIDER_FAILURES=2
```

## Autonomy Modes

- `draft`: queue draft content only.
- `approval`: future explicit human approval mode.
- `guarded`: future capped execution mode with policy, budget, and rate checks.
- `goham`: future bounded high-autonomy mode with visible controls and audit trails, not reckless automation.
