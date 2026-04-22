#!/usr/bin/env python3
"""
Entry point: load env, assemble a minimal Ham run context, accept a CLI prompt.
"""
import argparse
import copy
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.bridge.runtime import run_bridge_v0
from src.hermes_feedback import HermesReviewer
from src.ham.run_persist import persist_ham_run_record
from src.ham.one_shot_run import build_runtime_intent, select_intent_profile
from src.llm_client import configure_litellm_env
from src.swarm_agency import assemble_ham_run

MAX_REVIEW_CONTEXT_CHARS = 1_000
# Hermes review echoes bridge JSON + context; huge strings break terminal wrap/reflow.
MAX_STDOUT_HERMES_CODE_CHARS = 1_200
MAX_STDOUT_HERMES_CONTEXT_CHARS = 900


def _build_runtime_envelope(
    prompt: str,
    profile_id: str,
    bridge_result: object,
    review: dict[str, object],
) -> dict[str, object]:
    if hasattr(bridge_result, "model_dump"):
        bridge_payload = bridge_result.model_dump()
    elif hasattr(bridge_result, "dict"):
        bridge_payload = bridge_result.dict()
    else:
        bridge_payload = bridge_result
    return {
        "prompt_summary": prompt[:200],
        "intent_profile_id": profile_id,
        "bridge_result": bridge_payload,
        "hermes_review": review,
    }


def _truncate_envelope_for_stdout(envelope: dict[str, object]) -> dict[str, object]:
    """Shorten review strings for human stdout; full envelope is still written under .ham/runs/."""
    out = copy.deepcopy(envelope)
    hr = out.get("hermes_review")
    if not isinstance(hr, dict):
        return out
    for key, limit in (
        ("code", MAX_STDOUT_HERMES_CODE_CHARS),
        ("context", MAX_STDOUT_HERMES_CONTEXT_CHARS),
    ):
        val = hr.get(key)
        if isinstance(val, str) and len(val) > limit:
            omitted = len(val) - limit
            hr[key] = (
                val[:limit]
                + f"... [truncated {omitted} chars; full JSON in .ham/runs/]"
            )
    return out


def _dump_json(data: object, *, indent: int | None = None) -> str:
    if hasattr(data, "model_dump"):
        payload = data.model_dump()
    elif hasattr(data, "dict"):
        payload = data.dict()
    else:
        payload = data
    if indent is not None:
        return json.dumps(payload, sort_keys=True, ensure_ascii=True, indent=indent)
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    configure_litellm_env()

    parser = argparse.ArgumentParser(description="ham — autonomous developer swarm")
    parser.add_argument(
        "--compact-json",
        action="store_true",
        help="Emit RUNTIME_RESULT as a single line (for scripts). Default is indented JSON for readability in terminals.",
    )
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

    cwd = Path.cwd().resolve()
    assembly = assemble_ham_run(args.prompt, project_root=cwd)
    profile_id = select_intent_profile(assembly.user_prompt)
    intent = build_runtime_intent(assembly.user_prompt, profile_id, cwd)
    bridge_result = run_bridge_v0(assembly, intent)
    review_assembly = assembly
    if bridge_result.mutation_detected is True:
        review_assembly = assemble_ham_run(assembly.user_prompt, project_root=cwd)
    review_context = review_assembly.critic_backstory[:MAX_REVIEW_CONTEXT_CHARS]
    bridge_json = _dump_json(bridge_result)
    # Prefer the actual workspace mutation over the bridge metadata envelope so
    # Hermes reviews the code Droid changed rather than the command evidence.
    review_code = bridge_result.mutation_diff or bridge_json

    try:
        review = HermesReviewer().evaluate(review_code, review_context)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        review = {
            "ok": False,
            "notes": [f"Hermes review handoff failed ({type(exc).__name__})."],
            "code": review_code[:1000],
            "context": review_context[:1000],
        }

    envelope = _build_runtime_envelope(
        prompt=assembly.user_prompt,
        profile_id=profile_id,
        bridge_result=bridge_result,
        review=review,
    )
    persist_ham_run_record(
        cwd,
        prompt=assembly.user_prompt,
        profile_id=profile_id,
        bridge_result=bridge_result,
        review=review,
    )
    to_print = (
        envelope
        if args.compact_json
        else _truncate_envelope_for_stdout(envelope)
    )
    dumped = _dump_json(to_print, indent=None if args.compact_json else 2)
    if args.compact_json:
        print("RUNTIME_RESULT:", dumped)
    else:
        print("RUNTIME_RESULT:\n" + dumped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
