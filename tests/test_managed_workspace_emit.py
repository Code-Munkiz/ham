"""Managed workspace emitter: deterministic layout + fake object storage."""

from __future__ import annotations

import os
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from src.api.clerk_gate import get_ham_clerk_actor
from src.api.server import fastapi_app
from src.ham.droid_runner.build_lane_output import PostExecCommon
from src.ham.managed_workspace.snapshot_object_storage import DictSnapshotObjectStorage
from src.ham.managed_workspace.snapshot_store import (
    MemoryProjectSnapshotStore,
    set_project_snapshot_store_for_tests,
)
from src.ham.managed_workspace.workspace_adapter import (
    emit_managed_workspace_snapshot,
    managed_workspace_runtime,
    reset_managed_workspace_runtime,
)
from src.persistence.project_store import get_project_store


@pytest.fixture(autouse=True)
def _reset_managed_fixture() -> object:
    reset_managed_workspace_runtime()
    set_project_snapshot_store_for_tests(None)
    old = os.environ.pop("HAM_MANAGED_WORKSPACE_ROOT", None)
    yield
    reset_managed_workspace_runtime()
    set_project_snapshot_store_for_tests(None)
    if old is None:
        os.environ.pop("HAM_MANAGED_WORKSPACE_ROOT", None)
    else:
        os.environ["HAM_MANAGED_WORKSPACE_ROOT"] = old


def _layout(tmp_path: Path, workspace_id: str, project_id: str) -> Path:
    base = tmp_path / "roots"
    os.environ["HAM_MANAGED_WORKSPACE_ROOT"] = str(base)
    work = base / "managed" / workspace_id / project_id / "working"
    (work / "src").mkdir(parents=True, exist_ok=True)
    (work / "src/hello.txt").write_text("world", encoding="utf-8")
    return work


def test_emit_first_snapshot_writes_manifest_and_head(tmp_path: Path) -> None:
    stor = DictSnapshotObjectStorage()
    rt = managed_workspace_runtime()
    rt.object_storage = stor
    set_project_snapshot_store_for_tests(MemoryProjectSnapshotStore())

    wid = "wsdemo"
    pid = "projlocal"
    work = _layout(tmp_path, wid, pid)

    common = PostExecCommon(
        project_id=pid,
        project_root=work,
        summary=None,
        change_id="corr-1",
        workspace_id=wid,
    )
    out = emit_managed_workspace_snapshot(common)
    assert out.build_outcome == "succeeded"
    assert out.target_ref.get("neutral_outcome") == "succeeded"

    sid = str(out.target_ref.get("snapshot_id") or "").strip()
    assert sid

    mf_path = f"{wid}/{pid}/snapshots/{sid}/manifest.json"
    raw = stor.read_object(mf_path)
    assert raw is not None
    assert sid.encode("utf-8") in raw
    hh = stor.read_object(f"{wid}/{pid}/head.json")
    assert hh is not None

    ss = stor.read_object(f"{wid}/{pid}/snapshots/{sid}/files/src/hello.txt")
    assert ss == b"world"


def test_emit_second_snapshot_nothing_to_change(tmp_path: Path) -> None:
    stor = DictSnapshotObjectStorage()
    managed_workspace_runtime().object_storage = stor
    set_project_snapshot_store_for_tests(MemoryProjectSnapshotStore())

    wid = "wsdemo"
    pid = "projlocal"
    work = _layout(tmp_path, wid, pid)

    common = PostExecCommon(
        project_id=pid,
        project_root=work,
        summary=None,
        change_id="corr-2",
        workspace_id=wid,
    )

    assert emit_managed_workspace_snapshot(common).build_outcome == "succeeded"
    out2 = emit_managed_workspace_snapshot(common)
    assert out2.build_outcome == "nothing_to_change"
    assert out2.target_ref.get("changed_paths_count") == 0


def test_decide_managed_build_status_via_neutral() -> None:
    from src.ham.droid_workflows.preview_launch import _decide_build_status  # noqa: PLC0415

    ok, _ = _decide_build_status(
        target="managed_workspace",
        ok_exec=True,
        timed_out=False,
        exit_code=0,
        build_outcome=None,
        build_err=None,
        output_ref={"neutral_outcome": "succeeded"},
    )
    assert ok

    bad, reason = _decide_build_status(
        target="managed_workspace",
        ok_exec=True,
        timed_out=False,
        exit_code=0,
        build_outcome=None,
        build_err="oops",
        output_ref={"neutral_outcome": "failed"},
    )
    assert bad is False
    assert reason is not None


def test_snapshot_api_reads_roundtrip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    stor = DictSnapshotObjectStorage()
    rt = managed_workspace_runtime()
    rt.object_storage = stor
    ss = MemoryProjectSnapshotStore()
    set_project_snapshot_store_for_tests(ss)

    proj_root = tmp_path / "projroot"
    proj_root.mkdir()
    rec = get_project_store().make_record(name="ApiSnap", root=str(proj_root.resolve()))
    get_project_store().register(rec)

    wid = "wsapi"
    work = _layout(tmp_path, wid, rec.id)
    common = PostExecCommon(
        project_id=rec.id,
        project_root=work,
        summary=None,
        change_id="c3",
        workspace_id=wid,
    )

    monkeypatch.setattr(
        "src.api.project_snapshots.managed_workspace_runtime",
        lambda: rt,
        raising=True,
    )
    monkeypatch.setattr(
        "src.api.project_snapshots.snapshot_object_storage_from_env",
        lambda: stor,
        raising=True,
    )
    monkeypatch.setattr(
        "src.api.project_snapshots.get_project_snapshot_store",
        lambda: ss,
        raising=True,
    )

    out = emit_managed_workspace_snapshot(common)
    sid = str(out.target_ref.get("snapshot_id") or "").strip()

    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: None
    cli = TestClient(fastapi_app)
    r = cli.get(f"/api/projects/{rec.id}/snapshots")
    fastapi_app.dependency_overrides.pop(get_ham_clerk_actor, None)
    assert r.status_code == 200
    rows = r.json()["snapshots"]
    assert any(x["snapshot_id"] == sid for x in rows)

    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: None
    m = cli.get(f"/api/projects/{rec.id}/snapshots/{sid}/manifest")
    assert m.status_code == 200
    f = cli.get(
        f"/api/projects/{rec.id}/snapshots/{sid}/file",
        params={"path": "src/hello.txt"},
    )
    assert f.status_code == 200
    assert f.content == b"world"
    fastapi_app.dependency_overrides.pop(get_ham_clerk_actor, None)


def test_snapshot_export_zip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    stor = DictSnapshotObjectStorage()
    rt = managed_workspace_runtime()
    rt.object_storage = stor
    ss = MemoryProjectSnapshotStore()
    set_project_snapshot_store_for_tests(ss)

    proj_root = tmp_path / "projroot2"
    proj_root.mkdir()
    rec = get_project_store().make_record(name="ZipSnap", root=str(proj_root.resolve()))
    get_project_store().register(rec)

    wid = "wszip"
    work = _layout(tmp_path, wid, rec.id)
    out = emit_managed_workspace_snapshot(
        PostExecCommon(
            project_id=rec.id,
            project_root=work,
            summary=None,
            change_id="z",
            workspace_id=wid,
        ),
    )
    sid = str(out.target_ref["snapshot_id"])

    monkeypatch.setattr("src.api.project_snapshots.managed_workspace_runtime", lambda: rt)
    monkeypatch.setattr("src.api.project_snapshots.snapshot_object_storage_from_env", lambda: stor)
    monkeypatch.setattr("src.api.project_snapshots.get_project_snapshot_store", lambda: ss)

    fastapi_app.dependency_overrides[get_ham_clerk_actor] = lambda: None
    cli = TestClient(fastapi_app)
    zr = cli.get(f"/api/projects/{rec.id}/export", params={"snapshot": sid})
    fastapi_app.dependency_overrides.pop(get_ham_clerk_actor, None)

    assert zr.status_code == 200
    zf = zipfile.ZipFile(BytesIO(zr.content))
    names = set(zf.namelist())
    assert "manifest.json" in names
    assert any(n.endswith("src/hello.txt") for n in names)
