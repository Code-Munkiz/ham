# HAM-on-X Smoke Testing

Phase 1 smoke tests validate the HAM-on-X safety path without enabling posting.

## Modes

- `local`: Uses fixture candidate data and runs the real dry-run pipeline through scoring, drafting, policy review, budget/rate checks, autonomy decision, queue/audit output.
- `env`: Checks redacted environment status and safe defaults.
- `x-readonly`: Runs only a read-only `xurl search` smoke when all live gates are set. It never posts, quotes, likes, replies, follows, or opens timelines/mentions in Phase 1E.
- `xai`: Checks the future xAI smoke surface. Live calls are disabled unless `HAM_X_ENABLE_LIVE_SMOKE=true`; Phase 1D still returns not implemented.
- `e2e-dry-run`: Uses fixture data by default and runs the dry-run pipeline end to end. Future live read-only inputs may be added, but posting remains disabled.

## Safety Invariants

Every smoke result must preserve:

```text
mutation_attempted=false
execution_allowed=false
```

Default live smoke posture:

```dotenv
HAM_X_ENABLE_LIVE_SMOKE=false
HAM_X_DRY_RUN=true
HAM_X_AUTONOMY_ENABLED=false
```

No smoke mode should print or return raw secret values. Use `SmokeResult.redacted_dump()` when displaying results.

## Commands

Run local smoke:

```bash
python - <<'PY'
from src.ham.ham_x.smoke import run_smoke
print(run_smoke("local").redacted_dump())
PY
```

Run environment smoke:

```bash
python - <<'PY'
from src.ham.ham_x.smoke import run_smoke
print(run_smoke("env").redacted_dump())
PY
```

Run read-only X smoke only with staging credentials and explicit gates:

```bash
HAM_X_ENABLE_LIVE_SMOKE=true \
HAM_X_DRY_RUN=true \
HAM_X_AUTONOMY_ENABLED=false \
python - <<'PY'
from src.ham.ham_x.smoke import run_smoke
print(run_smoke("x-readonly").redacted_dump())
PY
```

Phase 1E uses:

```text
xurl search "Base ecosystem autonomous agents" --max-results 10
```

Check the result has `mutation_attempted=false`, `execution_allowed=false`, and `summary.safety_status=read_only_search_only`.

Run the narrow tests:

```bash
python -m pytest tests/test_ham_x_phase1a.py tests/test_ham_x_smoke.py tests/test_ham_x_xurl_readonly.py -v
```

## External Smoke Recommendation

Use staging X credentials only. Do not use production credentials for initial smoke validation, do not paste credential values into chat or logs, and do not change `HAM_X_AUTONOMY_ENABLED=false`.

The read-only adapter should be considered healthy only if the audit log and returned smoke result show a search-only argv, redacted stdout/stderr, `mutation_attempted=false`, and `execution_allowed=false`.
