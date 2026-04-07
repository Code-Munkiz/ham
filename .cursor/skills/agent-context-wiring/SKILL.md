---
name: agent-context-wiring
description: >-
  Wire memory_heist ContextBuilder into active orchestration role prompts in swarm_agency.py
  using a single shared ProjectContext and per-role render budgets. Use when connecting
  supervisory/execution flows to repo context, adjusting budgets, or integrating SessionMemory.
---

# Agent Context Wiring

## When to Use

- Integrating `ContextBuilder` into `src/swarm_agency.py`
- Setting per-role token / instruction / diff budgets
- Wiring `SessionMemory` into the active orchestration flow

## Anti-pattern: N full scans

**Do not** create one `ContextBuilder()` per agent if each constructor calls `ProjectContext.discover()` independently. That repeats `scan_workspace`, instruction discovery, config merge, and multiple git subprocess calls.

## Preferred pattern: one discovery, vary render only

1. Call `ProjectContext.discover()` **once** (or construct one `ContextBuilder` that owns a single `project` snapshot).
2. For each role, render context with **different budgets** (instruction caps, diff caps) by passing parameters into render helpers — or add a small API on `ContextBuilder` / `ProjectContext` such as `render_for_role(budgets=...)`.
3. Concatenate each role's static instruction line + that rendered string into the active prompt/backstory surface.

Example shape (adapt to actual `memory_heist` API after hardening):

```python
from pathlib import Path
from src.memory_heist import ProjectContext  # or ContextBuilder with shared project

def build_swarm_crew(user_prompt: str) -> Crew:
    root = Path.cwd()
    project = ProjectContext.discover(root)

    arch_text = project.render(
        max_instruction_file_chars=4_000,
        max_total_instruction_chars=16_000,
        max_diff_chars=8_000,
    )
    cmd_text = project.render(
        max_instruction_file_chars=2_000,
        max_total_instruction_chars=4_000,
        max_diff_chars=2_000,
    )
    # ... critic with its own budgets ...

    architect = Agent(
        backstory=f"You plan structure and interfaces.\n\n{arch_text}",
        ...
    )
```

Until `ProjectContext.render()` accepts budget overrides, implement the minimal change in `memory_heist.py` to support this pattern rather than constructing multiple discoverers.

## Config-driven budgets

Prefer reading per-role budgets from merged project config (`discover_config` / `.ham.json`) with sane code defaults. Avoid leaving magic numbers only in `swarm_agency.py` long-term.

## Budget guidelines (defaults until config exists)

| Role | Instruction budget (total) | Diff budget | Rationale |
|-------|---------------------------|-------------|-----------|
| Hermes supervisory context | Higher (e.g. 16,000) | Full (e.g. 8,000) | Routing, policy, quality context |
| Droid execution context | Lower (e.g. 4,000) | Tighter (e.g. 2,000) | Task scope, actionable execution details |
| Hermes review context | Medium (e.g. 8,000) | Default | Enough to critique and learn |

## Verification

1. Every active orchestration role receives repo-grounded context in its prompt/backstory surface.
2. Repo scan + git capture runs **once** per orchestration build (unless explicitly refreshing after Droid).
3. Budgets are tunable via config when available.
