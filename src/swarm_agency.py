"""
CrewAI agency: Architect, Commander, Hermes Critic — wired to LiteLLM and tools (placeholder).
"""
from crewai import Agent, Crew, Process, Task

from src.hermes_feedback import HermesReviewer
from src.llm_client import configure_litellm_env, get_crew_llm
from src.memory_heist import ProjectContext
from src.tools.droid_executor import droid_executor


def build_swarm_crew(user_prompt: str) -> Crew:
    """Assemble agents and a single kickoff task; expand with real task graphs later."""
    configure_litellm_env()
    llm = get_crew_llm()

    # Single discovery pass — all agents share one snapshot.
    project = ProjectContext.discover()

    # Per-agent budget overrides from config; code defaults are the fallback.
    arch_total  = project.config.get("architect_instruction_chars", 16_000)
    cmd_total   = project.config.get("commander_instruction_chars",  4_000)
    critic_total = project.config.get("critic_instruction_chars",    8_000)

    arch_ctx   = project.render(max_total_instruction_chars=arch_total,   max_diff_chars=8_000)
    cmd_ctx    = project.render(max_total_instruction_chars=cmd_total,    max_diff_chars=2_000)
    critic_ctx = project.render(max_total_instruction_chars=critic_total, max_diff_chars=8_000)

    architect = Agent(
        role="Architect",
        goal="Shape high-level design and constraints for the swarm.",
        backstory="You plan structure and interfaces before implementation.\n\n" + arch_ctx,
        llm=llm,
        verbose=True,
    )
    commander = Agent(
        role="Commander",
        goal="Delegate work and coordinate execution via available tools.",
        backstory="You break goals into steps and invoke tools when needed.\n\n" + cmd_ctx,
        tools=[droid_executor],
        llm=llm,
        verbose=True,
    )
    HermesReviewer()  # instantiate for side-effects (placeholder)
    critic = Agent(
        role="Hermes Critic",
        goal="Review outputs and feed learning signals (Hermes loop — placeholder).",
        backstory="You review agent outputs and record quality signals.\n\n" + critic_ctx,
        llm=llm,
        verbose=True,
    )

    kickoff = Task(
        description=f"User request (placeholder): {user_prompt}",
        expected_output="A short plan acknowledging the request (scaffold only).",
        agent=architect,
    )

    return Crew(
        agents=[architect, commander, critic],
        tasks=[kickoff],
        process=Process.sequential,
        verbose=True,
    )
