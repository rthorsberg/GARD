"""Unit tests for ADR-0015 R-1 blocker precedence ordering."""

from __future__ import annotations

import uuid

import pytest

from gard.core import prereq_predicates
from gard.core.envelope import Blocker, BlockerPredicateKind


def _b(
    kind: BlockerPredicateKind,
    severity: str = "required",
    rule_id: str | None = None,
) -> Blocker:
    return Blocker(
        rule_id=rule_id,
        rule_name=None,
        predicate_kind=kind,
        severity=severity,  # type: ignore[arg-type]
        required=None,
        observed=None,
        detail="-",
    )


def test_canonical_order_matches_adr_0015() -> None:
    """ADR-0015 §B lists the canonical order verbatim; this test is the lock."""
    assert prereq_predicates.BLOCKER_PREDICATE_ORDER == (
        "min_ram_mb",
        "min_disk_mb",
        "hardware_revision_in",
        "min_current_version",
        "intermediate_version_required",
        "missing_upgrade_path",
        "license_present",
        "not_in_state",
        "region_in",
        "missing_observation_field",
        "tagged_with",
    )


def test_required_severity_outranks_recommended_for_same_kind() -> None:
    rid = str(uuid.uuid4())
    a = _b("min_ram_mb", "recommended", rule_id=rid)
    b = _b("min_ram_mb", "required", rule_id=str(uuid.uuid4()))
    primary = prereq_predicates.primary_blocker_of([a, b])
    assert primary is b


def test_hardware_outranks_chain_when_both_required() -> None:
    chain = _b("missing_upgrade_path", "required", rule_id=None)
    hw = _b("min_ram_mb", "required", rule_id=str(uuid.uuid4()))
    primary = prereq_predicates.primary_blocker_of([chain, hw])
    assert primary is hw


def test_missing_observation_field_late_in_order() -> None:
    """Even at `required` severity, missing_observation_field sorts after
    real prereq blockers — operators see real problems first."""
    a = _b("min_ram_mb", "required", rule_id=str(uuid.uuid4()))
    b = _b("missing_observation_field", "required", rule_id=str(uuid.uuid4()))
    primary = prereq_predicates.primary_blocker_of([a, b])
    assert primary.predicate_kind == "min_ram_mb"


def test_tagged_with_last() -> None:
    a = _b("region_in", "required", rule_id=str(uuid.uuid4()))
    b = _b("tagged_with", "recommended", rule_id=str(uuid.uuid4()))
    primary = prereq_predicates.primary_blocker_of([a, b])
    assert primary.predicate_kind == "region_in"


def test_synthetic_blockers_sort_before_rule_blockers_within_kind() -> None:
    synthetic = _b("min_ram_mb", "required", rule_id=None)
    rule = _b("min_ram_mb", "required", rule_id="z-some-uuid")
    primary = prereq_predicates.primary_blocker_of([rule, synthetic])
    # rule_id="" (synthetic) sorts before "z-some-uuid"
    assert primary is synthetic


def test_primary_of_empty_returns_none() -> None:
    assert prereq_predicates.primary_blocker_of([]) is None


def test_sort_is_stable_across_invocations() -> None:
    rid1 = "00000000-0000-0000-0000-000000000001"
    rid2 = "00000000-0000-0000-0000-000000000002"
    blockers = [
        _b("license_present", "required", rule_id=rid2),
        _b("min_ram_mb", "required", rule_id=rid1),
        _b("missing_upgrade_path", "required", rule_id=None),
    ]
    first = prereq_predicates.sort_blockers(blockers)
    second = prereq_predicates.sort_blockers(blockers)
    assert [b.predicate_kind for b in first] == [b.predicate_kind for b in second]
    assert [b.predicate_kind for b in first] == [
        "min_ram_mb",
        "missing_upgrade_path",
        "license_present",
    ]


def test_predicate_index_covers_all_kinds() -> None:
    """No BlockerPredicateKind value is missing from the order tuple."""
    # The Literal type itself isn't iterable, but exhaustiveness is
    # captured by asserting count + uniqueness:
    assert len(prereq_predicates.BLOCKER_PREDICATE_ORDER) == 11
    assert len(set(prereq_predicates.BLOCKER_PREDICATE_ORDER)) == 11
    # And every kind in the dispatch table is in the order tuple:
    for kind in prereq_predicates.PREDICATE_DISPATCH:
        assert kind in prereq_predicates.BLOCKER_PREDICATE_ORDER
