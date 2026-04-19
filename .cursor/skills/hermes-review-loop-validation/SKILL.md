---
name: hermes-review-loop-validation
description: >-
  Validate the Hermes supervisory critic review loop: verify Hermes receives
  correct context, invokes HermesReviewer.evaluate(), and preserves learning
  signals for later persistence. Use when modifying hermes_feedback.py, the
  supervisory review path, or the review pipeline.
---

# Hermes Review Loop Validation

## When to Use

- Modifying `src/hermes_feedback.py`
- Changing Hermes-supervised context/backstory wiring in `src/swarm_agency.py`
- Integrating the real hermes-agent client
- Verifying FTS5 persistence after reviews

## Review Loop Contract

```
Execution output
      |
      v
Hermes supervisory critic path
      |
      v
HermesReviewer.evaluate(code, context)
      |
      v
FTS5 DB (persist learning signals)
```

## Validation Checklist

1. Hermes review logic must reference critique and learning signals, not broad execution ownership.
2. Hermes review path must not absorb Droid execution responsibilities.
3. `HermesReviewer.evaluate()` must receive the actual code output, not a summary.
4. `HermesReviewer.evaluate()` must receive repo-grounded context (from `ContextBuilder` / `ProjectContext` render path).
5. When the real hermes-agent client is integrated:
   - Verify it writes to `.hermes/` directory
   - Verify `.hermes/` is in `IGNORE_DIRS` so agents don't ingest the DB as source
6. The evaluate response must include structured fields: `ok`, `notes`, `code`, `context` at minimum.

## Current State

`HermesReviewer.evaluate()` is implemented with a stable schema and conservative
fallback behavior. Durable FTS5 learning persistence remains deferred.
