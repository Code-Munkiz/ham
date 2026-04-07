---
name: prompt-budget-audit
description: >-
  Audit token budgets across the Ham swarm to prevent context window overflows.
  Use when checking prompt sizes, reviewing MAX_* constants, or diagnosing
  truncation issues in agent outputs.
---

# Prompt Budget Audit

## When to Use

- Diagnosing agent output truncation or degraded quality
- Reviewing `MAX_*` constants in `src/memory_heist.py`
- Checking total prompt size before supervisory orchestration execution
- After changing instruction files, config, or git diff caps

## Audit Steps

1. Read `src/memory_heist.py` and note all `MAX_*` constants.
2. For each active role in `src/swarm_agency.py` (or current orchestration path), estimate total prompt/backstory size:
   - `ContextBuilder.build()` output size (instructions + git state + tree + config)
   - Plus the static backstory string
3. Compare against the model's context window (check `src/llm_client.py` for model ID).
4. Flag any agent whose estimated prompt exceeds 50% of the context window.
5. Check `SessionMemory.estimate_tokens()` -- the `chars // 4` heuristic can be 20-30% off for code-heavy content. Flag if compaction threshold is too close to the window limit.

## Common Model Context Windows

| Model | Window | 50% Budget |
|-------|--------|------------|
| Claude 3.5 Sonnet | 200K | 100K |
| GPT-4o | 128K | 64K |
| Llama 3.1 70B | 128K | 64K |

## Red Flags

- `git_diff()` returning >8K chars without `MAX_DIFF_CHARS` cap
- `_summarize()` Timeline section with >20 messages
- `_merge_summaries()` nesting without truncation
- `render_instruction_files()` hitting the budget cap silently
