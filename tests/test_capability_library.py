"""Capability library: store, ref validation, and API (Phase 1)."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.ham.capability_library.schema import CapabilityLibraryIndex, LibraryEntry
from src.ham.capability_library.store import (
    read_capability_library,
    remove_entry,
    revision_for_index,
    save_entry,
)


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def _register_project(client: TestClient, *, name: str, root: Path) -> str:
    res = client.post(
        "/api/projects",
        json={"name": name, "root": str(root), "description": ""},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_revision_for_empty_index() -> None:
    rev = revision_for_index(CapabilityLibraryIndex())
    assert len(rev) == 64
    assert rev == revision_for_index(CapabilityLibraryIndex())


def test_save_round_trip_hermes_ref(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    base, rev0 = read_capability_library(root)
    assert base.entries == []
    ref = "hermes:bundled.dogfood"
    r1 = save_entry(root, ref=ref, notes="n", expect_revision=rev0)
    assert r1.new_revision != rev0
    loaded, rev1 = read_capability_library(root)
    assert rev1 == r1.new_revision
    assert len(loaded.entries) == 1
    assert loaded.entries[0].ref == ref
    p = root / ".ham" / "capability-library" / "v1" / "index.json"
    assert p.is_file()
    ad = root / ".ham" / "_audit" / "capability-library"
    assert ad.is_dir()
    assert any(ad.glob("*.jsonl"))


def test_save_rejects_unknown_hermes_id(tmp_path: Path) -> None:
    root = tmp_path / "p"
    root.mkdir()
    _, rev0 = read_capability_library(root)
    with pytest.raises(ValueError, match="unknown Hermes"):
        save_entry(root, ref="hermes:definitely.missing.xxx", notes="", expect_revision=rev0)


def test_conflict_on_stale_revision(tmp_path: Path) -> None:
    from src.ham.capability_library.store import CapabilityLibraryWriteConflictError

    root = tmp_path / "p"
    root.mkdir()
    _, rev0 = read_capability_library(root)
    ref = "hermes:bundled.dogfood"
    save_entry(root, ref=ref, notes="a", expect_revision=rev0)
    with pytest.raises(CapabilityLibraryWriteConflictError):
        save_entry(root, ref=ref, notes="b", expect_revision=rev0)


def test_concurrent_saves_one_wins(
    tmp_path: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAM_CAPABILITY_LIBRARY_WRITE_TOKEN", "tok")
    client = TestClient(app)
    root = tmp_path / "proj"
    root.mkdir()
    pid = _register_project(client, name="cl", root=root)
    st = client.get("/api/capability-library/library", params={"project_id": pid})
    assert st.status_code == 200, st.text
    base_rev = st.json()["revision"]
    ref = "hermes:bundled.dogfood"
    err: list[str] = []

    def do_save() -> None:
        r = client.post(
            f"/api/capability-library/save?project_id={pid}",
            headers={"Authorization": "Bearer tok"},
            json={"ref": ref, "notes": "", "base_revision": base_rev},
        )
        if r.status_code not in (200, 409):
            err.append(r.text)

    t1 = threading.Thread(target=do_save)
    t2 = threading.Thread(target=do_save)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert not err
    fin = client.get("/api/capability-library/library", params={"project_id": pid})
    assert fin.status_code == 200
    # Exactly one 200 and one 409, or two sequential successes if serialized — at least one entry
    data = fin.json()
    assert len(data["entries"]) == 1


def test_malformed_ref_rejected() -> None:
    from src.ham.capability_library.schema import LibraryEntry
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        LibraryEntry(ref="hermes:../etc", notes="")


def test_api_reads_and_writes(
    tmp_path: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAM_CAPABILITY_LIBRARY_WRITE_TOKEN", "test-lib-token")
    client = TestClient(app)
    root = tmp_path / "proj2"
    root.mkdir()
    pid = _register_project(client, name="papi", root=root)

    ws = client.get("/api/capability-library/write-status")
    assert ws.status_code == 200
    assert ws.json()["writes_enabled"] is True

    g0 = client.get("/api/capability-library/library", params={"project_id": pid})
    assert g0.status_code == 200
    rev = g0.json()["revision"]

    bad = client.post(
        f"/api/capability-library/save?project_id={pid}",
        json={"ref": "hermes:bundled.dogfood", "notes": "", "base_revision": rev},
    )
    assert bad.status_code == 401

    ok = client.post(
        f"/api/capability-library/save?project_id={pid}",
        headers={"Authorization": "Bearer test-lib-token"},
        json={"ref": "hermes:bundled.dogfood", "notes": "x", "base_revision": rev},
    )
    assert ok.status_code == 200, ok.text
    new_rev = ok.json()["new_revision"]
    assert new_rev != rev

    agg = client.get("/api/capability-library/aggregate", params={"project_id": pid})
    assert agg.status_code == 200, agg.text
    body = agg.json()
    assert body["kind"] == "ham_capability_library_aggregate"
    assert len(body["items"]) == 1
    assert body["items"][0]["ref"] == "hermes:bundled.dogfood"
    assert body["items"][0]["in_library"] is True

    rem = client.post(
        f"/api/capability-library/remove?project_id={pid}",
        headers={"Authorization": "Bearer test-lib-token"},
        json={"ref": "hermes:bundled.dogfood", "base_revision": new_rev},
    )
    assert rem.status_code == 200, rem.text
    g1 = client.get("/api/capability-library/library", params={"project_id": pid})
    assert g1.json()["entries"] == []


def test_reorder(
    tmp_path: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HAM_CAPABILITY_LIBRARY_WRITE_TOKEN", "tok2")
    client = TestClient(app)
    root = tmp_path / "proj3"
    root.mkdir()
    pid = _register_project(client, name="pr", root=root)
    r0 = client.get("/api/capability-library/library", params={"project_id": pid}).json()["revision"]
    a = "hermes:bundled.dogfood"
    b = "hermes:community.example.v1"  # may not exist - pick second real from catalog
    from src.ham.hermes_skills_catalog import list_catalog_entries

    ids = [e["catalog_id"] for e in list_catalog_entries() if e.get("catalog_id")][:2]
    assert len(ids) >= 2, "catalog needs 2 entries"
    a = f"hermes:{ids[0]}"
    b = f"hermes:{ids[1]}"
    r1 = client.post(
        f"/api/capability-library/save?project_id={pid}",
        headers={"Authorization": "Bearer tok2"},
        json={"ref": a, "notes": "", "base_revision": r0},
    ).json()["new_revision"]
    r2 = client.post(
        f"/api/capability-library/save?project_id={pid}",
        headers={"Authorization": "Bearer tok2"},
        json={"ref": b, "notes": "", "base_revision": r1},
    ).json()["new_revision"]
    ro = client.post(
        f"/api/capability-library/reorder?project_id={pid}",
        headers={"Authorization": "Bearer tok2"},
        json={"order": [b, a], "base_revision": r2},
    )
    assert ro.status_code == 200, ro.text
    lib = client.get("/api/capability-library/library", params={"project_id": pid})
    ords = [e["user_order"] for e in lib.json()["entries"]]
    assert ords == [0, 1]
    refs = [e["ref"] for e in lib.json()["entries"]]
    assert refs == [b, a]
