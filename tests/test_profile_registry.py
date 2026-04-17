from __future__ import annotations

import pytest

from src.registry.profiles import DEFAULT_PROFILE_REGISTRY, KeywordSelector


def test_default_registry_contains_expected_profile_ids():
    assert DEFAULT_PROFILE_REGISTRY.ids() == ["inspect.cwd", "inspect.git_diff", "inspect.git_status"]


def test_each_profile_has_id_version_argv_metadata():
    for profile_id in DEFAULT_PROFILE_REGISTRY.ids():
        profile = DEFAULT_PROFILE_REGISTRY.get(profile_id)
        assert profile.id
        assert profile.version
        assert isinstance(profile.argv, list)
        assert profile.argv
        assert isinstance(profile.metadata, dict)


def test_registry_get_unknown_id_raises_keyerror_with_clear_message():
    unknown_id = "inspect.unknown"
    with pytest.raises(KeyError) as exc_info:
        DEFAULT_PROFILE_REGISTRY.get(unknown_id)
    assert unknown_id in str(exc_info.value)


def test_keyword_selector_routes_status_diff_and_fallback():
    selector = KeywordSelector()
    assert selector.select("show status") == "inspect.git_status"
    assert selector.select("show me diff") == "inspect.git_diff"
    assert selector.select("hello") == "inspect.cwd"


def test_keyword_selector_precedence_status_before_diff():
    selector = KeywordSelector()
    assert selector.select("diff against status") == "inspect.git_status"


def test_keyword_selector_word_boundary_no_substring_match():
    selector = KeywordSelector()
    assert selector.select("different") == "inspect.cwd"
    assert selector.select("difficult") == "inspect.cwd"
