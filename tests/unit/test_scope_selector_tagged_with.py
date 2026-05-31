"""Unit tests for scope_selector ``tagged_with`` (F7)."""

from __future__ import annotations

from gard.core import scope_selector as sel


def test_tagged_with_deferred_when_tags_unknown() -> None:
    result = sel.evaluate(
        {"tagged_with": ["edge"]},
        {"tags": None, "platform_family": "ios"},
    )
    assert result.matched is False
    assert result.deferred_keys == frozenset({"tagged_with"})


def test_tagged_with_matches_when_all_present() -> None:
    result = sel.evaluate(
        {"tagged_with": ["edge", "lab"]},
        {"tags": ["edge", "lab", "extra"]},
    )
    assert result.matched is True
    assert result.deferred_keys == frozenset()


def test_tagged_with_fails_when_tag_missing() -> None:
    result = sel.evaluate(
        {"tagged_with": ["edge"]},
        {"tags": ["lab"]},
    )
    assert result.matched is False
    assert result.deferred_keys == frozenset()
