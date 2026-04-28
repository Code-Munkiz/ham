# HAM-on-X Phase 1A Architecture

HAM-on-X Phase 1A is a supervised, non-mutating scaffold for social research and review. It supports the official HAM PR agent on X and the future reusable template for tenant-created HAM agents. It does not post, quote, like, or reply on X.

## Loop Shape

The intended production loop is:

1. Search X targets with a strict xurl wrapper.
2. Score candidate targets.
3. Generate a draft with the future xAI/Grok adapter.
4. Run safety, budget, and rate-limit checks.
5. Write a bounded review queue record.
6. Require human review before any future mutating action.

Phase 1A implements only the scaffold for this loop. Search is represented as a dry-run command plan. Draft generation returns a deterministic placeholder. Mutating actions are blocked.

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

The catalog skill id links xurl plans to HAM's vendored Hermes runtime skills catalog. Phase 1A records the linkage only; it does not install, invoke, or assume the skill is live.

## Autonomy Modes

- `draft`: generate candidate text and queue it for review only.
- `approval`: prepare bounded actions that require explicit human approval.
- `guarded`: future mode for tightly capped actions with policy, budget, and rate-limit gates.
- `goham`: bounded high-autonomy operation with visible controls, audit trails, and kill switch behavior. GoHAM is not reckless automation and must still respect platform policy and X rules.

## Boundaries

- Hermes remains the supervisory policy layer.
- Execution stays behind bounded adapters such as the xurl wrapper.
- `memory_heist` remains the repo context source when future HAM-on-X prompts need project context.
- GoHAM compatibility means the review queue and audit trail can later be surfaced in the workspace UI without adding autonomous posting in Phase 1A.

## Record Semantics

- `SocialActionEnvelope` records are per-action proposals.
- Review queue records are human-review proposals for proposed social actions.
- Audit records are append-only event traces.
- Durable multi-step campaign and control-plane runs are future work.

HAM-on-X review and audit helpers mirror existing HAM proposal/audit patterns in Phase 1A. Future phases should consolidate shared persistence primitives where doing so does not mix browser-control and social-agent semantics.

## Default Safety Posture

- `HAM_X_AUTONOMY_ENABLED=false`
- `HAM_X_DRY_RUN=true`
- `HAM_X_MAX_POSTS_PER_HOUR=0`
- `HAM_X_MAX_QUOTES_PER_HOUR=0`

These defaults mean Phase 1A can produce reviewable records but cannot publish content.
