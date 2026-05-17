---
name: diagnose
description: Structured diagnosis loop: reproduce, minimize, hypothesize, instrument, fix, and regression-test.
---

# Diagnose (HAM Local)

Follow a disciplined debug loop:

1. Build a deterministic feedback loop first.
2. Reproduce the exact reported issue.
3. Rank 3-5 falsifiable hypotheses.
4. Instrument minimally with tagged debug output.
5. Add regression coverage at the correct seam, then fix.
6. Re-run original repro and clean temporary debug scaffolding.

Always read and follow `docs/agents/ham-safety.md`.

## Attribution

Adapted from [`mattpocock/skills`](https://github.com/mattpocock/skills), `skills/engineering/diagnose/SKILL.md` (MIT License).
