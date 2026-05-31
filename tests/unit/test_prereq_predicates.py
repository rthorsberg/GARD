"""Truth-table tests for each F4 prerequisite predicate.

Pure-function tests — no DB. Each predicate gets one positive (rule
fires → Blocker) and one negative (rule passes → None) plus the
missing-input case for predicates that read observation/device fields
(emits a synthetic `missing_observation_field` blocker per Constitution III).
"""

from __future__ import annotations

import datetime as dt
import uuid
from types import SimpleNamespace
from typing import Any

from gard.core import prereq_predicates
from gard.models._enums import LifecycleState


def _rule(
    *,
    name: str,
    predicate_kind: str,
    predicate_args: dict[str, Any],
    severity: str = "required",
) -> SimpleNamespace:
    """Cheap stand-in for a FirmwarePrerequisiteRule row."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        predicate_kind=predicate_kind,
        predicate_args=predicate_args,
        severity=severity,
        applies_to={},
        evaluable=True,
        removed_at=None,
    )


def _device(**overrides: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "id": uuid.uuid4(),
        "hostname": "r1.oslo",
        "site": "oslo",
        "region": "oslo",
        "role": "edge",
        "vendor_normalized": "cisco",
        "platform_family": "iosxr",
        "hardware_revision": "rev-b",
        "ram_mb": 2048,
        "disk_mb": 8192,
        "licenses": ["base"],
        "lifecycle_state": LifecycleState.outside_target,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _obs(observed_firmware: str | None = "7.5.2") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        observed_firmware=observed_firmware,
        observed_at=dt.datetime.now(dt.UTC),
    )


# ---- min_ram_mb ----------------------------------------------------------


def test_min_ram_mb_fires_when_below() -> None:
    rule = _rule(name="iosxr-ram", predicate_kind="min_ram_mb",
                 predicate_args={"min_mb": 4096})
    dev = _device(ram_mb=2048)
    b = prereq_predicates.eval_min_ram_mb(rule, dev, _obs())
    assert b is not None
    assert b.predicate_kind == "min_ram_mb"
    assert b.required == {"min_mb": 4096}
    assert b.observed == {"ram_mb": 2048}
    assert b.severity == "required"


def test_min_ram_mb_silent_when_meets() -> None:
    rule = _rule(name="iosxr-ram", predicate_kind="min_ram_mb",
                 predicate_args={"min_mb": 1024})
    dev = _device(ram_mb=2048)
    assert prereq_predicates.eval_min_ram_mb(rule, dev, _obs()) is None


def test_min_ram_mb_missing_input_surfaces_synthetic_blocker() -> None:
    rule = _rule(name="iosxr-ram", predicate_kind="min_ram_mb",
                 predicate_args={"min_mb": 4096})
    dev = _device(ram_mb=None)
    b = prereq_predicates.eval_min_ram_mb(rule, dev, _obs())
    assert b is not None
    assert b.predicate_kind == "missing_observation_field"
    assert b.severity == "required"
    assert b.required == {"field": "ram_mb"}


# ---- min_disk_mb ---------------------------------------------------------


def test_min_disk_mb_fires_when_below() -> None:
    rule = _rule(name="d", predicate_kind="min_disk_mb",
                 predicate_args={"min_mb": 16384})
    dev = _device(disk_mb=8192)
    b = prereq_predicates.eval_min_disk_mb(rule, dev, _obs())
    assert b is not None
    assert b.predicate_kind == "min_disk_mb"


def test_min_disk_mb_silent_when_meets() -> None:
    rule = _rule(name="d", predicate_kind="min_disk_mb",
                 predicate_args={"min_mb": 1024})
    assert prereq_predicates.eval_min_disk_mb(rule, _device(), _obs()) is None


# ---- min_current_version -------------------------------------------------


def test_min_current_version_fires_when_below() -> None:
    rule = _rule(name="mv", predicate_kind="min_current_version",
                 predicate_args={"min_version": "7.6.0"})
    b = prereq_predicates.eval_min_current_version(
        rule, _device(), _obs(observed_firmware="7.5.2")
    )
    assert b is not None
    assert b.predicate_kind == "min_current_version"
    assert b.observed == {"observed_firmware": "7.5.2"}


def test_min_current_version_silent_when_meets() -> None:
    rule = _rule(name="mv", predicate_kind="min_current_version",
                 predicate_args={"min_version": "7.0.0"})
    b = prereq_predicates.eval_min_current_version(
        rule, _device(), _obs(observed_firmware="7.5.2")
    )
    assert b is None


def test_min_current_version_missing_observation_field() -> None:
    rule = _rule(name="mv", predicate_kind="min_current_version",
                 predicate_args={"min_version": "7.0.0"})
    b = prereq_predicates.eval_min_current_version(
        rule, _device(), _obs(observed_firmware=None)
    )
    assert b is not None
    assert b.predicate_kind == "missing_observation_field"


# ---- hardware_revision_in ------------------------------------------------


def test_hardware_revision_in_fires_when_not_in_set() -> None:
    rule = _rule(name="hw", predicate_kind="hardware_revision_in",
                 predicate_args={"revisions": ["rev-a", "rev-c"]})
    b = prereq_predicates.eval_hardware_revision_in(
        rule, _device(hardware_revision="rev-b"), _obs()
    )
    assert b is not None
    assert b.predicate_kind == "hardware_revision_in"


def test_hardware_revision_in_silent_when_in_set() -> None:
    rule = _rule(name="hw", predicate_kind="hardware_revision_in",
                 predicate_args={"revisions": ["rev-a", "rev-b"]})
    b = prereq_predicates.eval_hardware_revision_in(
        rule, _device(hardware_revision="rev-b"), _obs()
    )
    assert b is None


# ---- license_present -----------------------------------------------------


def test_license_present_fires_when_missing() -> None:
    rule = _rule(name="lic", predicate_kind="license_present",
                 predicate_args={"license": "advantage"})
    b = prereq_predicates.eval_license_present(rule, _device(licenses=["base"]), _obs())
    assert b is not None
    assert b.predicate_kind == "license_present"


def test_license_present_silent_when_present() -> None:
    rule = _rule(name="lic", predicate_kind="license_present",
                 predicate_args={"license": "base"})
    b = prereq_predicates.eval_license_present(rule, _device(licenses=["base"]), _obs())
    assert b is None


# ---- intermediate_version_required (always emits, recommended sev) ------


def test_intermediate_version_required_emits_recommended() -> None:
    rule = _rule(name="iv", predicate_kind="intermediate_version_required",
                 predicate_args={"via_version": "7.7.1"})
    b = prereq_predicates.eval_intermediate_version_required(
        rule, _device(), _obs(observed_firmware="7.5.2")
    )
    assert b is not None
    assert b.severity == "recommended"


# ---- not_in_state --------------------------------------------------------


def test_not_in_state_fires_when_in_forbidden() -> None:
    rule = _rule(name="nis", predicate_kind="not_in_state",
                 predicate_args={"states": ["uplift_planned", "approved"]})
    dev = _device(lifecycle_state=LifecycleState.uplift_planned)
    b = prereq_predicates.eval_not_in_state(rule, dev, _obs())
    assert b is not None
    assert b.predicate_kind == "not_in_state"


def test_not_in_state_silent_when_not_in_forbidden() -> None:
    rule = _rule(name="nis", predicate_kind="not_in_state",
                 predicate_args={"states": ["uplift_planned"]})
    dev = _device(lifecycle_state=LifecycleState.outside_target)
    assert prereq_predicates.eval_not_in_state(rule, dev, _obs()) is None


# ---- region_in -----------------------------------------------------------


def test_region_in_fires_when_not_in_set() -> None:
    rule = _rule(name="ri", predicate_kind="region_in",
                 predicate_args={"regions": ["bergen", "trondheim"]})
    b = prereq_predicates.eval_region_in(rule, _device(region="oslo"), _obs())
    assert b is not None
    assert b.predicate_kind == "region_in"


def test_region_in_silent_when_in_set() -> None:
    rule = _rule(name="ri", predicate_kind="region_in",
                 predicate_args={"regions": ["oslo", "bergen"]})
    assert prereq_predicates.eval_region_in(rule, _device(region="oslo"), _obs()) is None


# ---- tagged_with (deferred — always recommended) -------------------------


def test_tagged_with_emits_recommended_advisory() -> None:
    rule = _rule(name="tw", predicate_kind="tagged_with",
                 predicate_args={"tags": ["pre-uplift-review"]})
    b = prereq_predicates.eval_tagged_with(rule, _device(), _obs())
    assert b is not None
    assert b.severity == "recommended"
    assert b.predicate_kind == "tagged_with"


# ---- closed-dispatch invariant -------------------------------------------


def test_evaluate_rule_dispatches_to_correct_predicate() -> None:
    rule = _rule(name="r", predicate_kind="min_ram_mb",
                 predicate_args={"min_mb": 4096})
    dev = _device(ram_mb=1024)
    b = prereq_predicates.evaluate_rule(rule, dev, _obs())
    assert b is not None
    assert b.predicate_kind == "min_ram_mb"


def test_evaluate_rule_unknown_kind_raises() -> None:
    rule = _rule(name="r", predicate_kind="bogus_predicate",
                 predicate_args={})
    import pytest
    with pytest.raises(KeyError):
        prereq_predicates.evaluate_rule(rule, _device(), _obs())
