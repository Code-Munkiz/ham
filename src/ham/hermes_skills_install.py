"""Hermes runtime skills — shared-target install (Phase 2a: bundle + skills.external_dirs).

Local/co-located API only; curated catalog; no Hermes CLI subprocess.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import sys
import re
import shutil
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import yaml

if sys.platform == "win32":
    import msvcrt

from src.ham.hermes_skills_catalog import catalog_upstream_meta, get_catalog_entry_detail
from src.ham.hermes_skills_probe import probe_capabilities


class HermesSkillInstallError(Exception):
    """Structured install failure; ``code`` maps to API error codes."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_BUNDLE_SUBDIR = "ham-runtime-bundles"
_BUNDLE_VERSION = "v1"
_BACKUP_SUBDIR = Path("_ham_backups") / "hermes-config"
_AUDIT_SUBDIR = Path("_ham_audit") / "hermes-skills"
_PIN_FILENAME = ".ham-hermes-agent-commit"
_LOCK_NAME = ".ham-skills-install.lock"


def skills_apply_writes_enabled() -> bool:
    return bool((os.environ.get("HAM_SKILLS_WRITE_TOKEN") or "").strip())


def _config_path_for_hermes_home(hermes_home: Path) -> Path:
    override = (os.environ.get("HAM_HERMES_CONFIG_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (hermes_home / "config.yaml").resolve()


def _bundle_root(hermes_home: Path) -> Path:
    return (hermes_home / _BUNDLE_SUBDIR / _BUNDLE_VERSION).resolve()


def _catalog_id_slug(catalog_id: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", catalog_id.strip())
    return s[:200] if len(s) > 200 else s


def skill_pack_rel_in_source_repo(catalog_id: str) -> tuple[str, Path] | None:
    """Return (topdir, relative path) for skills/ or optional-skills/ tree."""
    cid = catalog_id.strip()
    if cid.startswith("bundled."):
        tail = cid[len("bundled.") :]
        if not tail:
            return None
        parts = tail.split(".")
        return "skills", Path(*parts)
    if cid.startswith("official."):
        tail = cid[len("official.") :]
        if not tail:
            return None
        parts = tail.split(".")
        return "optional-skills", Path(*parts)
    return None


def source_tree_ready() -> tuple[bool, list[str]]:
    """Whether ``HAM_HERMES_SKILLS_SOURCE_ROOT`` matches the vendored catalog pin."""
    warnings: list[str] = []
    raw_root = (os.environ.get("HAM_HERMES_SKILLS_SOURCE_ROOT") or "").strip()
    if not raw_root:
        warnings.append(
            "HAM_HERMES_SKILLS_SOURCE_ROOT is not set. "
            "Point it at a NousResearch/hermes-agent checkout (or extracted archive) "
            "at the same commit as the vendored catalog (see catalog `upstream.commit`). "
            "Create file `.ham-hermes-agent-commit` in that root with the full 40-character SHA."
        )
        return False, warnings
    root = Path(raw_root).expanduser().resolve()
    if not root.is_dir():
        warnings.append(f"HAM_HERMES_SKILLS_SOURCE_ROOT is not a directory: {raw_root!r}.")
        return False, warnings
    pin_file = root / _PIN_FILENAME
    if not pin_file.is_file():
        warnings.append(
            f"Missing { _PIN_FILENAME!r} under source root {root}; "
            "it must contain the catalog upstream commit SHA (40 hex chars)."
        )
        return False, warnings
    pin_text = pin_file.read_text(encoding="utf-8").strip()
    up = catalog_upstream_meta()
    expected = (up or {}).get("commit") if isinstance(up, dict) else None
    if not isinstance(expected, str) or len(expected) != 40:
        warnings.append("Catalog upstream commit missing or invalid; cannot verify source pin.")
        return False, warnings
    if pin_text != expected:
        warnings.append(
            f"Source pin mismatch: {_PIN_FILENAME} has {pin_text[:12]}… "
            f"but catalog expects {expected[:12]}…"
        )
        return False, warnings
    return True, warnings


def capability_extension_fields() -> dict[str, Any]:
    """Extra fields merged into GET /api/hermes-skills/capabilities."""
    caps = probe_capabilities()
    src_ok, src_warn = source_tree_ready()
    supported = (
        caps.get("mode") == "local"
        and bool(caps.get("hermes_home_detected"))
        and bool(caps.get("shared_target_supported"))
        and src_ok
    )
    install_readiness_warnings: list[str] = []
    if caps.get("mode") == "local" and caps.get("hermes_home_detected") and not src_ok:
        install_readiness_warnings.extend(src_warn)
    return {
        "shared_runtime_install_supported": supported,
        "skills_apply_writes_enabled": skills_apply_writes_enabled(),
        "install_readiness_warnings": install_readiness_warnings,
    }


def _require_local_shared_install() -> Path:
    caps = probe_capabilities()
    if caps.get("mode") == "remote_only":
        raise HermesSkillInstallError(
            "REMOTE_UNSUPPORTED",
            "API is not co-located with Hermes home (HAM_HERMES_SKILLS_MODE=remote_only).",
        )
    if caps.get("mode") != "local" or not caps.get("hermes_home_detected"):
        raise HermesSkillInstallError(
            "REMOTE_UNSUPPORTED",
            "Hermes home is not available on this API host; shared install is not supported.",
        )
    if not caps.get("shared_target_supported"):
        raise HermesSkillInstallError(
            "REMOTE_UNSUPPORTED",
            "Shared Hermes target is not supported in the current capability state.",
        )
    src_ok, _msgs = source_tree_ready()
    if not src_ok:
        raise HermesSkillInstallError(
            "SKILL_NOT_INSTALLABLE",
            "Hermes skill source tree is not configured or does not match the catalog pin "
            "(set HAM_HERMES_SKILLS_SOURCE_ROOT and .ham-hermes-agent-commit).",
        )
    hint = caps.get("hermes_home_path_hint")
    if not hint:
        raise HermesSkillInstallError("REMOTE_UNSUPPORTED", "Hermes home path is unknown.")
    return Path(hint).resolve()


def _resolve_source_skill_dir(catalog_id: str) -> Path:
    rel = skill_pack_rel_in_source_repo(catalog_id)
    if rel is None:
        raise HermesSkillInstallError(
            "SKILL_NOT_IN_CATALOG",
            f"Catalog id {catalog_id!r} does not map to a bundled/official skill path.",
        )
    top, sub = rel
    raw_root = (os.environ.get("HAM_HERMES_SKILLS_SOURCE_ROOT") or "").strip()
    root = Path(raw_root).expanduser().resolve()
    skill_dir = (root / top / sub).resolve()
    try:
        skill_dir.relative_to(root)
    except ValueError as exc:
        raise HermesSkillInstallError("BUNDLE_WRITE_FAILED", "Invalid skill source path.") from exc
    if not skill_dir.is_dir():
        raise HermesSkillInstallError(
            "BUNDLE_WRITE_FAILED",
            f"Skill directory not found under source root: {skill_dir}",
        )
    if not (skill_dir / "SKILL.md").is_file():
        raise HermesSkillInstallError(
            "BUNDLE_WRITE_FAILED",
            f"Skill directory missing SKILL.md: {skill_dir}",
        )
    return skill_dir


def _read_yaml_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HermesSkillInstallError("CONFIG_WRITE_FAILED", f"Cannot read config: {exc}") from exc
    if not text.strip():
        return {}
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise HermesSkillInstallError(
            "CONFIG_WRITE_FAILED",
            f"Hermes config YAML is invalid: {exc}",
        ) from exc
    return data if isinstance(data, dict) else {}


def revision_for_config_file(path: Path) -> str:
    if not path.is_file():
        return hashlib.sha256(b"").hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def merge_external_dirs(doc: dict[str, Any], new_dir: Path) -> dict[str, Any]:
    """Return deep copy of doc with ``skills.external_dirs`` updated (no duplicates, resolved paths)."""
    out = copy.deepcopy(doc)
    skills = out.get("skills")
    if skills is None:
        skills = {}
        out["skills"] = skills
    if not isinstance(skills, dict):
        skills = {}
        out["skills"] = skills
    ed = skills.get("external_dirs")
    if ed is None:
        ed = []
    if not isinstance(ed, list):
        ed = []
    skills["external_dirs"] = list(ed)
    norm_new = str(new_dir.resolve())
    seen: set[str] = set()
    normalized_list: list[str] = []
    for item in skills["external_dirs"]:
        if isinstance(item, str):
            p = str(Path(item).expanduser().resolve())
        else:
            continue
        if p not in seen:
            seen.add(p)
            normalized_list.append(p)
    skills["external_dirs"] = normalized_list
    if norm_new not in seen:
        skills["external_dirs"] = [*normalized_list, norm_new]
    return out


def external_dirs_list(doc: dict[str, Any]) -> list[str]:
    skills = doc.get("skills")
    if not isinstance(skills, dict):
        return []
    ed = skills.get("external_dirs")
    if not isinstance(ed, list):
        return []
    out: list[str] = []
    for item in ed:
        if isinstance(item, str):
            out.append(str(Path(item).expanduser().resolve()))
    return out


def _allowlisted_bundle_dest(hermes_home: Path, catalog_id: str, content_hash: str) -> Path:
    root = _bundle_root(hermes_home)
    h = (content_hash or "unknown")[:16]
    dest = (root / _catalog_id_slug(catalog_id) / h).resolve()
    if dest != root and root not in dest.parents:
        raise HermesSkillInstallError("BUNDLE_WRITE_FAILED", "Bundle path escaped allowlisted root.")
    return dest


def _assert_under_managed_prefix(path: Path, prefix: Path) -> None:
    path = path.resolve()
    prefix = prefix.resolve()
    if path != prefix and prefix not in path.parents:
        raise HermesSkillInstallError("BUNDLE_WRITE_FAILED", "Path violates managed allowlist.")


def compute_proposal_digest(
    *,
    catalog_id: str,
    bundle_dest: Path,
    base_revision: str,
    external_dirs_after: list[str],
) -> str:
    payload = {
        "base_revision": base_revision,
        "bundle_dest": str(bundle_dest.resolve()),
        "catalog_id": catalog_id,
        "skills_external_dirs": sorted(external_dirs_after),
        "target": {"kind": "shared"},
    }
    body = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def config_diff_external_dirs(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    b = external_dirs_list(before)
    a = external_dirs_list(after)
    added = [x for x in a if x not in b]
    return {"before": b, "after": a, "added": added}


@dataclass(frozen=True)
class InstallPreviewResult:
    catalog_id: str
    target: dict[str, str]
    paths_touched: list[str]
    config_path: str
    config_diff: dict[str, Any]
    config_snippet_after: dict[str, Any]
    warnings: list[str]
    proposal_digest: str
    base_revision: str
    bundle_dest: str
    entry_summary: dict[str, Any]


def preview_shared_install(
    catalog_id: str,
    *,
    client_proposal_id: str | None = None,
) -> InstallPreviewResult:
    _ = client_proposal_id
    hermes_home = _require_local_shared_install()
    entry = get_catalog_entry_detail(catalog_id.strip())
    if entry is None:
        raise HermesSkillInstallError(
            "SKILL_NOT_IN_CATALOG",
            f"No Hermes catalog entry for id {catalog_id!r}.",
        )
    if not entry.get("installable_by_default"):
        raise HermesSkillInstallError(
            "SKILL_NOT_INSTALLABLE",
            f"Catalog entry {catalog_id!r} is not installable by default.",
        )
    content_hash = str(entry.get("content_hash_sha256") or "")
    cfg_path = _config_path_for_hermes_home(hermes_home)
    doc_before = _read_yaml_config(cfg_path)
    base_rev = revision_for_config_file(cfg_path)
    bundle_dest = _allowlisted_bundle_dest(hermes_home, catalog_id.strip(), content_hash)
    doc_after = merge_external_dirs(doc_before, bundle_dest)
    diff = config_diff_external_dirs(doc_before, doc_after)
    ext_after = external_dirs_list(doc_after)
    digest = compute_proposal_digest(
        catalog_id=catalog_id.strip(),
        bundle_dest=bundle_dest,
        base_revision=base_rev,
        external_dirs_after=ext_after,
    )
    warnings: list[str] = []
    if not diff["added"]:
        warnings.append(
            "This bundle path is already present in skills.external_dirs; apply will refresh bundle files only."
        )
    snippet = {
        "skills": {
            "external_dirs": ext_after,
        }
    }
    entry_summary = {
        "display_name": entry.get("display_name"),
        "trust_level": entry.get("trust_level"),
        "source_kind": entry.get("source_kind"),
        "source_ref": entry.get("source_ref"),
        "version_pin": entry.get("version_pin"),
        "content_hash_sha256": content_hash,
    }
    return InstallPreviewResult(
        catalog_id=catalog_id.strip(),
        target={"kind": "shared"},
        paths_touched=[str(cfg_path), str(bundle_dest)],
        config_path=str(cfg_path),
        config_diff=diff,
        config_snippet_after=snippet,
        warnings=warnings,
        proposal_digest=digest,
        base_revision=base_rev,
        bundle_dest=str(bundle_dest),
        entry_summary=entry_summary,
    )


def _acquire_install_lock_fd(fd: int) -> None:
    if sys.platform == "win32":
        # msvcrt locks byte ranges; ensure at least one byte exists.
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"\n")
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX)


def _release_install_lock_fd(fd: int) -> None:
    if sys.platform == "win32":
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def _install_lock(hermes_home: Path) -> Iterator[None]:
    lock_path = hermes_home / _LOCK_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        _acquire_install_lock_fd(fd)
        yield
    finally:
        _release_install_lock_fd(fd)
        os.close(fd)


def _atomic_write_yaml(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(
        doc,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _materialize_bundle(source_skill_dir: Path, dest: Path, bundle_allow_root: Path) -> None:
    _assert_under_managed_prefix(dest, bundle_allow_root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_dir():
        shutil.rmtree(dest)
    shutil.copytree(
        source_skill_dir,
        dest,
        symlinks=False,
        ignore_dangling_symlinks=True,
        dirs_exist_ok=False,
    )


@dataclass(frozen=True)
class InstallApplyResult:
    audit_id: str
    catalog_id: str
    target: dict[str, str]
    installed_paths: list[str]
    new_revision: str
    backup_id: str
    warnings: list[str]


def apply_shared_install(
    catalog_id: str,
    *,
    proposal_digest: str,
    base_revision: str,
) -> InstallApplyResult:
    hermes_home = _require_local_shared_install()
    cid = catalog_id.strip()
    preview = preview_shared_install(cid)
    if preview.base_revision != base_revision:
        raise HermesSkillInstallError(
            "APPLY_CONFLICT",
            "Hermes config changed since preview; run preview again.",
        )
    cfg_path = Path(preview.config_path)
    if revision_for_config_file(cfg_path) != base_revision:
        raise HermesSkillInstallError(
            "APPLY_CONFLICT",
            "Hermes config file revision does not match base_revision.",
        )
    if preview.proposal_digest != proposal_digest.strip():
        raise HermesSkillInstallError(
            "APPLY_CONFLICT",
            "proposal_digest does not match the current preview; run preview again.",
        )
    entry = get_catalog_entry_detail(cid)
    if entry is None or not entry.get("installable_by_default"):
        raise HermesSkillInstallError("SKILL_NOT_INSTALLABLE", "Catalog entry is not installable.")
    content_hash = str(entry.get("content_hash_sha256") or "")
    bundle_dest = _allowlisted_bundle_dest(hermes_home, cid, content_hash)
    if str(bundle_dest.resolve()) != str(Path(preview.bundle_dest).resolve()):
        raise HermesSkillInstallError("APPLY_CONFLICT", "Bundle destination drifted; run preview again.")
    source_skill_dir = _resolve_source_skill_dir(cid)
    bundle_allow_root = _bundle_root(hermes_home)
    doc_before = _read_yaml_config(cfg_path)
    doc_after = merge_external_dirs(doc_before, bundle_dest)

    backup_dir = hermes_home / _BACKUP_SUBDIR
    audit_dir = hermes_home / _AUDIT_SUBDIR
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_id = f"{stamp}_{uuid.uuid4().hex[:8]}"
    warnings = list(preview.warnings)

    with _install_lock(hermes_home):
        if revision_for_config_file(cfg_path) != base_revision:
            raise HermesSkillInstallError(
                "APPLY_CONFLICT",
                "Hermes config changed during apply; run preview again.",
            )
        try:
            _materialize_bundle(source_skill_dir, bundle_dest, bundle_allow_root)
        except OSError as exc:
            raise HermesSkillInstallError("BUNDLE_WRITE_FAILED", str(exc)) from exc
        backup_dir.mkdir(parents=True, exist_ok=True)
        audit_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"{backup_id}.yaml"
        pre_raw = cfg_path.read_bytes() if cfg_path.is_file() else b""
        backup_wrapper = {
            "format": 1,
            "config_path": str(cfg_path),
            "raw_bytes_b64": base64.b64encode(pre_raw).decode("ascii"),
            "note": "Hermes config snapshot before skills.external_dirs merge",
        }
        backup_path.write_text(
            json.dumps(backup_wrapper, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        try:
            _atomic_write_yaml(cfg_path, doc_after)
        except OSError as exc:
            raise HermesSkillInstallError("CONFIG_WRITE_FAILED", str(exc)) from exc

    new_rev = revision_for_config_file(cfg_path)
    audit_id = f"{backup_id}-audit"
    audit_payload = {
        "action": "hermes_skill_install_shared",
        "audit_id": audit_id,
        "backup_id": backup_id,
        "base_revision": base_revision,
        "catalog_id": cid,
        "config_path": str(cfg_path),
        "hermes_home": str(hermes_home),
        "installed_bundle": str(bundle_dest),
        "new_revision": new_rev,
        "proposal_digest": proposal_digest.strip(),
        "result": "ok",
        "target": {"kind": "shared"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    (audit_dir / f"{audit_id}.json").write_text(
        json.dumps(audit_payload, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return InstallApplyResult(
        audit_id=audit_id,
        catalog_id=cid,
        target={"kind": "shared"},
        installed_paths=[str(bundle_dest), str(cfg_path)],
        new_revision=new_rev,
        backup_id=backup_id,
        warnings=warnings,
    )


def assert_shared_target(target: Any) -> None:
    if not isinstance(target, dict) or set(target.keys()) != {"kind"} or target.get("kind") != "shared":
        raise HermesSkillInstallError(
            "TARGET_NOT_SUPPORTED",
            'Phase 2a accepts only target {"kind": "shared"} (Hermes profile targets are deferred).',
        )
