from __future__ import annotations

from pathlib import Path

from src.bridge.contracts import ExecutionIntent, PolicyDecision

POLICY_VERSION = "bridge-v0"

# v0: intentionally narrow, read-only command scope
ALLOWLIST: dict[str, set[str]] = {
    "inspect": {"python", "git"},
    "validate": {"python", "pytest"},
}
DENYLIST = {
    "bash",
    "sh",
    "cmd",
    "powershell",
    "pwsh",
    "curl",
    "wget",
    "pip",
    "npm",
    "rm",
    "del",
    "mv",
    "move",
}

MAX_COMMANDS_CEILING = 3
MAX_TIMEOUT_CEILING = 30
MAX_STDOUT_CEILING = 8_000
MAX_STDERR_CEILING = 8_000
MAX_TOTAL_OUTPUT_CEILING = 16_000
READ_ONLY_GIT_SUBCOMMANDS = {"status", "diff", "log", "show", "rev-parse"}
ALLOWED_ENV_OVERRIDE_KEYS = {"PYTHONUTF8"}
SUSPICIOUS_PYTHON_C_TOKENS = {
    "open(",
    ".write(",
    "socket",
    "requests",
    "urllib",
    "http://",
    "https://",
    "subprocess",
    "os.remove",
    "os.rmdir",
    "os.unlink",
    "pathlib.path.write",
    "shutil",
    "connect(",
}


def validate_intent(intent: ExecutionIntent, *, repo_root: Path | None = None) -> PolicyDecision:
    reasons: list[str] = []
    root = (repo_root or Path.cwd()).resolve()

    if not intent.intent_id or not intent.request_id or not intent.run_id:
        reasons.append("Missing required correlation IDs.")

    if intent.scope.allow_network:
        reasons.append("Network access is not allowed in Bridge v0.")
    if intent.scope.allow_write:
        reasons.append("Write access is not allowed in Bridge v0.")

    if intent.limits.max_commands > MAX_COMMANDS_CEILING:
        reasons.append("max_commands exceeds Bridge v0 ceiling.")
    if intent.limits.timeout_sec_per_command > MAX_TIMEOUT_CEILING:
        reasons.append("timeout_sec_per_command exceeds Bridge v0 ceiling.")
    if intent.limits.max_stdout_chars > MAX_STDOUT_CEILING:
        reasons.append("max_stdout_chars exceeds Bridge v0 ceiling.")
    if intent.limits.max_stderr_chars > MAX_STDERR_CEILING:
        reasons.append("max_stderr_chars exceeds Bridge v0 ceiling.")
    if intent.limits.max_total_output_chars > MAX_TOTAL_OUTPUT_CEILING:
        reasons.append("max_total_output_chars exceeds Bridge v0 ceiling.")
    if len(intent.commands) > intent.limits.max_commands:
        reasons.append("Intent has more commands than allowed by limits.max_commands.")

    allowed_execs = ALLOWLIST.get(intent.task_class, set())
    for cmd in intent.commands:
        if not cmd.argv:
            reasons.append(f"Command {cmd.command_id} has empty argv.")
            continue
        executable = cmd.argv[0].strip().lower()
        if executable in DENYLIST:
            reasons.append(f"Command {cmd.command_id} uses denied executable: {executable}.")
        if executable not in allowed_execs:
            reasons.append(
                f"Command {cmd.command_id} executable '{executable}' is not in allowlist for task_class '{intent.task_class}'."
            )
        profile_reason = _profile_rejection_reason(intent.task_class, cmd.argv)
        if profile_reason is not None:
            reasons.append(f"Command {cmd.command_id} rejected: {profile_reason}")
        env_reason = _env_override_rejection_reason(cmd.env_overrides)
        if env_reason is not None:
            reasons.append(f"Command {cmd.command_id} rejected: {env_reason}")
        if _looks_like_shell_string(cmd.argv):
            reasons.append(f"Command {cmd.command_id} appears to require shell-string execution.")
        if not _within_scope(cmd.working_dir, intent.scope.allowed_roots, root):
            reasons.append(f"Command {cmd.command_id} working_dir escapes allowed scope.")

    accepted = not reasons
    return PolicyDecision(
        accepted=accepted,
        reasons=reasons,
        policy_version=POLICY_VERSION,
    )


def _looks_like_shell_string(argv: list[str]) -> bool:
    if len(argv) != 1:
        return False
    token = argv[0]
    shell_tokens = ("&&", "||", "|", ";", ">", "<", "$(", "`", "\n")
    return any(sym in token for sym in shell_tokens)


def _within_scope(working_dir: str, allowed_roots: list[str], cwd: Path) -> bool:
    try:
        wd = _resolve_path(cwd, working_dir)
    except OSError:
        return False
    for root_text in allowed_roots:
        try:
            root_path = _resolve_path(cwd, root_text)
            wd.relative_to(root_path)
            return True
        except (OSError, ValueError):
            continue
    return False


def _resolve_path(cwd: Path, value: str) -> Path:
    p = Path(value)
    if not p.is_absolute():
        p = cwd / p
    return p.resolve(strict=False)


def _profile_rejection_reason(task_class: str, argv: list[str]) -> str | None:
    executable = argv[0].strip().lower()

    if executable == "git":
        if len(argv) < 2:
            return "git requires an explicit read-only subcommand."
        subcommand = argv[1].strip().lower()
        if subcommand not in READ_ONLY_GIT_SUBCOMMANDS:
            return f"git subcommand '{subcommand}' is not allowed in Bridge v0."
        return None

    if executable == "python":
        if len(argv) < 3 or argv[1] != "-c":
            return "python must use a bounded '-c' read-only snippet in Bridge v0."
        snippet = argv[2].lower()
        for token in SUSPICIOUS_PYTHON_C_TOKENS:
            if token in snippet:
                return f"python -c contains disallowed token '{token}'."
        return None

    if executable == "pytest":
        if task_class != "validate":
            return "pytest is only allowed for task_class 'validate'."
        return None

    return None


def _env_override_rejection_reason(env_overrides: dict[str, str]) -> str | None:
    for key, value in env_overrides.items():
        if key not in ALLOWED_ENV_OVERRIDE_KEYS:
            return f"env override key '{key}' is not allowed."
        text = str(value)
        if "\n" in text or "\r" in text or "\x00" in text:
            return f"env override value for '{key}' contains disallowed control characters."
        if len(text) > 200:
            return f"env override value for '{key}' exceeds size limits."
    return None

