# HAM-on-X Environment

Use separate credentials for staging and production. Do not share production X or xAI credentials with local test runs.

## Variables

```dotenv
XAI_API_KEY=
X_API_KEY=
X_API_SECRET=
X_ACCESS_TOKEN=
X_ACCESS_TOKEN_SECRET=
X_BEARER_TOKEN=
HAM_X_AUTONOMY_ENABLED=false
HAM_X_DRY_RUN=true
HAM_X_MAX_POSTS_PER_HOUR=0
HAM_X_MAX_QUOTES_PER_HOUR=0
HAM_X_MAX_SEARCHES_PER_HOUR=30
HAM_X_DAILY_SPEND_LIMIT_USD=5
HAM_X_MODEL=grok-4.1-fast
HAM_X_XURL_BIN=xurl
HAM_X_CATALOG_SKILL_ID=bundled.social-media.xurl
HAM_X_REVIEW_QUEUE_PATH=.data/ham-x/review_queue.jsonl
HAM_X_AUDIT_LOG_PATH=.data/ham-x/audit.jsonl
```

## Platform Context Defaults

The Phase 1A scaffold defaults to the official HAM PR agent:

```text
tenant_id=ham-official
agent_id=ham-pr-rockstar
campaign_id=base-stealth-launch
account_id=ham-x-official
profile_id=ham.default
autonomy_mode=draft
policy_profile_id=platform-default
brand_voice_id=ham-canonical
```

Future tenant-created X agents should use tenant-scoped values for these fields while preserving the same review and audit schema.

`HAM_X_CATALOG_SKILL_ID` links xurl plans to the vendored Hermes runtime catalog entry `bundled.social-media.xurl`. It is metadata only in Phase 1A and does not install or execute the skill.

## Secret Handling

- Never commit `.env` or real tokens.
- Keep staging and production credentials separate.
- Do not print token values in logs, audit rows, review records, or command output.
- Prefer host secret managers for deployed environments.

## Phase 1A Defaults

Autonomy is disabled and dry-run is enabled by default. Mutating limits default to zero, so post, quote, and like actions stay blocked even if a caller constructs a mutating plan.
