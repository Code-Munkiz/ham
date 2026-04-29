# HAM-on-X Smoke Testing

Phase 1D smoke tests validate the HAM-on-X safety path without enabling posting.

## Modes

- `local`: Uses fixture candidate data and runs the real dry-run pipeline through scoring, drafting, policy review, budget/rate checks, autonomy decision, queue/audit output.
- `env`: Checks redacted environment status and safe defaults.
- `x-readonly`: Plans a read-only X search shape. Live execution is disabled unless `HAM_X_ENABLE_LIVE_SMOKE=true`; Phase 1D still returns not implemented.
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

Run the narrow tests:

```bash
python -m pytest tests/test_ham_x_phase1a.py tests/test_ham_x_smoke.py -v
```

## External Smoke Recommendation

The next external smoke should run `x-readonly` with staging credentials and `HAM_X_ENABLE_LIVE_SMOKE=true` only after a real read-only xurl adapter exists. It must verify search-only behavior and capture redacted output without enabling post, quote, like, or reply.
