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

Phase 2A manual canary execution is not autonomous. It may only handle one explicitly confirmed `post` or `quote`, remains capped to one action per run by default, respects daily caps and emergency stop, and must pass this deterministic safety policy before any provider call.

GoHAM mode, when introduced later, must remain bounded high-autonomy: visible operator controls, policy checks, budgets, rate limits, audit records, and a kill switch are still required.
