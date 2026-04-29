# HAM-on-X Phase 1 Architecture

HAM-on-X Phase 1 is a supervised, non-mutating scaffold for social research and review. It supports the official HAM PR agent on X and the future reusable template for tenant-created HAM agents. It does not post, quote, like, or reply on X.

## Loop Shape

The intended production loop is:

1. Search X targets with a strict xurl wrapper.
2. Score candidate targets.
3. Generate a draft with the future xAI/Grok adapter.
4. Run safety, budget, and rate-limit checks.
5. Write a bounded review queue record.
6. Require human review before any future mutating action.

Phase 1A implemented the safe scaffold. Phase 1B added a dry-run social opportunity pipeline: search plan, candidate normalization, deterministic scoring, deterministic draft generation, local Hermes policy review, budget/rate guardrails, review queue output, and audit traces. Phase 1C adds the Autonomy Decision Engine and exception queue. Phase 1D adds a safe smoke testing harness. Mutating actions remain blocked.

## Platform Context

Every action envelope, review queue record, and audit record should carry platform context so official and tenant agents can be separated without changing the record shape:

- `tenant_id=ham-official`
- `agent_id=ham-pr-rockstar`
- `campaign_id=base-stealth-launch`
- `account_id=ham-x-official`
- `profile_id=ham.default`
- `autonomy_mode=draft`
- `policy_profile_id=platform-default`
- `brand_voice_id=ham-canonical`
- `catalog_skill_id=bundled.social-media.xurl`

Tenant-created X agents can override these values through platform configuration in later phases while keeping the same audit and review schema.

The catalog skill id links xurl plans to HAM's vendored Hermes runtime skills catalog. Phase 1 records the linkage only; it does not install, invoke, or assume the skill is live.

## Autonomy Modes

- `draft`: generate candidate text and queue it for review only.
- `approval`: prepare bounded actions that require explicit human approval.
- `guarded`: future mode for tightly capped actions with policy, budget, and rate-limit gates.
- `goham`: bounded high-autonomy operation with visible controls, audit trails, and kill switch behavior. GoHAM is not reckless automation and must still respect platform policy and X rules.

## Autonomy Decisions

Phase 1C can decide `auto_reject`, `ignore`, `monitor`, `draft_only`, `queue_exception`, `queue_review`, or `auto_approve`. These are decision states only. `execution_allowed` is always `false`, and `auto_approve` means "autonomous approval candidate for a later execution phase," not an xurl call.

The emergency stop (`HAM_X_EMERGENCY_STOP=true`) blocks autonomous approval and routes affected actions to human attention.

## Smoke Harness

Phase 1D exposes `run_smoke()` for local safety checks. The supported modes are `local`, `env`, `x-readonly`, `xai`, and `e2e-dry-run`.

All smoke results preserve `execution_allowed=false` and `mutation_attempted=false`. Live-capable smoke behavior is gated by `HAM_X_ENABLE_LIVE_SMOKE=true`; by default, read-only X and xAI smoke modes return safe disabled summaries without network calls.

Phase 1E implements only a gated read-only `xurl search` smoke. It requires `HAM_X_DRY_RUN=true` and `HAM_X_AUTONOMY_ENABLED=false`, denies post/quote/like before subprocess execution, and keeps xAI smoke disabled/not implemented.

Phase 1F implements only a gated xAI tiny-call smoke for credential/model validation. The returned text is never connected to campaign drafting, review queue publishing, autonomy decisions, or xurl execution.

## Boundaries

- Hermes remains the supervisory policy layer.
- Execution stays behind bounded adapters such as the xurl wrapper.
- `memory_heist` remains the repo context source when future HAM-on-X prompts need project context.
- GoHAM compatibility means the review queue and audit trail can later be surfaced in the workspace UI without adding autonomous posting in Phase 1.

## Record Semantics

- `SocialActionEnvelope` records are per-action proposals.
- Review queue records are human-review proposals for proposed social actions.
- Exception queue records are uncertain, risky, budget-blocked, rate-blocked, or emergency-stop-blocked proposals.
- Audit records are append-only event traces.
- Durable multi-step campaign and control-plane runs are future work.

HAM-on-X review and audit helpers mirror existing HAM proposal/audit patterns in Phase 1. Future phases should consolidate shared persistence primitives where doing so does not mix browser-control and social-agent semantics.

## Default Safety Posture

- `HAM_X_AUTONOMY_ENABLED=false`
- `HAM_X_DRY_RUN=true`
- `HAM_X_ENABLE_LIVE_SMOKE=false`
- `HAM_X_MAX_POSTS_PER_HOUR=0`
- `HAM_X_MAX_QUOTES_PER_HOUR=0`

These defaults mean Phase 1 can produce reviewable records but cannot publish content.
