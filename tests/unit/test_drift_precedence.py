"""ADR-0014 precedence-ordering tests.

`DRIFT_PRECEDENCE` is a v1 binding decision — every downstream feature
(F4 readiness, the UI's triage view, F7 risk scoring) reads from this
constant. Tests assert the exact ordering and that ``primary_of()``
resolves multi-drift devices deterministically.
"""

from __future__ import annotations

import pytest

from gard.core.drift_rules import (
    DRIFT_PRECEDENCE,
    precedence_index,
    primary_of,
    sort_by_precedence,
)


def test_precedence_is_the_adr_ordering() -> None:
    """ADR-0014 §C: catalog > rule > package > target > discovery > evidence > exception."""
    assert DRIFT_PRECEDENCE == (
        "catalog_drift",
        "rule_drift",
        "package_drift",
        "target_drift",
        "discovery_drift",
        "evidence_drift",
        "exception_drift",
    )


def test_precedence_index_is_zero_for_top() -> None:
    assert precedence_index("catalog_drift") == 0
    assert precedence_index("exception_drift") == len(DRIFT_PRECEDENCE) - 1


def test_primary_of_empty_set_is_none() -> None:
    assert primary_of([]) is None


def test_primary_of_single_drift_returns_it() -> None:
    assert primary_of(["target_drift"]) == "target_drift"


def test_primary_of_multi_drift_picks_highest_precedence() -> None:
    # All four "upstream" drifts: catalog wins.
    assert (
        primary_of(["target_drift", "rule_drift", "package_drift", "catalog_drift"])
        == "catalog_drift"
    )
    # No catalog, rule wins.
    assert primary_of(["target_drift", "rule_drift", "package_drift"]) == "rule_drift"
    # Only downstream symptoms: target wins over discovery + evidence.
    assert primary_of(["evidence_drift", "discovery_drift", "target_drift"]) == "target_drift"


def test_primary_of_rejects_unknown_drift_type() -> None:
    with pytest.raises(ValueError, match="unknown drift type"):
        primary_of(["target_drift", "made_up_drift"])  # type: ignore[list-item]


def test_sort_is_stable_and_precedence_ordered() -> None:
    out = sort_by_precedence(["discovery_drift", "catalog_drift", "package_drift"])
    assert out == ["catalog_drift", "package_drift", "discovery_drift"]


def test_sort_handles_duplicates_idempotently() -> None:
    out = sort_by_precedence(["target_drift", "target_drift", "rule_drift"])
    assert out == ["rule_drift", "target_drift", "target_drift"]
