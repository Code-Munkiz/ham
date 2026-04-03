---
name: hermes-review-loop-validation
description: >-
  Validate the Hermes critic review loop: verify the Critic agent receives
  correct context, invokes HermesReviewer.evaluate(), and persists learning
  signals to FTS5. Use when modifying hermes_feedback.py, the Critic agent
  definition, or the review pipeline.
---

# Hermes Review Loop Validation

## When to Use

- Modifying `src/hermes_feedback.py`
- Changing the Hermes Critic agent in `src/swarm_agency.py`
- Integrating the real hermes-agent client
- Verifying FTS5 persistence after reviews

## Review Loop Contract

```
Commander output
      |
      v
Hermes Critic agent (CrewAI)
      |
      v
HermesReviewer.evaluate(code, context)
      |
      v
FTS5 DB (persist learning signals)
```

## Validation Checklist

1. The Critic agent's `goal` must reference review and learning, not planning or execution.
2. The Critic agent must NOT have `droid_executor` in its `tools` list.
3. `HermesReviewer.evaluate()` must receive the actual code output, not a summary.
4. `HermesReviewer.evaluate()` must receive context from `ContextBuilder` so it knows repo state.
5. When the real hermes-agent client is integrated:
   - Verify it writes to `.hermes/` directory
   - Verify `.hermes/` is in `IGNORE_DIRS` so agents don't ingest the DB as source
6. The evaluate response must include structured fields: `ok`, `notes`, `code`, `context` at minimum.

## Current State

`HermesReviewer` is a stub. The `evaluate()` method returns a hardcoded dict.
Integration with the real hermes-agent API is pending.
