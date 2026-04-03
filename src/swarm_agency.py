"""
CrewAI agency: Architect, Commander, Hermes Critic — wired to LiteLLM and tools (placeholder).
"""
from crewai import Agent, Crew, Process, Task

from src.hermes_feedback import HermesReviewer
from src.llm_client import configure_litellm_env, get_crew_llm
from src.tools.droid_executor import droid_executor


def build_swarm_crew(user_prompt: str) -> Crew:
    """Assemble agents and a single kickoff task; expand with real task graphs later."""
    configure_litellm_env()
    llm = get_crew_llm()
    hermes = HermesReviewer()

    architect = Agent(
        role="Architect",
        goal="Shape high-level design and constraints for the swarm.",
        backstory="You plan structure and interfaces before implementation.",
        llm=llm,
        verbose=True,
    )
    commander = Agent(
        role="Commander",
        goal="Delegate work and coordinate execution via available tools.",
        backstory="You break goals into steps and invoke tools when needed.",
        tools=[droid_executor],
        llm=llm,
        verbose=True,
    )
    critic = Agent(
        role="Hermes Critic",
        goal="Review outputs and feed learning signals (Hermes loop — placeholder).",
        backstory=f"Hermes reviewer stub; internal state: {hermes!r}",
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
