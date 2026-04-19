from __future__ import annotations

import pytest

from src.registry.droids import DEFAULT_DROID_REGISTRY, DroidRecord, DroidRegistry


def test_default_registry_contains_builder_and_reviewer():
    assert DEFAULT_DROID_REGISTRY.ids() == ["droid.builder", "droid.reviewer"]


def test_droid_record_has_required_convention_fields():
    record = DEFAULT_DROID_REGISTRY.get("droid.builder")
    assert record.id == "droid.builder"
    assert record.version
    assert isinstance(record.metadata, dict)


def test_droid_record_has_identity_and_model_fields():
    record = DEFAULT_DROID_REGISTRY.get("droid.builder")
    assert record.name == "Builder"
    assert record.role
    assert record.description
    assert record.model
    assert record.provider
    assert record.backend_id


def test_reviewer_record_is_distinct_from_builder():
    builder = DEFAULT_DROID_REGISTRY.get("droid.builder")
    reviewer = DEFAULT_DROID_REGISTRY.get("droid.reviewer")
    assert builder.id != reviewer.id
    assert builder.name != reviewer.name
    assert builder.role != reviewer.role


def test_get_unknown_droid_raises_keyerror_with_clear_message():
    unknown_id = "droid.unknown"
    with pytest.raises(KeyError) as exc_info:
        DEFAULT_DROID_REGISTRY.get(unknown_id)
    assert unknown_id in str(exc_info.value)


def test_ids_returns_sorted_list():
    ids = DEFAULT_DROID_REGISTRY.ids()
    assert ids == sorted(ids)


def test_droid_record_round_trips_via_model_dump():
    record = DEFAULT_DROID_REGISTRY.get("droid.reviewer")
    dumped = record.model_dump()
    restored = DroidRecord.model_validate(dumped)
    assert restored.id == record.id
    assert restored.version == record.version
    assert restored.name == record.name
    assert restored.role == record.role
    assert restored.metadata == record.metadata


def test_custom_registry_get_and_ids():
    r = DroidRecord(id="droid.custom", name="Custom", role="Specialist")
    registry = DroidRegistry({"droid.custom": r})
    assert registry.ids() == ["droid.custom"]
    assert registry.get("droid.custom").id == "droid.custom"


def test_droid_record_metadata_defaults_to_empty_dict():
    record = DroidRecord(id="droid.test", name="Test", role="Tester")
    assert record.metadata == {}


def test_droid_record_has_no_custom_methods():
    from pydantic import BaseModel

    base_attrs = set(dir(BaseModel))
    extra = {
        name for name in dir(DroidRecord)
        if not name.startswith("_")
        and name not in base_attrs
        and callable(getattr(DroidRecord, name, None))
        and not isinstance(getattr(DroidRecord, name, None), property)
    }
    assert extra == set(), f"DroidRecord has unexpected custom methods: {extra}"
