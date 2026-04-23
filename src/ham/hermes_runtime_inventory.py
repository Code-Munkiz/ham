"""Read-only Hermes local/runtime inventory via allowlisted CLI + sanitized config.

Does not mutate ~/.hermes, does not execute tools, does not enable/disable plugins or MCP.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

from src.ham.hermes_skills_catalog import list_catalog_entries
from src.ham.hermes_skills_install import _config_path_for_hermes_home
from src.ham.hermes_skills_probe import _resolve_hermes_home_path, probe_capabilities

_KIND = "ham_hermes_runtime_inventory"
_RAW_CAP = 12_000
_CMD_TIMEOUT_S = 25.0

# argv after the hermes binary name (allowlist only). No ``hermes dump`` — not a valid subcommand
# in current Hermes CLI builds.
_ALLOWED_CLI_INVOCATIONS: tuple[tuple[str, ...], ...] = (
    ("tools", "--summary"),
    ("plugins", "list"),
    ("mcp", "list"),
    ("status", "--all"),
)

_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"(?i)(Authorization:\s*Bearer\s+)\S+"),
        r"\1[REDACTED]",
    ),
    (re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*\S+"), r"\1: [REDACTED]"),
    # OpenRouter / similar: ``sk-or-v1-...`` (hyphens; not covered by ``sk-[a-zA-Z0-9]+`` alone).
    (re.compile(r"(?i)\bsk-or-v1-[a-z0-9_-]{20,}\b"), "[REDACTED]"),
    (re.compile(r"(?i)(sk-[a-zA-Z0-9]{10,})"), "[REDACTED]"),
    (re.compile(r"(?i)(Bearer\s+)\S+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(x-api-key:\s*)\S+", re.MULTILINE), r"\1[REDACTED]"),
    # Provider lines like ``FAL           ✓ uuid:secret-token``
    (
        re.compile(
            r"(?i)(\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:[0-9a-f]{16,}\b)"
        ),
        "[REDACTED]",
    ),
)


def resolve_hermes_cli_binary() -> str | None:
    override = (os.environ.get("HAM_HERMES_CLI_PATH") or "").strip()
    if override:
        p = Path(override).expanduser()
        return str(p) if p.is_file() and os.access(p, os.X_OK) else None
    return shutil.which("hermes")


def redact_secrets(text: str) -> str:
    out = text
    for pat, repl in _SECRET_PATTERNS:
        out = pat.sub(repl, out)
    return out


def redact_paths(text: str, home_hint: str | None) -> str:
    out = text
    if home_hint:
        expanded = str(Path(home_hint).expanduser().resolve())
        if expanded and expanded in out:
            out = out.replace(expanded, "~/.hermes")
        home_hint_norm = home_hint.rstrip("/")
        if home_hint_norm and home_hint_norm in out:
            out = out.replace(home_hint_norm, "~/.hermes")
    return out


def cap_raw(text: str) -> str:
    if len(text) <= _RAW_CAP:
        return text
    return text[: _RAW_CAP - 20] + "\n… [truncated]"


def _tools_requires_interactive_terminal(combined_output: str) -> bool:
    low = combined_output.lower()
    return (
        "interactive terminal" in low
        or "non-interactive" in low
        or ("tty" in low and "pipe" in low)
        or "requires an interactive" in low
    )


def _run_hermes_cli(
    hermes_bin: str,
    suffix: tuple[str, ...],
    *,
    env: dict[str, str],
) -> tuple[int, str, str]:
    cmd = [hermes_bin, *suffix]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_CMD_TIMEOUT_S,
            env=env,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except OSError as exc:
        return 1, "", str(exc)
    out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    return proc.returncode, out.strip(), (proc.stderr or "").strip()


def sanitize_mcp_server_entry(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    transport = "unknown"
    if spec.get("url") or spec.get("endpoint"):
        transport = "http"
    elif spec.get("command") or spec.get("cmd"):
        transport = "stdio"
    tools_include: list[str] = []
    tools_exclude: list[str] = []
    raw_inc = spec.get("tools_include") or spec.get("include_tools")
    raw_exc = spec.get("tools_exclude") or spec.get("exclude_tools")
    if isinstance(raw_inc, list):
        tools_include = [str(x) for x in raw_inc if x is not None]
    if isinstance(raw_exc, list):
        tools_exclude = [str(x) for x in raw_exc if x is not None]
    has_env = bool(spec.get("env") and isinstance(spec.get("env"), dict))
    has_headers = bool(spec.get("headers") and isinstance(spec.get("headers"), dict))
    return {
        "name": name,
        "enabled": bool(spec.get("enabled", True)),
        "transport": transport,
        "tools_include": tools_include,
        "tools_exclude": tools_exclude,
        "resources": bool(spec.get("resources", False)),
        "prompts": bool(spec.get("prompts", False)),
        "has_env": has_env,
        "has_headers": has_headers,
    }


def parse_sanitized_config_dict(doc: dict[str, Any]) -> dict[str, Any]:
    """Extract only operator-safe fields; never return raw env/header values."""
    out: dict[str, Any] = {
        "status": "ok",
        "toolsets": [],
        "plugins_enabled": [],
        "plugins_disabled": [],
        "mcp_servers": [],
        "memory_provider": "",
        "context_engine": "",
        "external_skill_dirs_count": 0,
    }
    skills = doc.get("skills")
    if isinstance(skills, dict):
        ed = skills.get("external_dirs")
        if isinstance(ed, list):
            out["external_skill_dirs_count"] = len(ed)
        for key in ("toolsets", "enabled_toolsets", "default_toolsets"):
            raw = skills.get(key)
            if isinstance(raw, list):
                out["toolsets"] = [str(x) for x in raw if x is not None and str(x).strip()]
                break
    plugins = doc.get("plugins")
    if isinstance(plugins, dict):
        en = plugins.get("enabled")
        if isinstance(en, list):
            out["plugins_enabled"] = [str(x) for x in en if x is not None]
        dis = plugins.get("disabled")
        if isinstance(dis, list):
            out["plugins_disabled"] = [str(x) for x in dis if x is not None]
    mcp = doc.get("mcp")
    if isinstance(mcp, dict):
        servers = mcp.get("servers")
        if isinstance(servers, dict):
            for sname, spec in servers.items():
                if isinstance(spec, dict):
                    out["mcp_servers"].append(sanitize_mcp_server_entry(str(sname), spec))
    memory = doc.get("memory")
    if isinstance(memory, dict):
        prov = memory.get("provider") or memory.get("backend")
        if prov:
            out["memory_provider"] = str(prov)
    if not out["memory_provider"]:
        mp = doc.get("memory_provider")
        if isinstance(mp, str) and mp.strip():
            out["memory_provider"] = mp.strip()
    ctx = doc.get("context_engine") or doc.get("context")
    if isinstance(ctx, dict):
        ce = ctx.get("provider") or ctx.get("engine") or ctx.get("backend")
        if ce:
            out["context_engine"] = str(ce)
    elif isinstance(ctx, str) and ctx.strip():
        out["context_engine"] = ctx.strip()
    return out


def load_sanitized_config(hermes_home: Path) -> dict[str, Any]:
    cfg_path = _config_path_for_hermes_home(hermes_home)
    if not cfg_path.is_file():
        return {
            "status": "missing",
            "toolsets": [],
            "plugins_enabled": [],
            "plugins_disabled": [],
            "mcp_servers": [],
            "memory_provider": "",
            "context_engine": "",
            "external_skill_dirs_count": 0,
        }
    try:
        raw_text = cfg_path.read_text(encoding="utf-8", errors="replace")
        doc = yaml.safe_load(raw_text)
    except (OSError, yaml.YAMLError) as exc:
        return {
            "status": "error",
            "error_detail": str(exc)[:500],
            "toolsets": [],
            "plugins_enabled": [],
            "plugins_disabled": [],
            "mcp_servers": [],
            "memory_provider": "",
            "context_engine": "",
            "external_skill_dirs_count": 0,
        }
    if not isinstance(doc, dict):
        return {
            "status": "error",
            "error_detail": "config root is not a mapping",
            "toolsets": [],
            "plugins_enabled": [],
            "plugins_disabled": [],
            "mcp_servers": [],
            "memory_provider": "",
            "context_engine": "",
            "external_skill_dirs_count": 0,
        }
    merged = parse_sanitized_config_dict(doc)
    merged["status"] = "ok"
    return merged


def _cli_section(
    hermes_bin: str,
    suffix: tuple[str, ...],
    env: dict[str, str],
    home_hint: str | None,
) -> dict[str, Any]:
    if suffix not in _ALLOWED_CLI_INVOCATIONS:
        return {
            "status": "error",
            "summary_text": "",
            "toolsets": [],
            "items": [],
            "servers": [],
            "raw_redacted": "[internal] disallowed Hermes CLI invocation",
        }
    code, combined, err_tail = _run_hermes_cli(hermes_bin, suffix, env=env)
    redacted = redact_paths(redact_secrets(combined), home_hint)
    if code != 0:
        err_r = redact_paths(redact_secrets(err_tail), home_hint) if err_tail else ""
        return {
            "status": "error",
            "summary_text": "",
            "toolsets": [],
            "items": [],
            "servers": [],
            "raw_redacted": cap_raw(redacted + (f"\nstderr: {err_r}" if err_r else "")),
            "exit_code": code,
        }
    return {
        "status": "ok",
        "summary_text": redacted.splitlines()[0][:2000] if redacted else "",
        "toolsets": [],
        "items": [],
        "servers": [],
        "raw_redacted": cap_raw(redacted),
        "exit_code": 0,
    }


def _plugins_items_from_text(text: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        items.append({"text": s[:2000]})
        if len(items) >= 200:
            break
    return items


def build_runtime_inventory() -> dict[str, Any]:
    caps = probe_capabilities()
    mode = str(caps.get("mode") or "unsupported")
    hermes_home_path = _resolve_hermes_home_path()
    home_hint = str(hermes_home_path) if caps.get("hermes_home_detected") else None
    warnings: list[str] = list(caps.get("warnings") or [])

    catalog_entries = list_catalog_entries()
    skills_block: dict[str, Any] = {
        "status": "ok",
        "catalog_count": len(catalog_entries),
        "static_catalog": True,
        "installed_note": "",
    }

    binary = resolve_hermes_cli_binary()
    source_meta = {
        "hermes_binary": binary or "",
        "hermes_home": redact_paths(home_hint or "", home_hint) if home_hint else "",
        "colocated": bool(caps.get("hermes_home_detected")) and mode == "local",
    }

    empty_tools = {
        "status": "unavailable",
        "summary_text": "",
        "toolsets": [],
        "config_toolsets": [],
        "raw_redacted": "",
        "warning": "",
    }
    empty_plugins: dict[str, Any] = {
        "status": "unavailable",
        "items": [],
        "raw_redacted": "",
    }
    empty_mcp: dict[str, Any] = {
        "status": "unavailable",
        "servers": [],
        "raw_redacted": "",
    }
    status_block: dict[str, Any] = {
        "status_all": {"status": "unavailable", "raw_redacted": ""},
    }

    if mode == "remote_only":
        warnings.append(
            "Local Hermes CLI inventory is disabled for this deployment (HAM_HERMES_SKILLS_MODE=remote_only). "
            "Skills below are the static HAM catalog count only.",
        )
        cfg = {
            "status": "missing",
            "toolsets": [],
            "plugins_enabled": [],
            "plugins_disabled": [],
            "mcp_servers": [],
            "memory_provider": "",
            "context_engine": "",
            "external_skill_dirs_count": 0,
        }
        if caps.get("hermes_home_detected") and hermes_home_path.is_dir():
            cfg = load_sanitized_config(hermes_home_path)
            if cfg.get("status") == "ok":
                cfg["note"] = "Config-backed fields parsed on API host; may not reflect your operator machine when remote_only."
        return {
            "kind": _KIND,
            "mode": "local_inventory",
            "available": False,
            "source": source_meta,
            "tools": empty_tools,
            "plugins": empty_plugins,
            "mcp": empty_mcp,
            "config": cfg,
            "skills": skills_block,
            "status": status_block,
            "warnings": warnings,
        }

    if not binary:
        warnings.append("Hermes CLI not found on PATH (install Hermes or set HAM_HERMES_CLI_PATH).")
        cfg = load_sanitized_config(hermes_home_path) if hermes_home_path.is_dir() else {
            "status": "missing",
            "toolsets": [],
            "plugins_enabled": [],
            "plugins_disabled": [],
            "mcp_servers": [],
            "memory_provider": "",
            "context_engine": "",
            "external_skill_dirs_count": 0,
        }
        return {
            "kind": _KIND,
            "mode": "local_inventory",
            "available": False,
            "source": source_meta,
            "tools": {**empty_tools, "status": "unavailable"},
            "plugins": empty_plugins,
            "mcp": empty_mcp,
            "config": cfg,
            "skills": skills_block,
            "status": status_block,
            "warnings": warnings,
        }

    env = os.environ.copy()
    if home_hint:
        env["HERMES_HOME"] = str(Path(home_hint).expanduser().resolve())
        env.setdefault("HAM_HERMES_HOME", env["HERMES_HOME"])

    cfg = load_sanitized_config(hermes_home_path) if hermes_home_path.is_dir() else {
        "status": "missing",
        "toolsets": [],
        "plugins_enabled": [],
        "plugins_disabled": [],
        "mcp_servers": [],
        "memory_provider": "",
        "context_engine": "",
        "external_skill_dirs_count": 0,
    }

    tools_out = _cli_section(binary, ("tools", "--summary"), env, home_hint)
    tools_out.setdefault("config_toolsets", [])
    tools_out.setdefault("warning", "")
    if "exit_code" in tools_out:
        ec = tools_out.pop("exit_code")
        raw_for_tty = tools_out.get("raw_redacted", "")
        if ec == 0:
            tools_out["status"] = "ok"
        elif _tools_requires_interactive_terminal(raw_for_tty):
            tools_out["status"] = "requires_tty"
            tools_out["warning"] = (
                "Hermes tools summary requires an interactive terminal in this CLI version."
            )
            warnings.append(tools_out["warning"])
        else:
            tools_out["status"] = "error"
    for line in tools_out.get("raw_redacted", "").splitlines():
        stripped = line.strip()
        if stripped.startswith(("-", "*")) or re.match(r"^\d+[\).\s]", stripped):
            tools_out.setdefault("toolsets", []).append(stripped[:500])
    if not tools_out["toolsets"] and tools_out.get("summary_text"):
        tools_out["toolsets"] = [tools_out["summary_text"][:500]]

    if cfg.get("toolsets") and tools_out["status"] in ("requires_tty", "error"):
        tools_out["config_toolsets"] = list(cfg["toolsets"])
        if not tools_out["toolsets"]:
            tools_out["toolsets"] = [f"config:{t}" for t in cfg["toolsets"][:48]]

    plugins_out = _cli_section(binary, ("plugins", "list"), env, home_hint)
    if "exit_code" in plugins_out:
        plugins_out["status"] = "ok" if plugins_out["exit_code"] == 0 else "error"
        del plugins_out["exit_code"]
    plugins_out["items"] = _plugins_items_from_text(plugins_out.get("raw_redacted", ""))
    for k in ("summary_text", "toolsets", "servers"):
        plugins_out.pop(k, None)

    mcp_out = _cli_section(binary, ("mcp", "list"), env, home_hint)
    if "exit_code" in mcp_out:
        mcp_out["status"] = "ok" if mcp_out["exit_code"] == 0 else "error"
        del mcp_out["exit_code"]
    mcp_out["servers"] = _plugins_items_from_text(mcp_out.get("raw_redacted", ""))
    for k in ("summary_text", "toolsets", "items"):
        mcp_out.pop(k, None)

    st_out = _cli_section(binary, ("status", "--all"), env, home_hint)
    if "exit_code" in st_out:
        st_out["status"] = "ok" if st_out["exit_code"] == 0 else "error"
        st_out.pop("exit_code", None)
    for k in ("summary_text", "toolsets", "items", "servers"):
        st_out.pop(k, None)
    status_block = {
        "status_all": {"status": st_out["status"], "raw_redacted": st_out.get("raw_redacted", "")},
    }

    if cfg.get("external_skill_dirs_count"):
        skills_block["installed_note"] = (
            f"Hermes config lists {cfg['external_skill_dirs_count']} external skill dir entries (paths not shown)."
        )

    if cfg.get("status") == "ok" and cfg.get("mcp_servers"):
        if mcp_out["status"] != "ok" or not mcp_out.get("servers"):
            mcp_out["servers"] = [{"text": f"config:{s['name']} ({s['transport']})"} for s in cfg["mcp_servers"][:50]]

    partial_note = (
        tools_out["status"] == "error"
        or plugins_out["status"] == "error"
        or mcp_out["status"] == "error"
        or status_block["status_all"]["status"] == "error"
    )
    if partial_note:
        warnings.append("One or more Hermes CLI subcommands failed; see per-section status and raw_redacted.")

    for k in ("items", "servers"):
        tools_out.pop(k, None)

    return {
        "kind": _KIND,
        "mode": "local_inventory",
        "available": True,
        "source": {
            **source_meta,
            "hermes_binary": binary,
        },
        "tools": tools_out,
        "plugins": plugins_out,
        "mcp": mcp_out,
        "config": cfg,
        "skills": skills_block,
        "status": status_block,
        "warnings": warnings,
    }
