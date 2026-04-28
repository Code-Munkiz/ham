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

## Reusable Agent Template

The official launch agent uses `tenant_id=ham-official`, `agent_id=ham-pr-rockstar`, and `campaign_id=base-stealth-launch`. The same action envelope can be reused for tenant-created agents by changing those context fields and attaching tenant-specific policy and brand voice profiles.

Supported autonomy modes are `draft`, `approval`, `guarded`, and `goham`. Phase 1 operates as `draft`; higher-autonomy modes are future states and must remain bounded by safety policy, rate limits, budgets, review/audit trails, and a kill switch.

## Future Promotion Criteria

Before any live posting phase, HAM-on-X needs explicit product approval, integration tests with mocked xurl/xAI clients, dashboard review controls, and a deployment-specific kill switch procedure.

Durable multi-step campaign/control-plane runs are not part of Phase 1A. The current records are per-action proposals plus append-only event traces.
