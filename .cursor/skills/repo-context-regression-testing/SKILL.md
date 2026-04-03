---
name: repo-context-regression-testing
description: >-
  Test that memory_heist.py correctly scans the repo, discovers configs and
  instructions, captures git state, and compacts sessions without data loss.
  Use when adding tests for Context Engine changes or verifying cross-platform behavior.
---

# Repo Context Regression Testing

## When to Use

- After any behavioral change to `src/memory_heist.py`
- When adding new entries to `IGNORE_DIRS` or `INTERESTING_EXTENSIONS`
- When modifying config discovery, instruction loading, or session compaction
- When verifying cross-platform path handling

## Test Categories

### 1. Workspace Scanning
- `scan_workspace` respects `IGNORE_DIRS` (does not descend into `.sessions`, `.hermes`, `.git`)
- `scan_workspace` respects `max_files` cap
- `scan_workspace` only returns files with `INTERESTING_EXTENSIONS`
- `workspace_tree` respects `max_depth`

### 2. Instruction Discovery
- `discover_instruction_files` finds `SWARM.md` at project root
- `discover_instruction_files` finds `.ham/SWARM.md` in dot-dir
- `discover_instruction_files` deduplicates identical files
- `render_instruction_files` respects `MAX_INSTRUCTION_FILE_CHARS` and `MAX_TOTAL_INSTRUCTION_CHARS`

### 3. Config Discovery
- `discover_config` loads `.ham.json` from home and project dirs
- `discover_config` merges configs with correct precedence (user < project < local)
- `discover_config` does NOT look for `.claude.json`

### 4. Git State
- `git_diff` output is capped at `MAX_DIFF_CHARS`
- `git_diff` includes `--stat` summary when diff is truncated

### 5. Session Compaction
- `_summarize` Timeline is capped at 20 messages
- `_merge_summaries` truncates previous summary to prevent nesting growth
- `compact()` reduces total token estimate, not increases it
- `save()` / `load()` round-trips without data loss
- `_extract_prior_summary` recognizes both current and legacy `_format_continuation` end markers (if backward compatibility is required)

### 6. Cross-Platform
- `_extract_key_files` detects `src/foo.py`, `src\foo.py`, and bare `foo.py`

## Test Location

All tests go in `tests/test_memory_heist.py`. Use `pytest` with `tmp_path` fixtures for filesystem tests.
