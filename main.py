#!/usr/bin/env python3
"""
Entry point: load env, initialize Crew from swarm_agency, accept a CLI prompt.
"""
import argparse
import os
import sys

from dotenv import load_dotenv

from src.llm_client import configure_litellm_env
from src.swarm_agency import build_swarm_crew


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    configure_litellm_env()

    parser = argparse.ArgumentParser(description="ham — autonomous developer swarm")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Hello, swarm.",
        help="User instruction for the crew (default: short demo prompt).",
    )
    args = parser.parse_args(argv)

    if not os.getenv("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY is not set. Copy .env.example to .env and add your key.")
        print("Prompt (would be sent to crew):", args.prompt)
        return 0

    crew = build_swarm_crew(args.prompt)
    # crew.kickoff() when you are ready to call the API
    print("Crew assembled (scaffold). Prompt:", args.prompt)
    print("Call crew.kickoff() to run the crew.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
