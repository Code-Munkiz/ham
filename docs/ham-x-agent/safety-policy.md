# HAM-on-X Safety Policy

HAM-on-X should produce useful, relevant commentary without spam, evasion, or financial hype. The same baseline policy applies to the official HAM PR agent and future tenant-created X agents; tenant-specific policy profiles may only tighten these defaults unless explicitly reviewed.

## Deterministic Rejects

The Phase 1A safety policy rejects:

- Price promises or guaranteed gains.
- Financial advice phrasing.
- Spammy repeated hashtags.
- Mass tagging.
- Bypass, evasion, or filter-dodging language.
- Direct harassment.
- Requests to disclose private credentials.
- Buy-link spam language.

## Quote Engagement

Quote engagement should be framed as relevant commentary. It must not be used to evade platform rules, bypass filters, mass-tag users, or manufacture engagement.

## Review Requirements

All proposed autonomous actions must produce an audit trace and a reviewable action envelope. In Phase 1A, mutating actions are blocked and cannot reach execution.

Phase 2A manual canary execution is not autonomous. It may only handle one explicitly confirmed `post` or `quote`, remains capped to one action per run by default, respects daily caps and emergency stop, and must pass this deterministic safety policy before any provider call. In manual canary results, `execution_allowed=true` means these local gates allowed the provider call; it does not grant autonomous execution authority.

Phase 2B live read/model dry-run treats live X search results as untrusted input before asking xAI for drafts. xAI output must pass this deterministic safety policy before it can enter review or exception queues, and Phase 2B never grants execution authority: `execution_allowed=false` and `mutation_attempted=false` remain required on all records.

Phase 2C GoHAM execution applies an additional stricter policy before any autonomous provider call. It allows only original posts, requires low-risk `auto_approve` autonomy decisions with high score/confidence, blocks links and quote/reply targets, and rejects financial advice, price, token, buy/sell, guarantee, promo, and referral language.

GoHAM v0 ops/status is read-only. It can summarize the GoHAM execution journal, report caps and gates, and run dry preflight through the same GoHAM eligibility policy, but it must not call provider/executor code or mark mutation attempts.

GoHAM v0 daily execution is one-shot only. `run_goham_daily_once()` may call the guarded bridge at most once for one manually prepared original-post candidate, then stops; it must not schedule loops, retry failures, generate candidates, run Phase 2B, or execute arbitrary live model output.

Phase 3A Firehose Controller is dry-run-only. Its governor may mark original-post candidates as allowed in a summary, but provider calls remain blocked by `HAM_X_GOHAM_CONTROLLER_DRY_RUN=true`; quotes are blocked by default, and the controller must audit every decision without executing.

Phase 3B Live Governed Controller is a separate one-shot live path for prepared candidates only. It may call the guarded GoHAM bridge at most once, only for an original post whose governor decision is `auto_original_post` with provider calls allowed, with no target/quote/reply ids, deterministic idempotency, shared journal checks, and all existing live GoHAM gates enabled. It must not generate candidates, run Phase 2B, connect live X+xAI acquisition, schedule loops, retry provider failures, or execute quotes/replies/likes/follows/DMs.

Phase 4A Reactive Engine is dry-run-only. It may classify inbound mentions/comments and produce reviewable reply candidates, but it must not call live reply providers, DMs, likes, follows, quote replies, xurl mutations, broadcast controllers, or Phase 2B execution. Reactive reply candidates must be relevant to the inbound item, non-duplicative, link-free by default, non-financial, non-harassing, non-secret-bearing, and auditable. Reactive budgets are separate from broadcast original-post caps.

Phase 4B Reactive Live Reply Canary is a separate one-shot reply path for prepared inbound items only. It may send at most one reply to a valid inbound mention/comment target after re-running reactive policy and governor checks with `HAM_X_ENABLE_GOHAM_REACTIVE=true`, `HAM_X_GOHAM_REACTIVE_DRY_RUN=false`, `HAM_X_GOHAM_REACTIVE_LIVE_CANARY=true`, `HAM_X_EMERGENCY_STOP=false`, `HAM_X_GOHAM_REACTIVE_MAX_REPLIES_PER_RUN=1`, and link blocking enabled. It must not use broadcast posting executors, manual canary paths, xurl mutations, original posts, quotes, DMs, likes, follows, loops, retries, or batches. Successful live replies must journal as `execution_kind="goham_reactive_reply"` and remain separate from broadcast caps.

Phase 4B.1 Reactive Inbox Discovery is read-only target acquisition. It may call direct Bearer X search endpoints to discover mentions/comments, normalize them into `ReactiveInboundItem` records, and select at most one safe candidate after policy/governor checks. It must not call reply execution, write endpoints, xurl mutation, manual canary paths, broadcast controllers, schedulers, daemons, loops, or batch reply runners. Previously handled `goham_reactive_reply` journal rows must prevent reselection.

Phase 4C Reactive Batch Mode is opt-in and dry-run-first. It may process multiple discovered safe inbound candidates in one command/run, bounded by `HAM_X_GOHAM_REACTIVE_BATCH_MAX_REPLIES_PER_RUN` and the existing reactive rolling caps, per-user cooldowns, per-thread cooldowns, duplicate inbound checks, duplicate response checks, link blocking, emergency stop, audit, and journal rules. Live batch mode must stop on configured auth/provider failures, must not retry the same item in the same run, and must not support DMs, likes, follows, quotes, cold replies, scheduler/daemon/infinite loops, xurl mutation, manual canary paths, broadcast controllers, or uncontrolled batch execution.

GoHAM mode, when introduced later, must remain bounded high-autonomy: visible operator controls, policy checks, budgets, rate limits, audit records, and a kill switch are still required.
