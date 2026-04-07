#!/usr/bin/env python3
"""
Entry point: load env, assemble a minimal Ham run context, accept a CLI prompt.
"""
import argparse
import os
import sys

from dotenv import load_dotenv

from src.llm_client import configure_litellm_env
from src.swarm_agency import assemble_ham_run


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    configure_litellm_env()

    parser = argparse.ArgumentParser(description="ham — autonomous developer swarm")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Hello, swarm.",
        help="User instruction for this run (default: short demo prompt).",
    )
    args = parser.parse_args(argv)

    if not os.getenv("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY is not set. Copy .env.example to .env and add your key.")
        print("Prompt (would be used for this run):", args.prompt)
        return 0

    assembly = assemble_ham_run(args.prompt)
    print("Run assembly prepared (scaffold). Prompt:", assembly.user_prompt)
    print(
        "Supervisory execution path is minimal; wire Hermes routing and Droid "
        "invocation in a follow-up milestone."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
