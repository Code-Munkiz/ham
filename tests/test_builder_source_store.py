from __future__ import annotations

from pathlib import Path

from src.persistence.builder_source_store import (
    BuilderSourceStore,
    ImportJob,
    ProjectSource,
    SourceSnapshot,
)


def test_store_lists_empty_arrays_by_default(tmp_path: Path) -> None:
    store = BuilderSourceStore(store_path=tmp_path / "builder_sources.json")
    assert store.list_project_sources(workspace_id="ws_a", project_id="project.a") == []
    assert store.list_source_snapshots(workspace_id="ws_a", project_id="project.a") == []
    assert store.list_import_jobs(workspace_id="ws_a", project_id="project.a") == []


def test_store_filters_by_workspace_and_project_and_orders_desc(tmp_path: Path) -> None:
    store = BuilderSourceStore(store_path=tmp_path / "builder_sources.json")

    store.upsert_project_source(
        ProjectSource(
            id="psrc_11111111111111111111111111111111",
            workspace_id="ws_a",
            project_id="project.a",
            display_name="older",
            created_at="2026-05-11T01:00:00Z",
            updated_at="2026-05-11T01:00:00Z",
        )
    )
    store.upsert_project_source(
        ProjectSource(
            id="psrc_22222222222222222222222222222222",
            workspace_id="ws_a",
            project_id="project.a",
            display_name="newer",
            created_at="2026-05-11T02:00:00Z",
            updated_at="2026-05-11T02:00:00Z",
        )
    )
    store.upsert_project_source(
        ProjectSource(
            id="psrc_33333333333333333333333333333333",
            workspace_id="ws_b",
            project_id="project.b",
            display_name="other",
        )
    )
    got = store.list_project_sources(workspace_id="ws_a", project_id="project.a")
    assert [row.id for row in got] == [
        "psrc_22222222222222222222222222222222",
        "psrc_11111111111111111111111111111111",
    ]

    store.upsert_source_snapshot(
        SourceSnapshot(
            id="ssnp_11111111111111111111111111111111",
            workspace_id="ws_a",
            project_id="project.a",
            project_source_id="psrc_11111111111111111111111111111111",
            created_at="2026-05-11T01:00:00Z",
        )
    )
    store.upsert_source_snapshot(
        SourceSnapshot(
            id="ssnp_22222222222222222222222222222222",
            workspace_id="ws_a",
            project_id="project.a",
            project_source_id="psrc_22222222222222222222222222222222",
            created_at="2026-05-11T02:00:00Z",
        )
    )
    snapshots = store.list_source_snapshots(workspace_id="ws_a", project_id="project.a")
    assert [row.id for row in snapshots] == [
        "ssnp_22222222222222222222222222222222",
        "ssnp_11111111111111111111111111111111",
    ]

    store.upsert_import_job(
        ImportJob(
            id="ijob_11111111111111111111111111111111",
            workspace_id="ws_a",
            project_id="project.a",
            updated_at="2026-05-11T01:00:00Z",
        )
    )
    store.upsert_import_job(
        ImportJob(
            id="ijob_22222222222222222222222222222222",
            workspace_id="ws_a",
            project_id="project.a",
            updated_at="2026-05-11T02:00:00Z",
        )
    )
    jobs = store.list_import_jobs(workspace_id="ws_a", project_id="project.a")
    assert [row.id for row in jobs] == [
        "ijob_22222222222222222222222222222222",
        "ijob_11111111111111111111111111111111",
    ]
