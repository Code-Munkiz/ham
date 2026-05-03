"""Store-level tests for ``preview_social_policy`` / apply / rollback.

Covers atomic write, revision conflict, backup + audit envelope creation,
bounded history listing, and absence of any outbound network or provider
side-effects (proven via :class:`pytest.MonkeyPatch` interception).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.ham.social_policy import (
    DEFAULT_SOCIAL_POLICY,
    SocialPolicyChanges,
    SocialPolicyWriteConflictError,
    apply_social_policy,
    list_audit_envelopes,
    list_backups,
    preview_social_policy,
    read_social_policy_document,
    revision_for_document,
    rollback_social_policy,
    social_policy_path,
    social_policy_writes_enabled,
)
from src.ham.social_policy.schema import (
    SocialPolicy,
)


def _changes(**overrides: Any) -> SocialPolicyChanges:
    base = DEFAULT_SOCIAL_POLICY.model_dump(mode="json")
    base.update(overrides)
    return SocialPolicyChanges(policy=SocialPolicy.model_validate(base))


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Pin the policy file under tmp and return the project root."""
    monkeypatch.delenv("HAM_SOCIAL_POLICY_PATH", raising=False)
    monkeypatch.delenv("HAM_SOCIAL_POLICY_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("HAM_SOCIAL_LIVE_APPLY_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _block_outbound_network(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Fail loudly on any urllib / socket attempt during preview/apply/rollback."""
    counters = {"urlopen": 0, "socket_connect": 0}

    def _block_urlopen(*args: Any, **kwargs: Any) -> Any:
        counters["urlopen"] += 1
        raise RuntimeError("urllib.request.urlopen called during policy operation")

    def _block_socket_connect(self: Any, *args: Any, **kwargs: Any) -> Any:
        counters["socket_connect"] += 1
        raise RuntimeError("socket.connect called during policy operation")

    import socket
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", _block_urlopen)
    monkeypatch.setattr(socket.socket, "connect", _block_socket_connect)
    return counters


def test_preview_with_no_existing_doc_warns_and_does_not_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolate(monkeypatch, tmp_path)
    counters = _block_outbound_network(monkeypatch)

    changes = _changes()
    result = preview_social_policy(root, changes)

    assert result.write_target.endswith("social_policy.json")
    assert "no_existing_policy_document_first_apply_will_create_one" in result.warnings
    assert result.live_autonomy_change is False
    assert result.base_revision == revision_for_document({})
    # Preview NEVER writes.
    assert not social_policy_path(root).exists()
    assert counters == {"urlopen": 0, "socket_connect": 0}


def test_apply_writes_atomically_creates_backup_and_audit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolate(monkeypatch, tmp_path)
    _block_outbound_network(monkeypatch)

    changes = _changes()
    preview = preview_social_policy(root, changes)
    apply_result = apply_social_policy(root, changes, base_revision=preview.base_revision)

    target = social_policy_path(root)
    assert target.is_file()
    on_disk = json.loads(target.read_text(encoding="utf-8"))
    SocialPolicy.model_validate(on_disk)
    assert apply_result.new_revision == revision_for_document(on_disk)
    assert apply_result.live_autonomy_change is False

    # Backup directory contains exactly one snapshot of the *prior* doc ({}).
    backups = list_backups(root)
    assert len(backups) == 1
    assert backups[0]["backup_id"] == apply_result.backup_id
    backup_doc = json.loads(
        (root / ".ham" / "_backups" / "social_policy" / f"{apply_result.backup_id}.json").read_text(
            encoding="utf-8"
        )
    )
    assert backup_doc["document"] == {}
    assert backup_doc["captured_revision"] == revision_for_document({})

    # Audit envelope exists and references the backup id.
    audits = list_audit_envelopes(root)
    assert len(audits) == 1
    assert audits[0]["audit_id"] == apply_result.audit_id
    assert audits[0]["action"] == "apply"
    assert audits[0]["live_autonomy_change"] is False


def test_apply_revision_conflict_blocks_second_writer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolate(monkeypatch, tmp_path)
    _block_outbound_network(monkeypatch)

    # First writer succeeds.
    changes_a = _changes()
    preview_a = preview_social_policy(root, changes_a)
    apply_social_policy(root, changes_a, base_revision=preview_a.base_revision)

    # Second writer used the *original* (pre-write) preview's revision.
    # Revision check should fire and reject.
    with pytest.raises(SocialPolicyWriteConflictError):
        apply_social_policy(root, changes_a, base_revision=preview_a.base_revision)


def test_proposal_digest_is_stable_for_same_input(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolate(monkeypatch, tmp_path)
    changes = _changes()
    a = preview_social_policy(root, changes)
    b = preview_social_policy(root, changes)
    assert a.proposal_digest == b.proposal_digest


def test_diff_reports_leaf_changes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolate(monkeypatch, tmp_path)
    base = _changes()
    apply_social_policy(root, base, base_revision=preview_social_policy(root, base).base_revision)

    # Modify a single field.
    raw = DEFAULT_SOCIAL_POLICY.model_dump(mode="json")
    raw["providers"]["x"]["posting_mode"] = "preview"
    next_changes = SocialPolicyChanges(policy=SocialPolicy.model_validate(raw))
    preview = preview_social_policy(root, next_changes)
    paths = {entry["path"] for entry in preview.diff}
    assert "providers.x.posting_mode" in paths


def test_rollback_restores_prior_document_and_keeps_pre_rollback_backup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolate(monkeypatch, tmp_path)
    _block_outbound_network(monkeypatch)

    # Apply v1.
    v1 = _changes()
    p1 = preview_social_policy(root, v1)
    a1 = apply_social_policy(root, v1, base_revision=p1.base_revision)

    # Apply v2: posting_mode changes.
    raw = DEFAULT_SOCIAL_POLICY.model_dump(mode="json")
    raw["providers"]["x"]["posting_mode"] = "preview"
    v2 = SocialPolicyChanges(policy=SocialPolicy.model_validate(raw))
    p2 = preview_social_policy(root, v2)
    apply_social_policy(root, v2, base_revision=p2.base_revision)

    # We now have two backups: the pre-v1 backup (a1.backup_id, contents={})
    # and the pre-v2 backup (contents=v1 doc). Find the pre-v2 backup by
    # filtering rather than relying on lexical sort order (the timestamps
    # may collide in the same second).
    backups = list_backups(root)
    assert len(backups) == 2
    pre_v2_candidates = [
        b["backup_id"] for b in backups if b["backup_id"] != a1.backup_id
    ]
    assert len(pre_v2_candidates) == 1
    pre_v2_backup_id = pre_v2_candidates[0]

    rollback = rollback_social_policy(root, pre_v2_backup_id)
    on_disk = read_social_policy_document(root)
    assert on_disk["providers"]["x"]["posting_mode"] == "off"
    assert rollback.new_revision == revision_for_document(on_disk)

    audits = list_audit_envelopes(root)
    actions = [a["action"] for a in audits]
    assert "rollback" in actions


def test_rollback_rejects_invalid_backup_id_shape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolate(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="invalid shape"):
        rollback_social_policy(root, "../../../etc/passwd")
    with pytest.raises(ValueError, match="invalid shape"):
        rollback_social_policy(root, "totally-not-a-stamp")


def test_rollback_missing_backup_raises_filenotfound(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolate(monkeypatch, tmp_path)
    # Well-formed shape but no such file.
    with pytest.raises(FileNotFoundError):
        rollback_social_policy(root, "20260503T040000Z_aaaaaaaa")


def test_history_and_audit_listings_are_bounded_to_25(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolate(monkeypatch, tmp_path)
    backup_dir = root / ".ham" / "_backups" / "social_policy"
    audit_dir = root / ".ham" / "_audit" / "social_policy"
    backup_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)

    for i in range(40):
        backup_id = f"20260503T04{i:04d}Z_{i:08x}"
        (backup_dir / f"{backup_id}.json").write_text(
            json.dumps({"format": 1, "document": {}, "captured_revision": "x"}),
            encoding="utf-8",
        )
        (audit_dir / f"{backup_id}-audit.json").write_text(
            json.dumps(
                {
                    "audit_id": f"{backup_id}-audit",
                    "timestamp": "2026-05-03T04:00:00Z",
                    "action": "apply",
                    "backup_id": backup_id,
                    "previous_revision": "x",
                    "new_revision": "y",
                    "live_autonomy_change": False,
                    "diff": [],
                    "result": "ok",
                }
            ),
            encoding="utf-8",
        )

    assert len(list_backups(root)) == 25
    assert len(list_audit_envelopes(root)) == 25


def test_writes_enabled_only_when_token_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HAM_SOCIAL_POLICY_WRITE_TOKEN", raising=False)
    assert social_policy_writes_enabled() is False
    monkeypatch.setenv("HAM_SOCIAL_POLICY_WRITE_TOKEN", "x")
    assert social_policy_writes_enabled() is True


def test_apply_records_live_autonomy_change_when_flag_flips(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolate(monkeypatch, tmp_path)
    _block_outbound_network(monkeypatch)

    # First apply with autonomy off.
    base = _changes()
    p1 = preview_social_policy(root, base)
    apply_social_policy(root, base, base_revision=p1.base_revision)

    # Second apply flips live_autonomy_armed=True (allowed at the schema level
    # only when autopilot_mode == "armed").
    raw = DEFAULT_SOCIAL_POLICY.model_dump(mode="json")
    raw["autopilot_mode"] = "armed"
    raw["live_autonomy_armed"] = True
    armed = SocialPolicyChanges(policy=SocialPolicy.model_validate(raw))
    p2 = preview_social_policy(root, armed)
    assert p2.live_autonomy_change is True
    apply = apply_social_policy(root, armed, base_revision=p2.base_revision)
    assert apply.live_autonomy_change is True
    audits = list_audit_envelopes(root)
    flags = [a.get("live_autonomy_change") for a in audits if a.get("action") == "apply"]
    assert True in flags


def test_module_does_not_import_provider_or_scheduler_modules() -> None:
    import importlib

    store_mod = importlib.import_module("src.ham.social_policy.store")
    schema_mod = importlib.import_module("src.ham.social_policy.schema")
    api_mod = importlib.import_module("src.api.social_policy")

    forbidden = {
        "asyncio",  # no event loops in this layer
        "threading",
        "src.ham.social_telegram_send",  # no live transport
        "src.ham.ham_x.goham_live_controller",
        "src.ham.ham_x.goham_reactive_live",
    }
    for mod in (store_mod, schema_mod, api_mod):
        loaded = set()
        for name in mod.__dict__:
            value = mod.__dict__[name]
            if hasattr(value, "__module__"):
                loaded.add(value.__module__)
        for f in forbidden:
            assert not any(name == f or name.startswith(f + ".") for name in loaded), (
                f"{mod.__name__} unexpectedly imported {f}"
            )


def test_atomic_write_via_tmp_replace_no_partial_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """After apply, only the canonical file exists (no leftover .tmp)."""
    root = _isolate(monkeypatch, tmp_path)
    changes = _changes()
    preview = preview_social_policy(root, changes)
    apply_social_policy(root, changes, base_revision=preview.base_revision)

    target = social_policy_path(root)
    assert target.is_file()
    siblings = sorted(p.name for p in target.parent.iterdir())
    assert "social_policy.json.tmp" not in siblings
