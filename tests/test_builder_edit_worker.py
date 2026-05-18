from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.ham.builder_chat_hooks import run_builder_happy_path_hook
from src.ham.builder_edit_worker import (
    DEFAULT_BUILDER_CODE_WORKER,
    apply_builder_worker_chat_directives,
    is_operator_plus_minus_blue_purple_border_edit,
    needs_hermes_gateway_edit_path,
    resolve_effective_builder_worker_id,
    run_builder_edit_worker_maybe,
    verify_calculator_gateway_patch,
    verify_plus_minus_blue_purple_preserve_calculator,
)
from src.ham.clerk_auth import HamActor
from src.persistence.builder_source_store import (
    BuilderSourceStore,
    ProjectSource,
    SourceSnapshot,
    set_builder_source_store_for_tests,
)

LONG_TAIL = "change the + and - button colors make them blue with purple border"


def _actor(user_id: str = "u") -> HamActor:
    return HamActor(
        user_id=user_id,
        org_id=None,
        session_id="sess",
        email=f"{user_id}@example.com",
        permissions=frozenset(),
        org_role=None,
        raw_permission_claim=None,
    )


def _sample_calc_snapshot_files() -> dict[str, str]:
    app = """
import React from 'react';
export default function App() {
  return (
    <main className="calc-app-root">
      <div className="keypad">
        <button type="button" className="ham-key-op">+</button>
        <button type="button" className="ham-key-op">-</button>
        <button type="button" className="ham-key-digit calc-digit-multicolor-keys calc-yellow-digit-border">1</button>
      </div>
    </main>
  );
}
"""
    css = """
.calc-digit-multicolor-keys { color: white; }
.calc-yellow-digit-border { border: 2px solid #facc15; }
.ham-key-op { background: #444; }
"""
    return {"src/App.tsx": app.strip(), "src/styles.css": css.strip()}


def _valid_gateway_patch_json(baseline: dict[str, str]) -> str:
    app = baseline["src/App.tsx"].replace(
        'className="ham-key-op">+',
        'className="ham-key-op ham-key-op-pm-plus">+',
    ).replace(
        'className="ham-key-op">-',
        'className="ham-key-op ham-key-op-pm-minus">-',
    )
    css = (
        baseline["src/styles.css"]
        + "\n.ham-key-op-pm-plus { background: #2563eb; border: 2px solid #a78bfa; }\n"
        + ".ham-key-op-pm-minus { background: #3b82f6; border: 2px solid #7c3aed; }\n"
    )
    payload = {
        "status": "success",
        "summary": "Style +/− only",
        "files": {"src/App.tsx": app, "src/styles.css": css},
        "checks": ["pm-classes", "theme"],
    }
    return json.dumps(payload, ensure_ascii=True)


@pytest.fixture(autouse=True)
def reset_builder_store():
    set_builder_source_store_for_tests(None)
    yield
    set_builder_source_store_for_tests(None)


def test_default_worker_is_hermes_gateway() -> None:
    assert DEFAULT_BUILDER_CODE_WORKER == "hermes_gateway"
    assert resolve_effective_builder_worker_id(None) == "hermes_gateway"
    src = ProjectSource(project_id="p", workspace_id="w")
    assert resolve_effective_builder_worker_id(src) == "hermes_gateway"


def test_long_tail_prompt_detected() -> None:
    assert is_operator_plus_minus_blue_purple_border_edit(LONG_TAIL) is True
    assert needs_hermes_gateway_edit_path(LONG_TAIL) is True
    assert is_operator_plus_minus_blue_purple_border_edit("make digits purple") is False
    assert needs_hermes_gateway_edit_path("make the digit keys purple") is False
    assert needs_hermes_gateway_edit_path("ham change the AC button to purple") is True
    assert needs_hermes_gateway_edit_path(
        "add particle effects when lines clear",
        active_template="tetris",
    ) is True


def test_verify_general_patch_preserves_theme() -> None:
    b = _sample_calc_snapshot_files()
    bad = dict(b)
    bad["src/App.tsx"] = b["src/App.tsx"].replace("calc-digit-multicolor-keys", "")
    assert verify_calculator_gateway_patch(before=b, after=bad, user_plain="change the AC button to purple") is False
    assert verify_calculator_gateway_patch(before=b, after=b, user_plain="change the AC button to purple") is True


def test_mock_gateway_blocks_without_snapshot_job(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "mock")
    store = BuilderSourceStore(store_path=tmp_path / "s.json")
    set_builder_source_store_for_tests(store)
    ws, pid = "ws1", "pr1"
    src = ProjectSource(
        workspace_id=ws,
        project_id=pid,
        kind="chat_scaffold",
        active_snapshot_id="snap1",
    )
    store.upsert_project_source(src)
    snap = SourceSnapshot(
        id="snap1",
        workspace_id=ws,
        project_id=pid,
        project_source_id=src.id,
        manifest={
            "kind": "inline_text_bundle",
            "file_count": 2,
            "entries": [
                {"path": "src/App.tsx", "size_bytes": 10},
                {"path": "src/styles.css", "size_bytes": 10},
            ],
            "inline_files": _sample_calc_snapshot_files(),
        },
    )
    store.upsert_source_snapshot(snap)

    out = run_builder_edit_worker_maybe(
        workspace_id=ws,
        project_id=pid,
        session_id="sess",
        last_user_plain=LONG_TAIL,
        created_by="u1",
        operation="update_existing_project",
        preferred_source=src,
        active_snapshot=snap,
    )
    assert out is not None
    assert out.get("builder_edit_worker_blocked") is True
    assert out.get("scaffolded") is not True
    jobs = store.list_import_jobs(workspace_id=ws, project_id=pid)
    assert jobs == []


def test_valid_hermes_json_writes_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:9")
    baseline = _sample_calc_snapshot_files()

    def fake_turn(messages: list) -> str:  # noqa: ARG001
        return _valid_gateway_patch_json(baseline)

    store = BuilderSourceStore(store_path=tmp_path / "s2.json")
    set_builder_source_store_for_tests(store)
    ws, pid = "ws2", "pr2"
    src = ProjectSource(
        workspace_id=ws,
        project_id=pid,
        kind="chat_scaffold",
        active_snapshot_id="snap_a",
        metadata={"template": "calculator"},
    )
    store.upsert_project_source(src)
    snap = SourceSnapshot(
        id="snap_a",
        workspace_id=ws,
        project_id=pid,
        project_source_id=src.id,
        metadata={"template": "calculator"},
        manifest={
            "kind": "inline_text_bundle",
            "file_count": 2,
            "entries": [],
            "inline_files": baseline,
        },
    )
    store.upsert_source_snapshot(snap)

    out = run_builder_edit_worker_maybe(
        workspace_id=ws,
        project_id=pid,
        session_id="sess",
        last_user_plain=LONG_TAIL,
        created_by="u1",
        operation="update_existing_project",
        preferred_source=src,
        active_snapshot=snap,
        complete_turn=fake_turn,
    )
    assert out is not None
    assert out.get("scaffolded") is True
    assert out.get("builder_edit_worker_blocked") is not True
    new_id = str(out.get("source_snapshot_id") or "")
    assert new_id and new_id != "snap_a"
    src2 = store.list_project_sources(workspace_id=ws, project_id=pid)[0]
    assert src2.active_snapshot_id == new_id
    jobs = store.list_import_jobs(workspace_id=ws, project_id=pid)
    assert jobs and jobs[0].status == "succeeded"
    meta = jobs[0].metadata or {}
    assert meta.get("origin") == "builder_edit_worker"
    seq = meta.get("builder_edit_activity") or []
    steps = [row.get("step") for row in seq]
    for name in ("plan", "read_files", "worker_selected", "patch_requested", "patch_received", "verify"):
        assert name in steps


def test_invalid_json_blocked(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:9")
    store = BuilderSourceStore(store_path=tmp_path / "s3.json")
    set_builder_source_store_for_tests(store)
    ws, pid = "ws3", "pr3"
    baseline = _sample_calc_snapshot_files()
    src = ProjectSource(workspace_id=ws, project_id=pid, kind="chat_scaffold", active_snapshot_id="s1")
    store.upsert_project_source(src)
    snap = SourceSnapshot(
        id="s1",
        workspace_id=ws,
        project_id=pid,
        project_source_id=src.id,
        manifest={
            "kind": "inline_text_bundle",
            "file_count": 2,
            "entries": [],
            "inline_files": baseline,
        },
    )
    store.upsert_source_snapshot(snap)

    def bad_turn(_m: list) -> str:
        return "not json at all"

    out = run_builder_edit_worker_maybe(
        workspace_id=ws,
        project_id=pid,
        session_id="sess",
        last_user_plain=LONG_TAIL,
        created_by="u1",
        operation="update_existing_project",
        preferred_source=src,
        active_snapshot=snap,
        complete_turn=bad_turn,
    )
    assert out and out.get("builder_edit_worker_blocked")
    assert out.get("scaffolded") is not True
    snaps = store.list_source_snapshots(workspace_id=ws, project_id=pid)
    assert len(snaps) == 1


def test_no_op_blocked(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:9")
    baseline = _sample_calc_snapshot_files()
    payload = {"status": "success", "summary": "x", "files": baseline, "checks": []}

    def same_turn(_m: list) -> str:
        return json.dumps(payload, ensure_ascii=True)

    store = BuilderSourceStore(store_path=tmp_path / "s4.json")
    set_builder_source_store_for_tests(store)
    ws, pid = "ws4", "pr4"
    src = ProjectSource(workspace_id=ws, project_id=pid, kind="chat_scaffold", active_snapshot_id="s1")
    store.upsert_project_source(src)
    snap = SourceSnapshot(
        id="s1",
        workspace_id=ws,
        project_id=pid,
        project_source_id=src.id,
        manifest={"kind": "inline_text_bundle", "file_count": 2, "entries": [], "inline_files": baseline},
    )
    store.upsert_source_snapshot(snap)
    out = run_builder_edit_worker_maybe(
        workspace_id=ws,
        project_id=pid,
        session_id="sess",
        last_user_plain=LONG_TAIL,
        created_by="u1",
        operation="update_existing_project",
        preferred_source=src,
        active_snapshot=snap,
        complete_turn=same_turn,
    )
    assert out and out.get("builder_edit_worker_blocked")


def test_verify_preserves_theme() -> None:
    b = _sample_calc_snapshot_files()
    bad = dict(b)
    bad["src/App.tsx"] = b["src/App.tsx"].replace("calc-digit-multicolor-keys", "")
    assert verify_plus_minus_blue_purple_preserve_calculator(before=b, after=bad) is False
    good = json.loads(_valid_gateway_patch_json(b))
    merged = dict(b)
    merged.update(good["files"])
    assert verify_plus_minus_blue_purple_preserve_calculator(before=b, after=merged) is True


def test_unsupported_worker_override_blocked(tmp_path) -> None:
    store = BuilderSourceStore(store_path=tmp_path / "sw.json")
    set_builder_source_store_for_tests(store)
    src = ProjectSource(
        workspace_id="w",
        project_id="p",
        kind="chat_scaffold",
        metadata={"builder_code_worker": "cursor_cli"},
        active_snapshot_id="snap_x",
    )
    store.upsert_project_source(src)
    store.upsert_source_snapshot(
        SourceSnapshot(
            id="snap_x",
            workspace_id="w",
            project_id="p",
            project_source_id=src.id,
            manifest={
                "kind": "inline_text_bundle",
                "file_count": 2,
                "entries": [],
                "inline_files": _sample_calc_snapshot_files(),
            },
        ),
    )
    out = run_builder_edit_worker_maybe(
        workspace_id="w",
        project_id="p",
        session_id="s",
        last_user_plain=LONG_TAIL,
        created_by="u",
        operation="update_existing_project",
        preferred_source=src,
        active_snapshot=store.list_source_snapshots(workspace_id="w", project_id="p")[0],
    )
    assert out and out.get("builder_edit_worker_blocked")
    assert (out.get("builder_edit_worker") or {}).get("blocked_reason") == "unsupported_worker"


def test_advice_does_not_invoke_worker(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    called: list[str] = []

    def boom(_m: list) -> str:
        called.append("x")
        return "{}"

    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:9")
    store = BuilderSourceStore(store_path=tmp_path / "adv.json")
    set_builder_source_store_for_tests(store)
    ws, pid = "wa", "pa"
    src = ProjectSource(workspace_id=ws, project_id=pid, kind="chat_scaffold", active_snapshot_id="sx")
    store.upsert_project_source(src)
    snap = SourceSnapshot(
        id="sx",
        workspace_id=ws,
        project_id=pid,
        project_source_id=src.id,
        manifest={
            "kind": "inline_text_bundle",
            "entries": [],
            "inline_files": _sample_calc_snapshot_files(),
        },
    )
    store.upsert_source_snapshot(snap)

    with patch("src.ham.builder_edit_worker.complete_chat_turn", boom):
        prefix, meta = run_builder_happy_path_hook(
            workspace_id=ws,
            project_id=pid,
            session_id="sess",
            last_user_plain="what files did you change?",
            ham_actor=_actor(),
        )
    assert called == []
    assert prefix is None


def test_scaffold_edit_not_long_tail(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Digit purple follow-up stays on scaffold path when verifier lists purple_digit_keys."""
    spy: list[str] = []

    def boom(_m: list) -> str:
        spy.append("gateway")
        return "{}"

    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:9")
    store = BuilderSourceStore(store_path=tmp_path / "sc.json")
    set_builder_source_store_for_tests(store)
    ws, pid = "wb", "pb"
    src = ProjectSource(workspace_id=ws, project_id=pid, kind="chat_scaffold", active_snapshot_id="sb")
    store.upsert_project_source(src)
    snap = SourceSnapshot(
        id="sb",
        workspace_id=ws,
        project_id=pid,
        project_source_id=src.id,
        manifest={
            "kind": "inline_text_bundle",
            "entries": [],
            "inline_files": _sample_calc_snapshot_files(),
        },
        metadata={"template": "calculator", "calculator_purple_digit_keys": True},
    )
    store.upsert_source_snapshot(snap)
    with patch("src.ham.builder_edit_worker.complete_chat_turn", boom):
        run_builder_happy_path_hook(
            workspace_id=ws,
            project_id=pid,
            session_id="sess",
            last_user_plain="make the digit keys darker purple",
            ham_actor=_actor(),
        )
    assert spy == []


def test_chat_directive_use_cursor_message(tmp_path) -> None:
    store = BuilderSourceStore(store_path=tmp_path / "dir.json")
    src = ProjectSource(workspace_id="w", project_id="p", kind="chat_scaffold")
    res = apply_builder_worker_chat_directives(
        last_user_plain="use Cursor for this project",
        project_source=src,
        store=store,
    )
    assert not res.cleaned_prompt.strip()
    assert "not available" in (res.assistant_note or "").lower()
    assert res.blocked_reason == "cursor"


def test_chat_directive_use_hermes_persists(tmp_path) -> None:
    store = BuilderSourceStore(store_path=tmp_path / "dh.json")
    src = ProjectSource(workspace_id="w", project_id="p", kind="chat_scaffold", id="psrc_x")
    store.upsert_project_source(src)
    res = apply_builder_worker_chat_directives(
        last_user_plain="use Hermes for this app",
        project_source=store.list_project_sources(workspace_id="w", project_id="p")[0],
        store=store,
    )
    row = store.list_project_sources(workspace_id="w", project_id="p")[0]
    assert (row.metadata or {}).get("builder_code_worker") == "hermes_gateway"
    assert res.cleaned_prompt == ""


def test_hook_invokes_gateway_for_long_tail(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:9")
    baseline = _sample_calc_snapshot_files()
    invoked: list[bool] = []

    def fake_turn(messages: list) -> str:
        invoked.append(True)
        assert "current_files" in messages[-1]["content"]
        return _valid_gateway_patch_json(baseline)

    store = BuilderSourceStore(store_path=tmp_path / "hk.json")
    set_builder_source_store_for_tests(store)
    ws, pid = "wh", "ph"
    src = ProjectSource(workspace_id=ws, project_id=pid, kind="chat_scaffold", active_snapshot_id="sh")
    store.upsert_project_source(src)
    store.upsert_source_snapshot(
        SourceSnapshot(
            id="sh",
            workspace_id=ws,
            project_id=pid,
            project_source_id=src.id,
            manifest={"kind": "inline_text_bundle", "entries": [], "inline_files": baseline},
        ),
    )
    with patch("src.ham.builder_edit_worker.complete_chat_turn", fake_turn):
        prefix, meta = run_builder_happy_path_hook(
            workspace_id=ws,
            project_id=pid,
            session_id="sess",
            last_user_plain=LONG_TAIL,
            ham_actor=_actor(),
        )
    assert invoked == [True]
    assert meta.get("scaffolded") is True
    assert (meta.get("builder_edit_worker") or {}).get("applied") is True
    assert prefix


def test_hook_invokes_gateway_for_ac_purple(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:9")
    baseline = _sample_calc_snapshot_files()
    invoked: list[bool] = []

    def fake_turn(messages: list) -> str:
        invoked.append(True)
        assert "current_files" in messages[-1]["content"]
        return _valid_gateway_patch_json(baseline)

    store = BuilderSourceStore(store_path=tmp_path / "ac.json")
    set_builder_source_store_for_tests(store)
    ws, pid = "wac", "pac"
    src = ProjectSource(workspace_id=ws, project_id=pid, kind="chat_scaffold", active_snapshot_id="sac")
    store.upsert_project_source(src)
    store.upsert_source_snapshot(
        SourceSnapshot(
            id="sac",
            workspace_id=ws,
            project_id=pid,
            project_source_id=src.id,
            metadata={"template": "calculator"},
            manifest={"kind": "inline_text_bundle", "entries": [], "inline_files": baseline},
        ),
    )
    with patch("src.ham.builder_edit_worker.complete_chat_turn", fake_turn):
        prefix, meta = run_builder_happy_path_hook(
            workspace_id=ws,
            project_id=pid,
            session_id="sess",
            last_user_plain="ham change the AC button to purple",
            ham_actor=_actor(),
        )
    assert invoked == [True]
    assert meta.get("scaffolded") is True
    assert (meta.get("builder_edit_worker") or {}).get("applied") is True
    assert prefix


def _tetris_min_files() -> dict[str, str]:
    app = (
        'import React from "react";\n'
        "export default function App() {\n"
        '  return <main className="tetris-root"><p>Tetris</p></main>;\n'
        "}\n"
    )
    css = ".tetris-root { padding: 1rem; }\n"
    return {"src/App.tsx": app, "src/styles.css": css, "package.json": "{}\n"}


def _tetris_patch_json(baseline: dict[str, str]) -> str:
    app = baseline["src/App.tsx"].replace("<p>Tetris</p>", "<p>Tetris</p>\n{/* ham-particles-v1 */}")
    payload = {
        "status": "success",
        "summary": "particles",
        "files": {"src/App.tsx": app},
        "checks": [],
    }
    return json.dumps(payload, ensure_ascii=True)


def test_tetris_worker_applies_gateway_patch(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:9")
    baseline = _tetris_min_files()
    store = BuilderSourceStore(store_path=tmp_path / "tr.json")
    set_builder_source_store_for_tests(store)
    ws, pid = "wtr", "ptr"
    src = ProjectSource(workspace_id=ws, project_id=pid, kind="chat_scaffold", active_snapshot_id="str1")
    store.upsert_project_source(src)
    store.upsert_source_snapshot(
        SourceSnapshot(
            id="str1",
            workspace_id=ws,
            project_id=pid,
            project_source_id=src.id,
            metadata={"template": "tetris"},
            manifest={"kind": "inline_text_bundle", "entries": [], "inline_files": baseline},
        ),
    )
    snap = store.list_source_snapshots(workspace_id=ws, project_id=pid)[0]

    out = run_builder_edit_worker_maybe(
        workspace_id=ws,
        project_id=pid,
        session_id="sess",
        last_user_plain="add particle effects when lines clear",
        created_by="u1",
        operation="update_existing_project",
        preferred_source=src,
        active_snapshot=snap,
        complete_turn=lambda _m: _tetris_patch_json(baseline),
    )
    assert out and out.get("scaffolded") is True
    assert str(out.get("source_snapshot_id") or "") != "str1"


def test_tetris_worker_rejects_disallowed_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:9")
    baseline = _tetris_min_files()
    store = BuilderSourceStore(store_path=tmp_path / "tr2.json")
    set_builder_source_store_for_tests(store)
    ws, pid = "w2", "p2"
    src = ProjectSource(workspace_id=ws, project_id=pid, kind="chat_scaffold", active_snapshot_id="s2")
    store.upsert_project_source(src)
    snap = SourceSnapshot(
        id="s2",
        workspace_id=ws,
        project_id=pid,
        project_source_id=src.id,
        metadata={"template": "tetris"},
        manifest={"kind": "inline_text_bundle", "entries": [], "inline_files": baseline},
    )
    store.upsert_source_snapshot(snap)

    def bad_turn(_m: list) -> str:
        payload = {"status": "success", "summary": "x", "files": {"README.md": "nope"}, "checks": []}
        return json.dumps(payload)

    out = run_builder_edit_worker_maybe(
        workspace_id=ws,
        project_id=pid,
        session_id="sess",
        last_user_plain="add particle effects when lines clear",
        created_by="u1",
        operation="update_existing_project",
        preferred_source=src,
        active_snapshot=snap,
        complete_turn=bad_turn,
    )
    assert out and out.get("builder_edit_worker_blocked")


def test_tetris_worker_rejects_empty_existing_file_patch(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Gateway must not be able to wipe an existing snapshot path with an empty string (verify_* allows keys-only)."""
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:9")
    baseline = _tetris_min_files()
    store = BuilderSourceStore(store_path=tmp_path / "empty.json")
    set_builder_source_store_for_tests(store)
    ws, pid = "we", "pe"
    src = ProjectSource(workspace_id=ws, project_id=pid, kind="chat_scaffold", active_snapshot_id="se")
    store.upsert_project_source(src)
    snap = SourceSnapshot(
        id="se",
        workspace_id=ws,
        project_id=pid,
        project_source_id=src.id,
        metadata={"template": "tetris"},
        manifest={"kind": "inline_text_bundle", "entries": [], "inline_files": baseline},
    )
    store.upsert_source_snapshot(snap)

    def empty_turn(_m: list) -> str:
        return json.dumps(
            {
                "status": "success",
                "summary": "bad",
                "files": {"src/App.tsx": ""},
                "checks": [],
            }
        )

    out = run_builder_edit_worker_maybe(
        workspace_id=ws,
        project_id=pid,
        session_id="sess",
        last_user_plain="add particle effects when lines clear",
        created_by="u1",
        operation="update_existing_project",
        preferred_source=src,
        active_snapshot=snap,
        complete_turn=empty_turn,
    )
    assert out and out.get("builder_edit_worker_blocked")
    assert (out.get("builder_edit_worker") or {}).get("blocked_reason") == "empty_file_content"


def test_tetris_worker_blocks_no_op_patch(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:9")
    baseline = _tetris_min_files()
    store = BuilderSourceStore(store_path=tmp_path / "noop.json")
    set_builder_source_store_for_tests(store)
    ws, pid = "wn", "pn"
    src = ProjectSource(workspace_id=ws, project_id=pid, kind="chat_scaffold", active_snapshot_id="sn")
    store.upsert_project_source(src)
    snap = SourceSnapshot(
        id="sn",
        workspace_id=ws,
        project_id=pid,
        project_source_id=src.id,
        metadata={"template": "tetris"},
        manifest={"kind": "inline_text_bundle", "entries": [], "inline_files": baseline},
    )
    store.upsert_source_snapshot(snap)

    def noop_turn(_m: list) -> str:
        # Non-empty files object required; identical contents must still fail closed as no_op.
        return json.dumps(
            {
                "status": "success",
                "summary": "noop",
                "files": {"src/App.tsx": baseline["src/App.tsx"]},
                "checks": [],
            }
        )

    out = run_builder_edit_worker_maybe(
        workspace_id=ws,
        project_id=pid,
        session_id="sess",
        last_user_plain="add particle effects when lines clear",
        created_by="u1",
        operation="update_existing_project",
        preferred_source=src,
        active_snapshot=snap,
        complete_turn=noop_turn,
    )
    assert out and out.get("builder_edit_worker_blocked")
    assert (out.get("builder_edit_worker") or {}).get("blocked_reason") == "no_op"


def test_tetris_advice_does_not_invoke_worker(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    called: list[bool] = []

    def boom(_m: list) -> str:
        called.append(True)
        return "{}"

    monkeypatch.setenv("HERMES_GATEWAY_MODE", "http")
    monkeypatch.setenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:9")
    store = BuilderSourceStore(store_path=tmp_path / "adv2.json")
    set_builder_source_store_for_tests(store)
    ws, pid = "wa2", "pa2"
    src = ProjectSource(workspace_id=ws, project_id=pid, kind="chat_scaffold", active_snapshot_id="sx2")
    store.upsert_project_source(src)
    snap = SourceSnapshot(
        id="sx2",
        workspace_id=ws,
        project_id=pid,
        project_source_id=src.id,
        metadata={"template": "tetris"},
        manifest={"kind": "inline_text_bundle", "entries": [], "inline_files": _tetris_min_files()},
    )
    store.upsert_source_snapshot(snap)
    with patch("src.ham.builder_edit_worker.complete_chat_turn", boom):
        prefix, meta = run_builder_happy_path_hook(
            workspace_id=ws,
            project_id=pid,
            session_id="sess",
            last_user_plain="what would you improve about this game?",
            ham_actor=_actor(),
        )
    assert called == []
    assert prefix is None