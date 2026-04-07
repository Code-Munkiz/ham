"""
Transitional orchestration scaffold: repo context + role prompts for a future
Hermes-supervised run (no third-party orchestration framework).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.llm_client import configure_litellm_env, get_llm_client
from src.memory_heist import ProjectContext
from src.tools.droid_executor import droid_executor


@dataclass(frozen=True)
class HamRunAssembly:
    """Prepared context and callables for a single user-directed run (scaffold)."""

    user_prompt: str
    architect_backstory: str
    commander_backstory: str
    critic_backstory: str
    llm_client: Any
    droid_executor: Callable[[str], str]


def assemble_ham_run(user_prompt: str) -> HamRunAssembly:
    """Discover repo context once, render per-role budgets, attach Droid + LLM handles."""
    configure_litellm_env()
    llm = get_llm_client()

    project = ProjectContext.discover()

    arch_total = project.config.get("architect_instruction_chars", 16_000)
    cmd_total = project.config.get("commander_instruction_chars", 4_000)
    critic_total = project.config.get("critic_instruction_chars", 8_000)

    arch_ctx = project.render(
        max_total_instruction_chars=arch_total,
        max_diff_chars=8_000,
    )
    cmd_ctx = project.render(
        max_total_instruction_chars=cmd_total,
        max_diff_chars=2_000,
    )
    critic_ctx = project.render(
        max_total_instruction_chars=critic_total,
        max_diff_chars=8_000,
    )

    architect_backstory = (
        "You plan structure and interfaces before implementation.\n\n" + arch_ctx
    )
    commander_backstory = (
        "You break goals into steps and invoke the Droid executor when needed.\n\n"
        + cmd_ctx
    )
    critic_backstory = (
        "You review outputs and record quality signals for the Hermes loop.\n\n"
        + critic_ctx
    )

    return HamRunAssembly(
        user_prompt=user_prompt,
        architect_backstory=architect_backstory,
        commander_backstory=commander_backstory,
        critic_backstory=critic_backstory,
        llm_client=llm,
        droid_executor=droid_executor,
    )
