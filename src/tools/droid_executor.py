"""
CrewAI tool: invoke Factory Droid CLI via subprocess (implementation TBD).
"""
from crewai.tools import tool


@tool("droid_executor")
def droid_executor(command: str) -> str:
    """
    Run a Factory Droid CLI command in a subprocess.

    Args:
        command: Shell-style command string for the droid binary (placeholder).

    Returns:
        Captured stdout/stderr summary (stub).
    """
    return f"[droid_executor placeholder] would run: {command!r}"
