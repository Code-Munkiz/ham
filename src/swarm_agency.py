"""
Hermes-supervised context assembly: one `ProjectContext.discover()` and per-role
render budgets for Architect, routing/delegation, and critic prompt surfaces.

There is no CrewAI or third-party orchestration framework here—only shared repo
context wired for Hermes-led supervisory flows (`main.py`, `hermes_feedback.py`).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.bridge.browser_adapters import build_browser_executor
from src.llm_client import configure_litellm_env, get_llm_client
from src.memory_heist import ProjectContext, browser_policy_from_config
from src.registry.backends import BackendRegistry, DEFAULT_BACKEND_REGISTRY
from src.tools.droid_executor import droid_executor


@dataclass(frozen=True)
class HamRunAssembly:
    """Prepared context and callables for a single user-directed run (scaffold)."""

    user_prompt: str
    architect_backstory: str
    commander_backstory: str
    critic_backstory: str
    llm_client: Any
    backend_registry: BackendRegistry
    droid_executor: Callable[..., Any]
    browser_executor: Any
    browser_adapter: str


def assemble_ham_run(user_prompt: str, project_root: Path | None = None) -> HamRunAssembly:
    """Discover repo context once, render per-role budgets, attach Droid + LLM handles."""
    configure_litellm_env()
    llm = get_llm_client()

    project = ProjectContext.discover(project_root)
    browser_policy = browser_policy_from_config(project.config)
    browser_adapter = str(browser_policy.get("adapter", "playwright"))

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
        "You are the Hermes-supervised routing surface: break goals into steps, "
        "delegate execution-heavy work to the Droid executor, and preserve "
        "separation of duties.\n\n"
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
        backend_registry=DEFAULT_BACKEND_REGISTRY,
        droid_executor=droid_executor,
        browser_executor=build_browser_executor(browser_adapter),
        browser_adapter=browser_adapter,
    )
