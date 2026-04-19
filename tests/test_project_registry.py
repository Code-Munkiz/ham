from __future__ import annotations

import inspect

from pydantic import BaseModel

from src.registry.projects import ProjectRecord


def test_project_record_is_pydantic_model():
    assert issubclass(ProjectRecord, BaseModel)


def test_project_record_required_fields():
    r = ProjectRecord(id="project.foo-abc123", name="Foo", root="/tmp/foo")
    assert r.id == "project.foo-abc123"
    assert r.name == "Foo"
    assert r.root == "/tmp/foo"


def test_project_record_defaults():
    r = ProjectRecord(id="project.foo-abc123", name="Foo", root="/tmp/foo")
    assert r.version == "1.0.0"
    assert r.description == ""
    assert r.metadata == {}


def test_project_record_accepts_description_and_metadata():
    r = ProjectRecord(
        id="project.foo-abc123",
        name="Foo",
        root="/tmp/foo",
        description="A test project",
        metadata={"team": "core"},
    )
    assert r.description == "A test project"
    assert r.metadata["team"] == "core"


def test_project_record_metadata_is_independent():
    r1 = ProjectRecord(id="p1", name="A", root="/a")
    r2 = ProjectRecord(id="p2", name="B", root="/b")
    r1.metadata["x"] = 1
    assert "x" not in r2.metadata


def test_project_record_model_dump_roundtrip():
    r = ProjectRecord(
        id="project.foo-abc123",
        name="Foo",
        root="/tmp/foo",
        description="desc",
        metadata={"k": "v"},
    )
    d = r.model_dump()
    r2 = ProjectRecord.model_validate(d)
    assert r2 == r


def test_project_record_has_no_custom_methods():
    base_names = set(dir(BaseModel))
    custom = [
        name
        for name in dir(ProjectRecord)
        if not name.startswith("_") and name not in base_names
        and inspect.isfunction(getattr(ProjectRecord, name, None))
    ]
    assert custom == [], f"Unexpected custom methods: {custom}"
