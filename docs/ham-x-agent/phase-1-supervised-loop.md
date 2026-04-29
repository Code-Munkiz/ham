# Phase 1 Supervised Loop

Phase 1 is review-queue oriented. It prepares the surfaces needed for the official HAM PR agent and future tenant-created X agents without enabling live posting.

## Flow

1. Build a dry-run X search plan.
2. Score candidate posts or accounts with a normalized action envelope.
3. Draft relevant commentary with the xAI/Grok adapter shape.
4. Run deterministic safety policy checks.
5. Run local budget and rate-limit guardrails.
6. Append a redacted audit event.
7. Append a redacted review queue record.

## Phase 1A Behavior

- Search uses `xurl_wrapper.plan_search()` and does not call the network.
- Drafting uses `grok_client.draft_social_action()` and does not call xAI.
- Mutating actions use `xurl_wrapper.plan_mutating_action()` and are blocked.
- Queue and audit writes are append-only JSONL.
- Records include tenant, agent, campaign, account, profile, policy profile, brand voice, and autonomy mode context.
- xurl plans include `catalog_skill_id=bundled.social-media.xurl` as Hermes catalog metadata only.

## Phase 1B Behavior

Phase 1B adds `run_supervised_opportunity_loop()` as a non-mutating pipeline:

1. Create a dry-run xurl search plan.
2. Normalize candidate-like records into `CandidateTarget`.
3. Score candidates deterministically for keyword quality, campaign relevance, Base ecosystem fit, spam/bot signals, hostile/unsafe content, natural engagement fit, and PR opportunity quality.
4. Ignore or monitor low-quality candidates.
5. Draft deterministic placeholder commentary for good candidates.
6. Review drafts with the no-network Hermes policy adapter.
7. Attach placeholder budget and rate-limit results.
8. Queue only allowed drafts for human review.
9. Audit each step with platform context and action ids where a draft action exists.

The pipeline does not make live xurl calls, live xAI/Grok calls, or mutating X calls.

## Phase 1C Behavior

Phase 1C adds `decide_autonomy()` after policy, budget, and rate checks. The decision engine produces one of:

- `auto_reject`
- `ignore`
- `monitor`
- `draft_only`
- `queue_exception`
- `queue_review`
- `auto_approve`

`auto_approve` is only an execution candidate record for future phases. In Phase 1C, every decision has `execution_allowed=false`; no xurl post, quote, or like command is executed.

The exception queue stores uncertain, risky, emergency-stop-blocked, budget-blocked, and rate-blocked action proposals as bounded redacted JSONL. The review queue remains for calibration and approval-mode review, not as a permanent requirement for every action.

## Phase 1E Behavior

Phase 1E adds a read-only X smoke adapter for `xurl search` only. It is gated by `HAM_X_ENABLE_LIVE_SMOKE=true`, `HAM_X_DRY_RUN=true`, and `HAM_X_AUTONOMY_ENABLED=false`.

The adapter validates xurl/X wiring without enabling posting. It denies post, quote, and like before subprocess execution, uses argv arrays with `shell=False`, redacts stdout/stderr, and preserves `mutation_attempted=false` and `execution_allowed=false`.

## Phase 1F Behavior

Phase 1F adds an xAI tiny-call smoke for `XAI_API_KEY` and `HAM_X_MODEL` validation only. It sends the fixed prompt `Return exactly: HAM_XAI_SMOKE_OK` with a strict output cap and short timeout.

The smoke result is not campaign drafting. It is not connected to review queue publishing, autonomy decisions, xurl, or posting, and it preserves `mutation_attempted=false` and `execution_allowed=false`.

## Phase 2A Boundary

Phase 2A manual canary execution is outside the supervised opportunity loop. The loop may still create proposals and decisions, but it must not call the canary executor. The executor is a separate operator-triggered path for one manually confirmed `post` or `quote`.

## Phase 2B Live Read/Model Dry-Run

Phase 2B adds a live-read/live-model dry-run path:

1. Run direct Bearer X recent search.
2. Normalize returned tweets into bounded `CandidateTarget` records.
3. Score candidates deterministically.
4. Draft with xAI using bounded prompts, bounded output, and `store=false`.
5. Apply deterministic safety policy and Hermes local policy review.
6. Run autonomy decisioning for routing only.
7. Append review or exception queue records and redacted audit events.

This path is for GoHAM-style opportunity preparation, not posting. It does not import or call `manual_canary` or `x_executor`, and every result preserves `execution_allowed=false` and `mutation_attempted=false`.

## Phase 2C Guarded GoHAM Bridge

Phase 2C is the first autonomous execution bridge, but it stays outside the Phase 2B dry-run loop. Only `goham_bridge.py` may call the low-level X executor for autonomous work, and only after `goham_policy.py` passes a narrow original-post eligibility check.

The bridge supports original posts only. It blocks quote/reply/like/follow/DM actions, links, financial or buy language, non-low-risk decisions, low score/confidence, duplicate idempotency keys, and cap overages. Phase 2B remains a preparation loop and does not gain posting authority.

## Reusable Agent Template

The official launch agent uses `tenant_id=ham-official`, `agent_id=ham-pr-rockstar`, and `campaign_id=base-stealth-launch`. The same action envelope can be reused for tenant-created agents by changing those context fields and attaching tenant-specific policy and brand voice profiles.

Supported autonomy modes are `draft`, `approval`, `guarded`, and `goham`. Higher-autonomy modes remain bounded by safety policy, rate limits, budgets, review/audit trails, emergency stop, and later execution gates.

## Future Promotion Criteria

Before any live posting phase, HAM-on-X needs explicit product approval, integration tests with mocked xurl/xAI clients, dashboard review controls, and a deployment-specific kill switch procedure.

Durable multi-step campaign/control-plane runs are not part of Phase 1. The current records are per-action proposals, autonomy decisions, queue records, and append-only event traces.
