---
name: agent-context-wiring
description: >-
  Wire memory_heist ContextBuilder into Hermes-supervised role prompts in swarm_agency.py
  using a single shared ProjectContext and per-role render budgets. Use when connecting
  Hermes-led flows to repo context, adjusting budgets, or integrating SessionMemory. (No CrewAI.)
---

# Agent Context Wiring

## When to Use

- Integrating `ContextBuilder` into `src/swarm_agency.py`
- Setting per-role token / instruction / diff budgets
- Wiring `SessionMemory` into the active Hermes-supervised flow

## Anti-pattern: N full scans

**Do not** create one `ContextBuilder()` per agent if each constructor calls `ProjectContext.discover()` independently. That repeats `scan_workspace`, instruction discovery, config merge, and multiple git subprocess calls.

## Preferred pattern: one discovery, vary render only

1. Call `ProjectContext.discover()` **once** (or construct one `ContextBuilder` that owns a single `project` snapshot).
2. For each role, render context with **different budgets** (instruction caps, diff caps) by passing parameters into render helpers — or add a small API on `ContextBuilder` / `ProjectContext` such as `render_for_role(budgets=...)`.
3. Concatenate each role's static instruction line + that rendered string into the active prompt/backstory surface.

Example shape (adapt to actual `memory_heist` API after hardening):

```python
from src.memory_heist import ProjectContext
from src.swarm_agency import HamRunAssembly

def assemble_ham_run(user_prompt: str) -> HamRunAssembly:
    project = ProjectContext.discover()

    arch_text = project.render(
        max_total_instruction_chars=16_000,
        max_diff_chars=8_000,
    )
    cmd_text = project.render(
        max_total_instruction_chars=4_000,
        max_diff_chars=2_000,
    )
    # ... critic with its own budgets; attach llm + droid per production wiring ...

    return HamRunAssembly(
        user_prompt=user_prompt,
        architect_backstory=f"You plan structure and interfaces.\n\n{arch_text}",
        commander_backstory=(
            "You are the Hermes-supervised routing surface: delegate execution to Droid.\n\n"
            f"{cmd_text}"
        ),
        critic_backstory="...",
        llm_client=None,
        droid_executor=lambda cmd: "...",
    )
```

Until `ProjectContext.render()` accepts budget overrides, implement the minimal change in `memory_heist.py` to support this pattern rather than constructing multiple discoverers.

## Config-driven budgets

Prefer reading per-role budgets from merged project config (`discover_config` / `.ham.json`) with sane code defaults. Avoid leaving magic numbers only in `swarm_agency.py` long-term.

## Budget guidelines (defaults until config exists)

| Role surface | Instruction budget (total) | Diff budget | Rationale |
|-------|---------------------------|-------------|-----------|
| Architect | Higher (e.g. 16,000) | Full (e.g. 8,000) | Planning / interfaces |
| Hermes routing (`commander_*` config keys) | Lower (e.g. 4,000) | Tighter (e.g. 2,000) | Delegation & sequencing |
| Hermes review / critic | Medium (e.g. 8,000) | Default | Critique & learning context |

## Verification

1. Every Hermes-supervised role surface receives repo-grounded context in its prompt/backstory.
2. Repo scan + git capture runs **once** per `assemble_ham_run` build (unless explicitly refreshing after Droid).
3. Budgets are tunable via config when available.
