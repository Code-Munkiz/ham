"""TypeScript validation for generated Vite preview bundles before marking builds ready."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_DEFAULT_TSCONFIG = (
    "{\n"
    '  "compilerOptions": {\n'
    '    "target": "ES2020",\n'
    '    "useDefineForClassFields": true,\n'
    '    "lib": ["ES2020", "DOM", "DOM.Iterable"],\n'
    '    "module": "ESNext",\n'
    '    "skipLibCheck": true,\n'
    '    "moduleResolution": "bundler",\n'
    '    "allowImportingTsExtensions": true,\n'
    '    "isolatedModules": true,\n'
    '    "moduleDetection": "force",\n'
    '    "noEmit": true,\n'
    '    "jsx": "react-jsx",\n'
    '    "strict": false,\n'
    '    "noUnusedLocals": false,\n'
    '    "noUnusedParameters": false\n'
    "  },\n"
    '  "include": ["src"]\n'
    "}\n"
)

_TAILWIND_CONTENT = '["./index.html", "./src/**/*.{js,ts,jsx,tsx}"]'

_TS_NAME_ERROR_RE = re.compile(
    r"error TS(?:2304|2552):\s*Cannot find name '([^']+)'",
    re.IGNORECASE,
)
_TS_DID_YOU_MEAN_RE = re.compile(
    r"Cannot find name '([^']+)'\.\s*Did you mean '([^']+)'\?",
    re.IGNORECASE,
)
_TS_FILE_LINE_RE = re.compile(r"^([\w./-]+\.(?:tsx?|jsx?))\((\d+),\d+\):")

_USER_SAFE_TYPECHECK_MESSAGE = (
    "The generated app did not pass TypeScript checks. "
    "HAM could not prepare a runnable preview from this build."
)

_REPAIR_TYPECHECK_SUMMARY = (
    "TypeScript reported errors in the generated source (for example undefined "
    "identifiers or type mismatches). Fix every reported symbol so names match "
    "their declarations, then return the full corrected file bundle."
)


def preview_typecheck_enabled(env: dict[str, str] | None = None) -> bool:
    mapping = env if env is not None else os.environ
    raw = (mapping.get("HAM_PREVIEW_TYPECHECK") or "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _package_json_obj(files: dict[str, str]) -> dict[str, Any] | None:
    raw = files.get("package.json")
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _project_uses_tailwind(files: dict[str, str]) -> bool:
    pkg = _package_json_obj(files)
    if pkg:
        for section in ("dependencies", "devDependencies"):
            deps = pkg.get(section)
            if isinstance(deps, dict) and "tailwindcss" in deps:
                return True
    postcss = files.get("postcss.config.js") or files.get("postcss.config.cjs") or ""
    if "tailwindcss" in postcss:
        return True
    for path, body in files.items():
        if path.endswith((".css",)) and "@tailwind" in body:
            return True
    return False


def build_default_tailwind_config_js() -> str:
    return (
        "/** @type {import('tailwindcss').Config} */\n"
        "export default {\n"
        f"  content: {_TAILWIND_CONTENT},\n"
        "  theme: {\n"
        "    extend: {},\n"
        "  },\n"
        "  plugins: [],\n"
        "};\n"
    )


def ensure_preview_tsconfig(files: dict[str, str]) -> dict[str, str]:
    """Add a minimal tsconfig when the bundle has TypeScript sources but no config."""
    out = dict(files)
    has_ts = any(
        p.endswith((".ts", ".tsx")) and p.startswith("src/") for p in out
    )
    if not has_ts:
        return out
    if not any(p.startswith("tsconfig") and p.endswith(".json") for p in out):
        out["tsconfig.json"] = _DEFAULT_TSCONFIG
    return out


def ensure_tailwind_config_for_preview(files: dict[str, str]) -> dict[str, str]:
    """Ensure tailwind.config.js exists when Tailwind is in use; preserve existing postcss."""
    if not _project_uses_tailwind(files):
        return files
    out = dict(files)
    if "tailwind.config.js" not in out and "tailwind.config.cjs" not in out:
        out["tailwind.config.js"] = build_default_tailwind_config_js()
    return out


def sanitize_typecheck_output(raw: str) -> str:
    """Strip absolute paths and noisy internals from compiler output for safe summaries."""
    text = str(raw or "")
    if not text.strip():
        return ""
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("at ") or "node_modules" in stripped:
            continue
        # Drop absolute filesystem prefixes while keeping relative src paths.
        cleaned = re.sub(r"(?:[A-Za-z]:)?[/\\][\w./\\-]+[/\\](?=src/)", "", line)
        cleaned = re.sub(r"(?:[A-Za-z]:)?[/\\][\w./\\-]{20,}[/\\]", "", cleaned)
        lines.append(cleaned.strip())
    return "\n".join(lines[:24])


def summarize_typecheck_for_repair(compiler_output: str) -> str:
    """Build a safe, focused repair note from sanitized compiler output."""
    sanitized = sanitize_typecheck_output(compiler_output)
    if not sanitized:
        return _REPAIR_TYPECHECK_SUMMARY
    return f"{_REPAIR_TYPECHECK_SUMMARY}\n\nCompiler summary:\n{sanitized}"


def user_safe_typecheck_failure_message() -> str:
    return _USER_SAFE_TYPECHECK_MESSAGE


def _declared_identifiers_in_source(content: str) -> set[str]:
    names: set[str] = set()
    for match in re.finditer(
        r"(?:\bconst|\blet|\bvar|\bfunction|\bclass|\benum)\s+([A-Za-z_$][\w$]*)",
        content,
    ):
        names.add(match.group(1))
    for match in re.finditer(r"\bexport\s+default\s+function\s+([A-Za-z_$][\w$]*)", content):
        names.add(match.group(1))
    return names


def try_repair_identifier_case_mismatch(
    files: dict[str, str], compiler_output: str
) -> dict[str, str] | None:
    """Fix simple TS2304/TS2552 name errors when the correct symbol differs only by casing."""
    replacements: list[tuple[str, str]] = []
    for match in _TS_DID_YOU_MEAN_RE.finditer(compiler_output):
        wrong, right = match.group(1), match.group(2)
        if wrong and right and wrong != right:
            replacements.append((wrong, right))

    missing: list[str] = []
    for match in _TS_NAME_ERROR_RE.finditer(compiler_output):
        name = match.group(1)
        if name and name not in missing:
            missing.append(name)

    out = dict(files)
    changed = False
    source_paths = sorted(
        p for p in out if p.endswith((".ts", ".tsx", ".js", ".jsx")) and p.startswith("src/")
    )
    all_declared: set[str] = set()
    for path in source_paths:
        all_declared |= _declared_identifiers_in_source(out[path])

    for wrong_name in missing:
        canonical = None
        for wrong, right in replacements:
            if wrong == wrong_name:
                canonical = right
                break
        if not canonical:
            for declared in all_declared:
                if declared.lower() == wrong_name.lower() and declared != wrong_name:
                    canonical = declared
                    break
        if not canonical:
            continue
        pattern = re.compile(rf"\b{re.escape(wrong_name)}\b")
        for path in source_paths:
            body = out[path]
            if not pattern.search(body):
                continue
            out[path] = pattern.sub(canonical, body)
            changed = True
    return out if changed else None


def _write_project_tree(project_dir: Path, files: dict[str, str]) -> None:
    for rel_path, content in files.items():
        dest = project_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")


def preview_typecheck_install_enabled(env: dict[str, str] | None = None) -> bool:
    mapping = env if env is not None else os.environ
    raw = (mapping.get("HAM_PREVIEW_TYPECHECK_INSTALL") or "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _npm_install(project_dir: Path) -> tuple[bool, str]:
    npm = shutil.which("npm")
    if not npm:
        return False, "npm is not available for preview dependency install"
    proc = subprocess.run(
        [npm, "install", "--no-audit", "--no-fund", "--legacy-peer-deps"],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    combined = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode == 0, combined.strip()


def run_preview_typecheck(
    files: dict[str, str],
    *,
    project_dir: Path | None = None,
) -> tuple[bool, str]:
    """Run ``npm install`` (when enabled) then ``tsc --noEmit``. Returns ``(ok, output)``."""
    if not preview_typecheck_enabled():
        return True, ""

    prepared = ensure_tailwind_config_for_preview(ensure_preview_tsconfig(dict(files)))
    owns_dir = project_dir is None
    tmp_ctx: tempfile.TemporaryDirectory[str] | None = None
    if owns_dir:
        tmp_ctx = tempfile.TemporaryDirectory(prefix="ham-preview-tsc-")
        project_dir = Path(tmp_ctx.name)
    assert project_dir is not None
    try:
        _write_project_tree(project_dir, prepared)
        tsconfig = project_dir / "tsconfig.json"
        if not tsconfig.is_file():
            return False, "error TS5023: missing tsconfig.json"

        if preview_typecheck_install_enabled() and (project_dir / "package.json").is_file():
            installed, install_log = _npm_install(project_dir)
            if not installed:
                return False, sanitize_typecheck_output(install_log) or "npm install failed"

        tsc_bin = project_dir / "node_modules" / ".bin" / "tsc"
        if tsc_bin.is_file():
            cmd = [str(tsc_bin), "--noEmit", "-p", str(tsconfig.name)]
        else:
            npx = shutil.which("npx")
            if not npx:
                return False, "error TS5033: npx not available for preview typecheck"
            cmd = [
                npx,
                "--yes",
                "-p",
                "typescript@5.6.3",
                "tsc",
                "--noEmit",
                "-p",
                str(tsconfig.name),
            ]
        proc = subprocess.run(
            cmd,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        combined = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        return proc.returncode == 0, combined.strip()
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()


@dataclass(frozen=True)
class PreviewTypecheckResult:
    ok: bool
    files: dict[str, str]
    repair_summary: str | None
    user_message: str
    compiler_output: str
    deterministic_repair_attempted: bool


def validate_preview_app_files(files: dict[str, str]) -> PreviewTypecheckResult:
    """Bootstrap ts/tailwind helpers, optional deterministic repair, then typecheck."""
    prepared = ensure_tailwind_config_for_preview(ensure_preview_tsconfig(dict(files)))
    ok, output = run_preview_typecheck(prepared)
    if ok:
        return PreviewTypecheckResult(
            ok=True,
            files=prepared,
            repair_summary=None,
            user_message="",
            compiler_output=output,
            deterministic_repair_attempted=False,
        )

    repaired = try_repair_identifier_case_mismatch(prepared, output)
    if repaired is not None:
        ok2, output2 = run_preview_typecheck(repaired)
        if ok2:
            return PreviewTypecheckResult(
                ok=True,
                files=repaired,
                repair_summary=None,
                user_message="",
                compiler_output=output2,
                deterministic_repair_attempted=True,
            )
        output = output2 or output
        prepared = repaired

    return PreviewTypecheckResult(
        ok=False,
        files=prepared,
        repair_summary=summarize_typecheck_for_repair(output),
        user_message=user_safe_typecheck_failure_message(),
        compiler_output=output,
        deterministic_repair_attempted=repaired is not None,
    )
