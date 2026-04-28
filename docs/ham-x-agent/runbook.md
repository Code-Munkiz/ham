# HAM-on-X Phase 1A Runbook

## Local Setup

1. Copy `.env.example` to `.env`.
2. Keep `HAM_X_AUTONOMY_ENABLED=false`.
3. Keep `HAM_X_DRY_RUN=true`.
4. Use staging credentials only if credentials are needed for future local testing.

## Smoke Test

Run the focused tests:

```bash
python -m pytest tests/test_ham_x_phase1a.py -v
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
```

In Phase 1A, mutating actions are blocked even if these values are changed.

## Autonomy Modes

- `draft`: queue draft content only.
- `approval`: future explicit human approval mode.
- `guarded`: future capped execution mode with policy, budget, and rate checks.
- `goham`: future bounded high-autonomy mode with visible controls and audit trails, not reckless automation.
