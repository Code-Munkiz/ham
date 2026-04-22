"""
Defensive argv validation for the remote droid runner.

HAM builds argv from the workflow registry; the runner still validates so a compromised
or misconfigured API cannot turn this endpoint into a generic shell gateway.
"""

from __future__ import annotations

from pathlib import Path

# Exact-match forbidden tokens (any position in argv).
_FORBIDDEN_EXACT = frozenset(
    {
        "--skip-permissions-unsafe",
    }
)

_MAX_ARGV_LEN = 256
_MAX_ARG_STR_LEN = 200_000


def validate_remote_droid_argv(argv: list[str], *, expected_cwd: Path) -> str | None:
    """
    Return a human-readable rejection reason, or None if argv is acceptable.

    Rules (Phase 1):
    - argv[0] must be exactly ``droid`` (PATH resolution on the runner host).
    - argv[1] must be ``exec``.
    - Only known flags before the final positional prompt: ``--cwd``, ``--output-format``,
      ``--auto``, ``--disabled-tools``.
    - ``--cwd`` value must resolve to the same path as ``expected_cwd``.
    - ``--output-format`` value must be ``json``.
    - ``--auto`` value must be ``low`` (only level used by current workflows).
    - No forbidden tokens (e.g. ``--skip-permissions-unsafe``).
    - Final element is the prompt; it must not start with ``--``.
    """
    if not argv:
        return "argv must be non-empty."
    if len(argv) > _MAX_ARGV_LEN:
        return f"argv too long (max {_MAX_ARGV_LEN} elements)."
    for a in argv:
        if len(a) > _MAX_ARG_STR_LEN:
            return "argv element exceeds maximum length."
        if "\x00" in a:
            return "argv contains NUL byte."

    if argv[0] != "droid":
        return "argv[0] must be the bare command name `droid` (no paths or wrappers)."
    if len(argv) < 3 or argv[1] != "exec":
        return "argv must begin with `droid exec`."

    for tok in argv:
        if tok in _FORBIDDEN_EXACT:
            return f"Forbidden flag or token: {tok!r}."

    try:
        resolved_request = expected_cwd.expanduser().resolve()
    except OSError as exc:
        return f"Invalid cwd: {exc}"

    i = 2
    seen_cwd = False
    n = len(argv)
    # Last element is always the prompt (non-flag).
    while i < n - 1:
        flag = argv[i]
        if flag in _FORBIDDEN_EXACT:
            return f"Forbidden flag or token: {flag!r}."
        if not flag.startswith("--"):
            return f"Expected a flag before the prompt, got {flag!r}."
        if flag == "--cwd":
            if i + 1 >= n - 1:
                return "`--cwd` is missing its value."
            try:
                arg_cwd = Path(argv[i + 1]).expanduser().resolve()
            except OSError as exc:
                return f"Invalid `--cwd` path: {exc}"
            if arg_cwd != resolved_request:
                return "`argv` `--cwd` does not match request `cwd`."
            seen_cwd = True
            i += 2
            continue
        if flag == "--output-format":
            if i + 1 >= n - 1:
                return "`--output-format` is missing its value."
            if argv[i + 1] != "json":
                return "Only `--output-format json` is allowed."
            i += 2
            continue
        if flag == "--auto":
            if i + 1 >= n - 1:
                return "`--auto` is missing its value."
            if argv[i + 1] != "low":
                return "Only `--auto low` is allowed."
            i += 2
            continue
        if flag == "--disabled-tools":
            if i + 1 >= n - 1:
                return "`--disabled-tools` is missing its value."
            if not argv[i + 1].strip():
                return "`--disabled-tools` value must be non-empty."
            i += 2
            continue
        return f"Unknown or disallowed flag: {flag!r}."

    if not seen_cwd:
        return "argv must include `--cwd` matching request cwd."

    prompt = argv[-1]
    if prompt.startswith("--"):
        return "Final argv element (prompt) must not start with `--`."

    return None
