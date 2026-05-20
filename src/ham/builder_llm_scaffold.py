"""LLM-driven scaffold generator — Phase 2 Subsystem 9 (ADR-0011).

Generates file scaffolds for new template kinds via a single LLM call
(BYO OpenRouter key, per ADR-0009).  Every template kind — including
``calculator`` and ``tetris`` — routes through this generator; the legacy
deterministic runtime path was retired (see
``tests/test_legacy_runtime_cut.py``).

Public API:
    ``generate_scaffold(plan, project_id, workspace_id) → ScaffoldResult``

On LLM or validation failure the function retries once with a stricter system
prompt.  If the second attempt also fails, ``LLMScaffoldError`` is raised;
it carries an ``error_code`` (from ``builder_error_codes`` constants) so the
caller can build an ``ErrorEnvelope`` without knowing internals.

Spec: docs/PHASE_2_DESIGN.md § Subsystem 9
ADR: docs/adr/0011-llm-scaffold-staged-by-template-kind.md
ADR: docs/adr/0009-planner-byo-openrouter-with-regex-fallback.md
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from src.ham.builder_error_codes import (
    STEP_MODEL_UNAVAILABLE,
    STEP_VERIFICATION_FAILED,
)
from src.ham.builder_kits import (
    BuilderKit,
    get_kit_for_template_kind,
    render_kit_context,
)
from src.ham.builder_plan import Plan
from src.llm_client import (
    complete_chat_messages_openrouter,
    resolve_openrouter_api_key_for_actor,
    resolve_openrouter_model_name,
)

_LOG = logging.getLogger(__name__)

_MAX_FILES = 24
_MAX_TOTAL_BYTES = 200_000


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ScaffoldResult:
    """Output of :func:`generate_scaffold`.

    Attributes:
        file_changes: List of ``(path, content)`` tuples — one entry per
            generated source file.
        assertions: Plain-English test assertions intended for
            ``builder_verifier`` to evaluate after the scaffold is applied.
    """

    file_changes: list[tuple[str, str]]  # (path, content)
    assertions: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------


class LLMScaffoldError(Exception):
    """Raised when LLM scaffold generation fails after the retry budget.

    Carries ``error_code`` (a constant from ``builder_error_codes``) so the
    caller can embed it in an ``ErrorEnvelope`` without knowing internals.
    """

    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------

_SCAFFOLD_SYSTEM_PROMPT = """\
You are the HAM builder scaffolder. Given a project Plan and a target template kind,
generate ALL the initial source files needed to implement it as a runnable web app.

Output ONLY a JSON object matching this exact schema (no markdown, no prose):

{
  "file_changes": [
    {"path": "src/App.tsx", "content": "...full file content..."},
    {"path": "src/index.css", "content": "..."}
  ],
  "assertions": [
    "The app renders without errors",
    "The UI matches the requested template kind"
  ]
}

Rules:
- file_changes: list of {path, content} objects. Include every file needed.
- Max 24 files. Max 200 KB total content.
- assertions: 1–5 plain-English test assertions for the builder_verifier.
- Output only the JSON object — no markdown fences, no commentary.
- Generate real, runnable code. Use React + TypeScript + Tailwind CSS.
"""

_SCAFFOLD_SYSTEM_PROMPT_STRICT = (
    _SCAFFOLD_SYSTEM_PROMPT
    + "\n\nYour previous response was not valid JSON. "
    "Output ONLY the JSON object starting with { and ending with }. "
    "No markdown code blocks, no extra text."
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> str:
    """Extract the first ``{...}`` block from an LLM response.

    LLMs sometimes wrap output in triple-backtick code fences; this strips
    them and finds the outermost ``{...}`` pair.
    """
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    start = text.find("{")
    if start == -1:
        return text.strip()
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:].strip()


def _parse_scaffold_result(raw: str) -> ScaffoldResult:
    """Parse the raw LLM response into a :class:`ScaffoldResult`.

    Raises:
        json.JSONDecodeError: If the text cannot be parsed as JSON.
        ValueError: If the parsed payload is structurally invalid
            (empty ``file_changes``, wrong types, etc.).
    """
    json_str = _extract_json(raw)
    if not json_str:
        raise ValueError("LLM response is empty or contains no JSON object")

    payload: dict[str, Any] = json.loads(json_str)

    raw_changes = payload.get("file_changes", [])
    if not isinstance(raw_changes, list):
        raise ValueError(
            f"file_changes must be a list, got {type(raw_changes).__name__}"
        )
    if not raw_changes:
        raise ValueError("file_changes is empty — LLM produced no files")

    file_changes: list[tuple[str, str]] = []
    total_bytes = 0
    for item in raw_changes[:_MAX_FILES]:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "")).strip()
        content = str(item.get("content", ""))
        if not path:
            continue
        encoded = content.encode("utf-8")
        total_bytes += len(encoded)
        if total_bytes > _MAX_TOTAL_BYTES:
            _LOG.warning(
                "LLM scaffold: total content exceeds %d bytes — truncating",
                _MAX_TOTAL_BYTES,
            )
            break
        file_changes.append((path, content))

    if not file_changes:
        raise ValueError("No valid file entries found in LLM scaffold output")

    raw_assertions = payload.get("assertions", [])
    assertions: list[str] = [
        str(a) for a in raw_assertions if isinstance(a, str)
    ]

    return ScaffoldResult(file_changes=file_changes, assertions=assertions)


def _get_scaffold_model(*, model_override: str | None = None) -> str:
    """Resolve the model to use for LLM scaffold calls.

    Resolution order: explicit ``model_override`` (from chat ``model_id``),
    then ``HAM_PLANNER_MODEL``, then ``DEFAULT_MODEL`` via
    :func:`resolve_openrouter_model_name` (not ``HERMES_GATEWAY_MODEL``).
    """
    explicit = (model_override or "").strip()
    if explicit:
        if explicit.startswith("openrouter/"):
            return explicit
        return f"openrouter/{explicit}"
    planner = (os.environ.get("HAM_PLANNER_MODEL") or "").strip()
    if planner:
        if planner.startswith("openrouter/"):
            return planner
        return f"openrouter/{planner}"
    return resolve_openrouter_model_name()


def _build_scaffold_messages(
    plan: Plan,
    *,
    system_prompt: str = _SCAFFOLD_SYSTEM_PROMPT,
    kit: BuilderKit | None = None,
) -> list[dict[str, Any]]:
    """Assemble the LLM message list for a scaffold call."""
    template_kind = (plan.metadata or {}).get("template_kind", "unknown")
    steps_text = "\n".join(
        f"  Step {i + 1}: {s.title} — {s.description}"
        for i, s in enumerate(plan.steps)
    )
    user_content = (
        f"Template kind: {template_kind}\n"
        f"User request: {plan.user_message}\n"
        f"Steps:\n{steps_text}"
    )
    if kit is not None:
        user_content = (
            f"{user_content}\n\nBuilder Kit context:\n{render_kit_context(kit)}"
        )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_scaffold(
    plan: Plan,
    project_id: str,
    workspace_id: str,
    *,
    ham_actor: Any | None = None,
    model_override: str | None = None,
) -> ScaffoldResult:
    """Generate a project scaffold via one LLM call (BYO OpenRouter key).

    Mirrors the contract of ``builder_chat_scaffold.maybe_chat_scaffold_for_turn``
    but for new template kinds (ADR-0011).  One LLM call with the Plan + Step
    list as input; produces file changes (path → content).  Retries once with
    a stricter system prompt if the first response is not valid JSON.

    Args:
        plan: The approved :class:`Plan` (Phase 0 schema).  The template kind
            is read from ``plan.metadata["template_kind"]``.
        project_id: Target project ID (for logging and future store writes).
        workspace_id: Target workspace ID (for logging and future store writes).

    Returns:
        :class:`ScaffoldResult` with ``file_changes`` and ``assertions``.

    Raises:
        LLMScaffoldError: When no OpenRouter API key is configured
            (``error_code = STEP_MODEL_UNAVAILABLE``), or when the LLM output
            fails JSON validation after two attempts
            (``error_code = STEP_VERIFICATION_FAILED``).
    """
    api_key = resolve_openrouter_api_key_for_actor(ham_actor)
    if not api_key:
        raise LLMScaffoldError(
            "No OpenRouter API key configured — LLM scaffold cannot run",
            error_code=STEP_MODEL_UNAVAILABLE,
        )

    model = _get_scaffold_model(model_override=model_override)
    template_kind = (plan.metadata or {}).get("template_kind", "")
    kit = get_kit_for_template_kind(template_kind)

    # --- Attempt 1 ---
    messages = _build_scaffold_messages(
        plan, system_prompt=_SCAFFOLD_SYSTEM_PROMPT, kit=kit
    )
    try:
        raw = complete_chat_messages_openrouter(
            messages,
            model_override=model,
            api_key_override=api_key,
        )
        result = _parse_scaffold_result(raw)
        _LOG.info(
            "LLM scaffold produced %d file(s) for plan=%s project=%s workspace=%s model=%s",
            len(result.file_changes),
            plan.plan_id,
            project_id,
            workspace_id,
            model,
        )
        return result
    except (json.JSONDecodeError, ValueError) as first_exc:
        _LOG.warning(
            "LLM scaffold first attempt failed (%s: %s) — retrying with stricter prompt",
            type(first_exc).__name__,
            first_exc,
        )
    except RuntimeError as llm_exc:
        raise LLMScaffoldError(
            f"LLM API error during scaffold (attempt 1): {llm_exc}",
            error_code=STEP_MODEL_UNAVAILABLE,
        ) from llm_exc
    except Exception as llm_exc:  # noqa: BLE001
        raise LLMScaffoldError(
            f"LLM error during scaffold (attempt 1): {llm_exc}",
            error_code=STEP_MODEL_UNAVAILABLE,
        ) from llm_exc

    # --- Attempt 2 (stricter prompt) ---
    messages2 = _build_scaffold_messages(
        plan, system_prompt=_SCAFFOLD_SYSTEM_PROMPT_STRICT, kit=kit
    )
    try:
        raw2 = complete_chat_messages_openrouter(
            messages2,
            model_override=model,
            api_key_override=api_key,
        )
        result2 = _parse_scaffold_result(raw2)
        _LOG.info(
            "LLM scaffold (retry) produced %d file(s) for plan=%s project=%s workspace=%s",
            len(result2.file_changes),
            plan.plan_id,
            project_id,
            workspace_id,
        )
        return result2
    except (json.JSONDecodeError, ValueError) as second_exc:
        raise LLMScaffoldError(
            f"LLM scaffold could not produce valid output after 2 attempts: {second_exc}",
            error_code=STEP_VERIFICATION_FAILED,
        ) from second_exc
    except RuntimeError as llm_exc:
        # LLM API errors (bad key, network, model unavailable) on attempt 2
        raise LLMScaffoldError(
            f"LLM API error during scaffold (attempt 2): {llm_exc}",
            error_code=STEP_MODEL_UNAVAILABLE,
        ) from llm_exc
