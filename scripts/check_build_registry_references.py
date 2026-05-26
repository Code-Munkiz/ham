#!/usr/bin/env python3
"""Local reference checker for Build Kit Registry v2 Game Pack YAML.

Warning/report oriented — not wired into runtime, CI, or API paths.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ham.build_registry import (
    DEFAULT_RENDER_CHAR_BUDGET,
    BuildRegistryConfigError,
    compose_build_recipe,
    load_registry_pack,
    render_playbook_context,
    validate_registry_pack,
)
from src.ham.build_registry.models import MODULE_INDEX_KEYS, PACK_MANIFEST_NAME

Severity = Literal["info", "warning", "error"]

NEAR_BUDGET_RATIO = 0.9
RENDER_PROBE_BUDGET = 999_999

INDEX_DIRECTORY: dict[str, tuple[str, bool]] = {
    "app_types": ("app-types", True),
    "stack_kits": ("stack-kits", False),
    "mechanics": ("mechanics", False),
    "component_contracts": ("component-contracts", False),
    "validators": ("validators", False),
    "recovery_playbooks": ("recovery-playbooks", False),
    "progress_labels": ("progress-labels", False),
    "learning_hooks": ("learning-hooks", False),
}

NON_TEMPLATE_KINDS = frozenset(
    {
        "registry_pack",
        "app_type",
        "mechanic",
        "component_contract",
        "stack_kit",
        "validator",
        "recovery_playbook",
        "progress_label",
        "learning_hook",
    }
)

APP_TYPE_REF = re.compile(r"^(?:game|app)\.[a-z0-9-]+$")


@dataclass(frozen=True)
class CheckIssue:
    code: str
    severity: Severity
    message: str
    path: str | None = None
    suggestion: str | None = None


@dataclass
class CheckResult:
    issues: list[CheckIssue] = field(default_factory=list)
    pack_path: str | None = None
    pack_root: str | None = None

    @property
    def errors(self) -> list[CheckIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[CheckIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    @property
    def infos(self) -> list[CheckIssue]:
        return [issue for issue in self.issues if issue.severity == "info"]

    @property
    def summary_counts(self) -> dict[str, int]:
        counts = {"error": 0, "warning": 0, "info": 0}
        for issue in self.issues:
            counts[issue.severity] += 1
        return counts


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top-level YAML must be a mapping")
    return data


def _issue(
    code: str,
    severity: Severity,
    message: str,
    *,
    path: Path | str | None = None,
    suggestion: str | None = None,
) -> CheckIssue:
    path_str = str(path) if path is not None else None
    return CheckIssue(
        code=code,
        severity=severity,
        message=message,
        path=path_str,
        suggestion=suggestion,
    )


def _add_issue(result: CheckResult, issue: CheckIssue) -> None:
    result.issues.append(issue)


def _expected_module_path(pack_root: Path, index_key: str, module_id: str) -> Path:
    directory, use_full_id = INDEX_DIRECTORY[index_key]
    if use_full_id:
        filename = f"{module_id}.yaml"
    else:
        slug = module_id.split(".", 1)[1] if "." in module_id else module_id
        filename = f"{slug}.yaml"
    return pack_root / directory / filename


def _flatten_module_index(module_index: dict[str, Any]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for key in MODULE_INDEX_KEYS:
        entries = module_index.get(key)
        if not isinstance(entries, list):
            grouped[key] = []
            continue
        grouped[key] = [
            item.strip()
            for item in entries
            if isinstance(item, str) and item.strip()
        ]
    return grouped


def _collect_yaml_module_paths(pack_root: Path) -> list[Path]:
    return sorted(
        path
        for path in pack_root.rglob("*.yaml")
        if path.name != PACK_MANIFEST_NAME
    )


def _parse_loader_errors(message: str, pack_root: Path) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    for line in message.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("Registry pack validation failed"):
            continue
        if stripped.startswith("- "):
            stripped = stripped[2:]
        if "Orphan YAML modules not in module_index" in stripped:
            issues.append(
                _issue(
                    "orphan_module",
                    "warning",
                    stripped,
                    path=pack_root,
                    suggestion="Add module id to registry-pack.yaml or remove orphan file",
                )
            )
            continue
        if "Indexed module ids missing YAML files" in stripped:
            issues.append(
                _issue(
                    "missing_referenced_file",
                    "error",
                    stripped,
                    path=pack_root,
                    suggestion="Create the missing YAML module or remove stale index entry",
                )
            )
            continue
        if "Duplicate module id" in stripped or "duplicate ids in module_index" in stripped:
            issues.append(
                _issue(
                    "duplicate_module_id",
                    "error",
                    stripped,
                    path=pack_root,
                )
            )
            continue
        issues.append(
            _issue(
                "registry_validation_error",
                "error",
                stripped,
                path=pack_root,
            )
        )
    if not issues and message.strip():
        issues.append(
            _issue(
                "registry_load_error",
                "error",
                message.strip(),
                path=pack_root,
            )
        )
    return issues


def _check_index_references(
    result: CheckResult,
    pack_root: Path,
    grouped_index: dict[str, list[str]],
) -> set[str]:
    indexed_ids: set[str] = set()
    for index_key, module_ids in grouped_index.items():
        if index_key not in INDEX_DIRECTORY:
            continue
        seen: set[str] = set()
        for module_id in module_ids:
            if module_id in seen:
                _add_issue(
                    result,
                    _issue(
                        "duplicate_module_id",
                        "error",
                        f"Duplicate id {module_id!r} in module_index.{index_key}",
                        path=pack_root / PACK_MANIFEST_NAME,
                    ),
                )
            seen.add(module_id)
            indexed_ids.add(module_id)
            expected = _expected_module_path(pack_root, index_key, module_id)
            if not expected.is_file():
                _add_issue(
                    result,
                    _issue(
                        "missing_referenced_file",
                        "error",
                        f"Indexed module {module_id!r} missing expected file {expected}",
                        path=expected,
                        suggestion="Create YAML file or fix registry-pack.yaml index entry",
                    ),
                )
    return indexed_ids


def _scan_module_files(
    result: CheckResult,
    pack_root: Path,
) -> dict[str, Path]:
    ids_to_paths: dict[str, Path] = {}
    for path in _collect_yaml_module_paths(pack_root):
        try:
            payload = _load_yaml(path)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            _add_issue(
                result,
                _issue(
                    "invalid_yaml",
                    "error",
                    f"Failed to load {path}: {exc}",
                    path=path,
                ),
            )
            continue
        module_id = payload.get("id")
        if not isinstance(module_id, str) or not module_id.strip():
            _add_issue(
                result,
                _issue(
                    "missing_module_id",
                    "error",
                    f"{path}: missing or empty id",
                    path=path,
                ),
            )
            continue
        module_id = module_id.strip()
        if module_id in ids_to_paths:
            _add_issue(
                result,
                _issue(
                    "duplicate_module_id",
                    "error",
                    f"Duplicate module id {module_id!r} ({ids_to_paths[module_id]} and {path})",
                    path=path,
                ),
            )
            continue
        ids_to_paths[module_id] = path
    return ids_to_paths


def _check_orphans(
    result: CheckResult,
    pack_root: Path,
    indexed_ids: set[str],
    ids_to_paths: dict[str, Path],
) -> None:
    orphan_ids = sorted(set(ids_to_paths) - indexed_ids)
    for module_id in orphan_ids:
        path = ids_to_paths[module_id]
        _add_issue(
            result,
            _issue(
                "orphan_module",
                "warning",
                f"YAML module {module_id!r} is not listed in registry-pack.yaml module_index",
                path=path,
                suggestion="Add to module_index or remove orphan file",
            ),
        )


def _check_filename_id_mismatch(
    result: CheckResult,
    grouped_index: dict[str, list[str]],
    ids_to_paths: dict[str, Path],
) -> None:
    for index_key, module_ids in grouped_index.items():
        if index_key not in INDEX_DIRECTORY:
            continue
        pack_root = Path(result.pack_root or ".")
        for module_id in module_ids:
            expected = _expected_module_path(pack_root, index_key, module_id)
            actual = ids_to_paths.get(module_id)
            if actual is None:
                continue
            if actual.resolve() != expected.resolve():
                _add_issue(
                    result,
                    _issue(
                        "id_filename_mismatch",
                        "warning",
                        (
                            f"Module {module_id!r} loaded from {actual} "
                            f"but convention expects {expected}"
                        ),
                        path=actual,
                        suggestion="Rename file or update id to match Game Pack conventions",
                    ),
                )


def _check_applies_to(
    result: CheckResult,
    grouped_index: dict[str, list[str]],
    ids_to_paths: dict[str, Path],
) -> None:
    app_type_ids = set(grouped_index.get("app_types", []))
    for module_id, path in ids_to_paths.items():
        try:
            payload = _load_yaml(path)
        except (OSError, ValueError, yaml.YAMLError):
            continue
        applies_to = payload.get("applies_to")
        if not isinstance(applies_to, list):
            continue
        for entry in applies_to:
            if not isinstance(entry, str) or not entry.strip():
                continue
            entry = entry.strip()
            if entry.startswith("tag:"):
                continue
            if not APP_TYPE_REF.match(entry):
                continue
            if entry not in app_type_ids:
                _add_issue(
                    result,
                    _issue(
                        "invalid_applies_to",
                        "error",
                        f"{module_id}: applies_to references unknown app type {entry!r}",
                        path=path,
                        suggestion="Fix applies_to entry or add app type to module_index.app_types",
                    ),
                )


def _check_non_template_statements(
    result: CheckResult,
    ids_to_paths: dict[str, Path],
) -> None:
    for module_id, path in ids_to_paths.items():
        try:
            payload = _load_yaml(path)
        except (OSError, ValueError, yaml.YAMLError):
            continue
        kind = payload.get("kind")
        if kind not in NON_TEMPLATE_KINDS:
            continue
        statement = payload.get("non_template_statement")
        if not isinstance(statement, str) or not statement.strip():
            _add_issue(
                result,
                _issue(
                    "missing_non_template_statement",
                    "warning",
                    f"{module_id}: missing non_template_statement",
                    path=path,
                    suggestion="Add generative non-template posture per AUTHORING_GUIDE.md",
                ),
            )


def _check_render_budgets(
    result: CheckResult,
    pack,
    *,
    app_type: str | None,
) -> None:
    if app_type:
        app_type_ids = [app_type]
    else:
        app_type_ids = [
            module_id
            for module_id, module in pack.modules.items()
            if module.kind == "app_type"
        ]
    near_cap = int(DEFAULT_RENDER_CHAR_BUDGET * NEAR_BUDGET_RATIO)
    for app_type_id in app_type_ids:
        if app_type_id is None:
            continue
        try:
            recipe = compose_build_recipe(pack, app_type_id)
            rendered = render_playbook_context(recipe, max_chars=RENDER_PROBE_BUDGET)
        except BuildRegistryConfigError as exc:
            _add_issue(
                result,
                _issue(
                    "render_budget_check_failed",
                    "error",
                    f"{app_type_id}: compose/render failed: {exc}",
                    path=pack.modules[app_type_id].path
                    if app_type_id in pack.modules
                    else None,
                ),
            )
            continue
        length = len(rendered)
        module_path = pack.modules[app_type_id].path
        if length > DEFAULT_RENDER_CHAR_BUDGET:
            _add_issue(
                result,
                _issue(
                    "render_over_budget",
                    "error",
                    (
                        f"{app_type_id}: rendered playbook length {length} exceeds "
                        f"budget {DEFAULT_RENDER_CHAR_BUDGET}"
                    ),
                    path=module_path,
                    suggestion="Trim module guidance or raise budget deliberately",
                ),
            )
        elif length >= near_cap:
            _add_issue(
                result,
                _issue(
                    "render_near_budget",
                    "warning",
                    (
                        f"{app_type_id}: rendered playbook length {length} is "
                        f">= {NEAR_BUDGET_RATIO:.0%} of budget {DEFAULT_RENDER_CHAR_BUDGET}"
                    ),
                    path=module_path,
                    suggestion="Consider trimming guidance before next module additions",
                ),
            )


def run_reference_checks(
    pack_path: Path,
    *,
    app_type: str | None = None,
    check_orphans: bool = False,
    check_render_budget: bool = False,
    strict: bool = False,
    warn_only: bool = False,
) -> CheckResult:
    """Run reference checks against a registry pack manifest path."""
    del strict, warn_only  # exit behavior handled by caller
    pack_path = pack_path.resolve()
    pack_root = pack_path.parent
    result = CheckResult(pack_path=str(pack_path), pack_root=str(pack_root))

    if not pack_path.is_file():
        _add_issue(
            result,
            _issue(
                "missing_pack_manifest",
                "error",
                f"Registry pack manifest not found: {pack_path}",
                path=pack_path,
            ),
        )
        return result

    try:
        manifest = _load_yaml(pack_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        _add_issue(
            result,
            _issue(
                "invalid_pack_manifest",
                "error",
                f"Failed to load {pack_path}: {exc}",
                path=pack_path,
            ),
        )
        return result

    module_index = manifest.get("module_index")
    if not isinstance(module_index, dict):
        _add_issue(
            result,
            _issue(
                "missing_module_index",
                "error",
                "registry-pack.yaml: missing module_index mapping",
                path=pack_path,
            ),
        )
        return result

    grouped_index = _flatten_module_index(module_index)
    indexed_ids = _check_index_references(result, pack_root, grouped_index)
    ids_to_paths = _scan_module_files(result, pack_root)

    missing_indexed = sorted(indexed_ids - set(ids_to_paths))
    for module_id in missing_indexed:
        _add_issue(
            result,
            _issue(
                "missing_referenced_file",
                "error",
                f"Indexed module {module_id!r} has no YAML file with matching id",
                path=pack_root / PACK_MANIFEST_NAME,
            ),
        )

    if check_orphans:
        _check_orphans(result, pack_root, indexed_ids, ids_to_paths)

    _check_filename_id_mismatch(result, grouped_index, ids_to_paths)
    _check_applies_to(result, grouped_index, ids_to_paths)
    _check_non_template_statements(result, ids_to_paths)

    if result.errors:
        return result

    try:
        pack = load_registry_pack(pack_root)
    except BuildRegistryConfigError as exc:
        parsed = _parse_loader_errors(str(exc), pack_root)
        if parsed:
            for issue in parsed:
                if issue.code == "orphan_module":
                    if check_orphans:
                        continue
                    _add_issue(
                        result,
                        _issue(
                            issue.code,
                            "error",
                            issue.message,
                            path=issue.path,
                            suggestion=issue.suggestion,
                        ),
                    )
                else:
                    _add_issue(result, issue)
        else:
            _add_issue(
                result,
                _issue(
                    "registry_load_error",
                    "error",
                    str(exc),
                    path=pack_root,
                ),
            )
        return result

    try:
        validate_registry_pack(pack)
    except BuildRegistryConfigError as exc:
        for issue in _parse_loader_errors(str(exc), pack_root):
            _add_issue(result, issue)
        return result
    except Exception as exc:  # noqa: BLE001 — checker surfaces unexpected validate failures
        _add_issue(
            result,
            _issue(
                "registry_validation_error",
                "error",
                f"Registry validation failed: {exc}",
                path=pack_root,
            ),
        )
        return result

    if check_render_budget:
        _check_render_budgets(result, pack, app_type=app_type)

    return result


def compute_exit_code(
    result: CheckResult,
    *,
    strict: bool = False,
    warn_only: bool = False,
) -> int:
    if warn_only:
        return 0
    if strict and (result.errors or result.warnings):
        return 1
    if result.errors:
        return 1
    return 0


def format_human_report(result: CheckResult) -> str:
    lines = [
        "Build Registry v2 reference checker",
        f"Pack: {result.pack_path}",
    ]
    counts = result.summary_counts
    lines.append(
        "Summary: "
        f"{counts['error']} error(s), "
        f"{counts['warning']} warning(s), "
        f"{counts['info']} info"
    )
    if not result.issues:
        lines.append("OK: no reference issues detected")
        return "\n".join(lines) + "\n"

    for severity in ("error", "warning", "info"):
        bucket = [issue for issue in result.issues if issue.severity == severity]
        if not bucket:
            continue
        lines.append("")
        lines.append(f"[{severity.upper()}]")
        for issue in bucket:
            location = f" ({issue.path})" if issue.path else ""
            lines.append(f"- {issue.code}{location}: {issue.message}")
            if issue.suggestion:
                lines.append(f"  suggestion: {issue.suggestion}")
    return "\n".join(lines) + "\n"


def format_json_report(result: CheckResult) -> str:
    payload = {
        "pack_path": result.pack_path,
        "pack_root": result.pack_root,
        "summary_counts": result.summary_counts,
        "issues": [asdict(issue) for issue in result.issues],
    }
    return json.dumps(payload, indent=2) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check Build Kit Registry v2 Game Pack references and drift."
    )
    parser.add_argument(
        "--pack",
        type=Path,
        default=REPO_ROOT / "docs/build-kit-registry-v2/game-pack/registry-pack.yaml",
        help="Path to registry-pack.yaml",
    )
    parser.add_argument(
        "--app-type",
        help="Limit render budget checks to one app type id",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors for exit code",
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Always exit 0 while still reporting issues",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report",
    )
    parser.add_argument(
        "--check-orphans",
        action="store_true",
        help="Warn on YAML module files not indexed in registry-pack.yaml",
    )
    parser.add_argument(
        "--check-render-budget",
        action="store_true",
        help="Compose/render app types and check playbook length budget",
    )
    args = parser.parse_args(argv)

    result = run_reference_checks(
        args.pack,
        app_type=args.app_type,
        check_orphans=args.check_orphans,
        check_render_budget=args.check_render_budget,
        strict=args.strict,
        warn_only=args.warn_only,
    )

    report = format_json_report(result) if args.json else format_human_report(result)
    sys.stdout.write(report)
    return compute_exit_code(result, strict=args.strict, warn_only=args.warn_only)


if __name__ == "__main__":
    raise SystemExit(main())
