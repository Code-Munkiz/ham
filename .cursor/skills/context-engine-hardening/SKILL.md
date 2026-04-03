---
name: context-engine-hardening
description: >-
  Harden memory_heist.py against token blowouts, unbounded growth, cross-platform
  path bugs, stale Claude references, and continuation/parser marker drift. Use when
  modifying memory_heist.py, fixing compaction logic, capping diffs, or adding safety
  limits to the Context Engine.
---

# Context Engine Hardening

## When to Use

- Modifying `src/memory_heist.py`
- Fixing token budget issues, diff size blowouts, or summary growth
- Ensuring cross-platform path handling (Windows/Linux/macOS)
- Removing residual Claude-specific naming
- Changing `_format_continuation()` or `_extract_prior_summary()`

## Checklist

1. Read `src/memory_heist.py` before making changes.
2. Verify `IGNORE_DIRS` includes `.sessions` and `.hermes`.
3. Verify all instruction constants reference Ham names (`SWARM.md`, `.ham`).
4. Verify `discover_config()` uses `.ham.json` / `.ham/` paths only.
5. Check that `git_diff()` output is capped by `MAX_DIFF_CHARS` (when implemented).
6. Check that `_summarize()` caps the Timeline to the last N messages (e.g. 20).
7. Check that `_merge_summaries()` truncates the previous summary to prevent nesting growth.
8. Check that `_extract_key_files()` does NOT gate on `"/" in token` only — extension-based detection for cross-platform paths.
9. Check that `_format_continuation()` uses agent-appropriate language, not chatbot phrasing.
10. **Continuation / parser coupling**: If `_format_continuation()` text changes, update `_extract_prior_summary()` `end_markers` to match; keep legacy markers for backward compatibility with existing session JSON until migrated.
11. Run lints on `src/memory_heist.py` after changes.
12. Add or update tests for any behavioral change (see Repo Context Regression Testing skill).

## Key Constants to Audit

| Constant | Default | Purpose |
|----------|---------|---------|
| `MAX_INSTRUCTION_FILE_CHARS` | 4,000 | Per-file instruction cap |
| `MAX_TOTAL_INSTRUCTION_CHARS` | 12,000 | Total instruction budget |
| `MAX_DIFF_CHARS` | 8,000 | Git diff output cap |
| `MAX_SUMMARY_CHARS` | 4,000 | Compaction summary cap |

All of these should be overridable via `ContextBuilder` constructor params once wiring is complete.
