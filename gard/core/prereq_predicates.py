"""F4 prerequisite predicate evaluators (one pure function per `predicate_kind`).

Each function takes a :class:`FirmwarePrerequisiteRule`, a :class:`Device`,
and an optional :class:`DeviceObservation` and returns either a
:class:`Blocker` (the rule fired) or ``None`` (the rule passed / doesn't
apply).

These functions are deliberately *pure* — no DB access, no logging, no
audit. The controller owns IO; this module owns predicate logic. That
separation lets the unit-test suite drive every predicate from constructed
inputs without spinning up the catalogue (tests/unit/test_prereq_predicates.py).

Closed-dispatch invariant (Constitution III): an unknown ``predicate_kind``
raises ``KeyError`` from :data:`PREDICATE_DISPATCH` rather than silently
passing. F2 loader validates predicate_kind against its own enum, but the
catch here is defence-in-depth.

The R-1 ordering (ADR-0015 §B) is captured in :data:`BLOCKER_PREDICATE_ORDER`.
:func:`primary_blocker_of` returns ``blockers[0]`` after sorting.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from gard.core.envelope import (
    Blocker,
    BlockerPredicateKind,
    BlockerSeverity,
)
from gard.models import Device, DeviceObservation, FirmwarePrerequisiteRule

# Canonical ordering per ADR-0015 §B. Lower index = higher priority when
# severity ties (i.e. shown first; surfaced as the primary blocker).
BLOCKER_PREDICATE_ORDER: tuple[BlockerPredicateKind, ...] = (
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

_PREDICATE_INDEX: dict[BlockerPredicateKind, int] = {
    k: i for i, k in enumerate(BLOCKER_PREDICATE_ORDER)
}


def predicate_index(kind: BlockerPredicateKind) -> int:
    """Where this predicate sits in :data:`BLOCKER_PREDICATE_ORDER`."""
    return _PREDICATE_INDEX[kind]


def _severity_of(rule: FirmwarePrerequisiteRule) -> BlockerSeverity:
    """Translate F2's `severity` column into our literal type.

    F2 stores `required` | `recommended` as plain strings; we narrow the
    return type so the rest of F4 can rely on the closed enum.
    """
    sev = rule.severity
    if sev == "recommended":
        return "recommended"
    return "required"


def _blocker(
    rule: FirmwarePrerequisiteRule,
    kind: BlockerPredicateKind,
    *,
    required: dict[str, Any] | None,
    observed: dict[str, Any] | None,
    detail: str,
    severity_override: BlockerSeverity | None = None,
) -> Blocker:
    """Construct a Blocker citing the F2 rule."""
    return Blocker(
        rule_id=str(rule.id),
        rule_name=rule.name,
        predicate_kind=kind,
        severity=severity_override or _severity_of(rule),
        required=required,
        observed=observed,
        detail=detail,
    )


# ---- individual predicates ------------------------------------------------
#
# Each returns Blocker if it fires, None otherwise. Predicates that need an
# observation accept it as an argument (the controller pre-resolves the
# latest observation per device); predicates that read device facts (ram,
# disk, hardware, licenses, lifecycle, region) don't need the observation.
#
# Convention: when the predicate's required input is missing from the
# device row, we emit a synthetic `missing_observation_field` blocker
# (severity_override=required) rather than coercing the absent value to
# zero / empty (Constitution III).


def eval_min_ram_mb(
    rule: FirmwarePrerequisiteRule,
    device: Device,
    observation: DeviceObservation | None,
) -> Blocker | None:
    required_mb = int(rule.predicate_args.get("min_mb", 0))
    if device.ram_mb is None:
        return _blocker(
            rule,
            "missing_observation_field",
            required={"field": "ram_mb"},
            observed={"ram_mb": None},
            detail=(
                f"rule {rule.name!r} requires ram_mb >= {required_mb} "
                f"but device row has no ram_mb value"
            ),
            severity_override="required",
        )
    if device.ram_mb < required_mb:
        return _blocker(
            rule,
            "min_ram_mb",
            required={"min_mb": required_mb},
            observed={"ram_mb": device.ram_mb},
            detail=(
                f"device has {device.ram_mb} MB RAM; rule {rule.name!r} "
                f"requires >= {required_mb} MB"
            ),
        )
    return None


def eval_min_disk_mb(
    rule: FirmwarePrerequisiteRule,
    device: Device,
    observation: DeviceObservation | None,
) -> Blocker | None:
    required_mb = int(rule.predicate_args.get("min_mb", 0))
    if device.disk_mb is None:
        return _blocker(
            rule,
            "missing_observation_field",
            required={"field": "disk_mb"},
            observed={"disk_mb": None},
            detail=(
                f"rule {rule.name!r} requires disk_mb >= {required_mb} "
                f"but device row has no disk_mb value"
            ),
            severity_override="required",
        )
    if device.disk_mb < required_mb:
        return _blocker(
            rule,
            "min_disk_mb",
            required={"min_mb": required_mb},
            observed={"disk_mb": device.disk_mb},
            detail=(
                f"device has {device.disk_mb} MB disk; rule {rule.name!r} "
                f"requires >= {required_mb} MB"
            ),
        )
    return None


def eval_min_current_version(
    rule: FirmwarePrerequisiteRule,
    device: Device,
    observation: DeviceObservation | None,
) -> Blocker | None:
    required_version = str(rule.predicate_args.get("min_version", ""))
    observed = observation.observed_firmware if observation is not None else None
    if observed is None:
        return _blocker(
            rule,
            "missing_observation_field",
            required={"field": "observed_firmware"},
            observed={"observed_firmware": None},
            detail=(
                f"rule {rule.name!r} requires min_current_version "
                f">= {required_version!r} but no observation carries "
                f"observed_firmware"
            ),
            severity_override="required",
        )
    # v1 string comparison; semver-aware comparison is a v2 concern.
    if observed < required_version:
        return _blocker(
            rule,
            "min_current_version",
            required={"min_version": required_version},
            observed={"observed_firmware": observed},
            detail=(f"observed_firmware={observed!r} < required min_version={required_version!r}"),
        )
    return None


def eval_hardware_revision_in(
    rule: FirmwarePrerequisiteRule,
    device: Device,
    observation: DeviceObservation | None,
) -> Blocker | None:
    allowed = list(rule.predicate_args.get("revisions", []))
    if device.hardware_revision is None:
        return _blocker(
            rule,
            "missing_observation_field",
            required={"field": "hardware_revision"},
            observed={"hardware_revision": None},
            detail=(
                f"rule {rule.name!r} requires hardware_revision in "
                f"{allowed} but device row has no hardware_revision"
            ),
            severity_override="required",
        )
    if device.hardware_revision not in allowed:
        return _blocker(
            rule,
            "hardware_revision_in",
            required={"revisions": allowed},
            observed={"hardware_revision": device.hardware_revision},
            detail=(
                f"device hardware_revision={device.hardware_revision!r} "
                f"is not in the allowed set {allowed}"
            ),
        )
    return None


def eval_license_present(
    rule: FirmwarePrerequisiteRule,
    device: Device,
    observation: DeviceObservation | None,
) -> Blocker | None:
    needed = str(rule.predicate_args.get("license", ""))
    if device.licenses is None:
        return _blocker(
            rule,
            "missing_observation_field",
            required={"field": "licenses"},
            observed={"licenses": None},
            detail=(
                f"rule {rule.name!r} requires license={needed!r} but "
                f"device row has no licenses value"
            ),
            severity_override="required",
        )
    if needed not in device.licenses:
        return _blocker(
            rule,
            "license_present",
            required={"license": needed},
            observed={"licenses": list(device.licenses)},
            detail=(
                f"device does not carry license {needed!r}; observed "
                f"licenses={list(device.licenses)}"
            ),
        )
    return None


def eval_intermediate_version_required(
    rule: FirmwarePrerequisiteRule,
    device: Device,
    observation: DeviceObservation | None,
) -> Blocker | None:
    """Surface a hop that the operator must traverse before the target.

    v1 emits this as a recommended-severity blocker citing the named
    intermediate. The controller's upgrade-path check is the authoritative
    "is the chain reachable?" signal — this predicate is advisory.
    """
    intermediate = str(rule.predicate_args.get("via_version", ""))
    observed = observation.observed_firmware if observation is not None else None
    return _blocker(
        rule,
        "intermediate_version_required",
        required={"via_version": intermediate},
        observed={"observed_firmware": observed},
        detail=(
            f"rule {rule.name!r} recommends an intermediate hop via "
            f"{intermediate!r} before reaching the target"
        ),
        severity_override="recommended",
    )


def eval_not_in_state(
    rule: FirmwarePrerequisiteRule,
    device: Device,
    observation: DeviceObservation | None,
) -> Blocker | None:
    forbidden = list(rule.predicate_args.get("states", []))
    if device.lifecycle_state.value in forbidden:
        return _blocker(
            rule,
            "not_in_state",
            required={"states_not_in": forbidden},
            observed={"lifecycle_state": device.lifecycle_state.value},
            detail=(
                f"device is in lifecycle_state={device.lifecycle_state.value!r} "
                f"which the rule forbids ({forbidden})"
            ),
        )
    return None


def eval_region_in(
    rule: FirmwarePrerequisiteRule,
    device: Device,
    observation: DeviceObservation | None,
) -> Blocker | None:
    allowed = list(rule.predicate_args.get("regions", []))
    if device.region is None:
        return _blocker(
            rule,
            "missing_observation_field",
            required={"field": "region"},
            observed={"region": None},
            detail=(
                f"rule {rule.name!r} requires region in {allowed} but "
                f"device row has no region value"
            ),
            severity_override="required",
        )
    if device.region not in allowed:
        return _blocker(
            rule,
            "region_in",
            required={"regions": allowed},
            observed={"region": device.region},
            detail=(f"device region={device.region!r} is not in the allowed set {allowed}"),
        )
    return None


def eval_tagged_with(
    rule: FirmwarePrerequisiteRule,
    device: Device,
    observation: DeviceObservation | None,
) -> Blocker | None:
    """Deferred per F2 / Constitution VII — surfaces as advisory.

    v1 cannot evaluate tags (no Device.tags column). We emit a
    `recommended`-severity blocker noting deferral so the verdict does
    not flip to `blocked` purely on tag input. F2's scope_selector
    handles the same deferral for its scope keys.
    """
    tags = list(rule.predicate_args.get("tags", []))
    return _blocker(
        rule,
        "tagged_with",
        required={"tags": tags},
        observed={"tags_known": False},
        detail=(
            f"rule {rule.name!r} depends on device tags which v1 cannot "
            f"evaluate (Constitution VII deferral); surfacing as advisory"
        ),
        severity_override="recommended",
    )


# Closed dispatch table — unknown predicate_kind raises KeyError, which the
# controller surfaces as an internal error (catalog is mis-validated).
PredicateFn = Callable[
    [FirmwarePrerequisiteRule, Device, DeviceObservation | None],
    Blocker | None,
]

PREDICATE_DISPATCH: dict[str, PredicateFn] = {
    "min_ram_mb": eval_min_ram_mb,
    "min_disk_mb": eval_min_disk_mb,
    "min_current_version": eval_min_current_version,
    "hardware_revision_in": eval_hardware_revision_in,
    "license_present": eval_license_present,
    "intermediate_version_required": eval_intermediate_version_required,
    "not_in_state": eval_not_in_state,
    "region_in": eval_region_in,
    "tagged_with": eval_tagged_with,
}


def evaluate_rule(
    rule: FirmwarePrerequisiteRule,
    device: Device,
    observation: DeviceObservation | None,
) -> Blocker | None:
    """Dispatch to the right predicate based on `rule.predicate_kind`.

    Raises ``KeyError`` for an unknown predicate_kind. The catalog
    loader validates this at reload time but we treat it defensively
    here too — Constitution III.
    """
    fn = PREDICATE_DISPATCH[rule.predicate_kind]
    return fn(rule, device, observation)


# ---- ordering helpers ----------------------------------------------------


def _sort_key(b: Blocker) -> tuple[int, int, str]:
    """R-1 ordering key: severity desc, predicate_kind index asc, rule_id asc.

    Severity reversal is done by mapping `required` → 0, `recommended` → 1
    so that a normal ascending sort yields required-first.
    """
    sev_rank = 0 if b.severity == "required" else 1
    kind_rank = _PREDICATE_INDEX[b.predicate_kind]
    # Synthetic blockers carry rule_id=None; sort them first within their
    # kind bucket (empty string sorts before any UUID string).
    rule_rank = b.rule_id or ""
    return (sev_rank, kind_rank, rule_rank)


def sort_blockers(blockers: Iterable[Blocker]) -> list[Blocker]:
    """Stable sort per ADR-0015 §B."""
    return sorted(blockers, key=_sort_key)


def primary_blocker_of(blockers: Iterable[Blocker]) -> Blocker | None:
    """First blocker after R-1 sort, or ``None`` for an empty set."""
    sorted_list = sort_blockers(blockers)
    return sorted_list[0] if sorted_list else None
