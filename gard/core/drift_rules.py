"""Pure-function drift rules for F3.

One function per drift type (`is_target_drift`, `is_catalog_drift`, ...).
Each takes the F2 envelope plus the inputs the rule needs and returns
either a :class:`ComplianceReason` (the rule fired) or ``None`` (the
rule did not fire).

These functions are deliberately *pure* — no DB access, no logging, no
audit. The controller owns IO; this module owns logic. That separation
lets the unit-test suite drive every rule via constructed inputs
(`tests/unit/test_drift_rules.py`) without spinning up the catalog.

The seven canonical types and the precedence ordering are formalised
in **ADR-0014**. Do not reorder ``DRIFT_PRECEDENCE`` without first
amending the ADR — F4's readiness pipeline reads the same constant.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from typing import TYPE_CHECKING

from gard.core.envelope import (
    ComplianceReason,
    DriftType,
    FirmwareComplianceEnvelope,
)

if TYPE_CHECKING:
    from gard.models import DeviceObservation, FirmwarePackage


# Precedence ordering when a device classifies into multiple drift types.
# Upstream causes (catalog/rule/package) outrank downstream symptoms
# (target/discovery/evidence) so triage routes to the right team first
# (ADR-0014 §C).
DRIFT_PRECEDENCE: tuple[DriftType, ...] = (
    "catalog_drift",
    "rule_drift",
    "package_drift",
    "target_drift",
    "discovery_drift",
    "evidence_drift",
    "exception_drift",
)

_PRECEDENCE_INDEX: dict[DriftType, int] = {d: i for i, d in enumerate(DRIFT_PRECEDENCE)}


def precedence_index(drift: DriftType) -> int:
    """Lookup of where a drift type sits in :data:`DRIFT_PRECEDENCE`."""
    return _PRECEDENCE_INDEX[drift]


def primary_of(drifts: Iterable[DriftType]) -> DriftType | None:
    """Return the highest-precedence drift type, or ``None`` for an empty set.

    Deterministic — relies on :data:`DRIFT_PRECEDENCE`.
    """
    best: tuple[int, DriftType] | None = None
    for d in drifts:
        idx = _PRECEDENCE_INDEX.get(d)
        if idx is None:
            # Unknown drift type — refuse to silently coerce (Constitution III).
            raise ValueError(f"unknown drift type: {d}")
        if best is None or idx < best[0]:
            best = (idx, d)
    return best[1] if best is not None else None


def sort_by_precedence(drifts: Iterable[DriftType]) -> list[DriftType]:
    """Sort a set of drift types by :data:`DRIFT_PRECEDENCE`."""
    return sorted(drifts, key=_PRECEDENCE_INDEX.__getitem__)


# ---- individual rules -----------------------------------------------------
#
# Each rule returns a ComplianceReason (with a v1 reason-kind) or None.
# The controller composes the final reason list per ADR-0014; the rules
# do not know about each other.


def is_target_drift(env: FirmwareComplianceEnvelope) -> ComplianceReason | None:
    """A target is resolved and the observed firmware != target_version.

    Returns ``None`` for the reason payload even when the rule fires —
    F2's envelope already carries the ``version_mismatch`` reason that
    fully explains this drift type. We avoid the duplicate by
    surfacing only the *drift type* (``target_drift``) and leaving the
    reason narration to F2.

    Callers detect "rule fired" by the device's ``compliance_state``
    being ``outside_target`` plus this function returning a sentinel
    truthy non-None — see :func:`target_drift_fired` for the boolean
    primitive.
    """
    if env.state != "outside_target":
        return None
    # Sentinel reason that the controller's dedupe will collapse against
    # the F2 version_mismatch — same kind + ref_id + detail wording.
    f2_reason_detail = (
        f"observed_firmware={env.observed_version!r} != target_version={env.target_version!r}"
    )
    return ComplianceReason(
        kind="version_mismatch",
        detail=f2_reason_detail,
    )


def target_drift_fired(env: FirmwareComplianceEnvelope) -> bool:
    """Did target_drift fire? Used by the controller to keep the
    drift-type set independent of the optional reason payload."""
    return env.state == "outside_target"


def is_catalog_drift(env: FirmwareComplianceEnvelope) -> ComplianceReason | None:
    """No live FirmwareTarget matched the device's facts.

    F2 surfaces this with state=``classified`` and either an
    ``empty_catalog`` or ``no_target_matched`` reason. We promote it
    into a drift type so the summary endpoint can count it explicitly.
    """
    if env.state != "classified":
        return None
    for r in env.reasons:
        if r.kind in ("no_target_matched", "empty_catalog"):
            return ComplianceReason(
                kind=r.kind,
                detail=r.detail,
            )
    return None


def is_package_drift(
    env: FirmwareComplianceEnvelope,
    *,
    package: FirmwarePackage | None,
) -> ComplianceReason | None:
    """Target version has no FirmwarePackage row OR the package has no blob.

    Caller is responsible for resolving the package via
    ``(vendor_normalized → vendor, platform_family, version=target_version)``.
    Either condition (missing row, missing blob) routes work to the
    catalog team — both surface as ``package_not_built`` for v1
    simplicity; the detail string carries the distinction.
    """
    if env.target_version is None or env.state != "outside_target":
        return None
    if package is None:
        return ComplianceReason(
            kind="package_not_built",
            detail=(f"no FirmwarePackage row exists for target_version={env.target_version!r}"),
        )
    if not package.blob_present:
        return ComplianceReason(
            kind="package_not_built",
            ref_type="FirmwarePackage",
            ref_id=str(package.id),
            detail=(
                f"FirmwarePackage for {env.target_version!r} exists but "
                f"blob has not been uploaded (blob_present=false)"
            ),
        )
    return None


def is_rule_drift(
    env: FirmwareComplianceEnvelope,
    *,
    upgrade_paths_exist: bool,
) -> ComplianceReason | None:
    """No upgrade chain exists from observed_version to target_version.

    Caller supplies ``upgrade_paths_exist`` — typically a fast query of
    ``FirmwareUpgradePath`` rows on the platform_family. v1 treats
    "any chain exists" as sufficient; F4's reachability check is
    stricter and uses the graph directly.
    """
    if env.state != "outside_target":
        return None
    if env.observed_version is None or env.target_version is None:
        return None
    if upgrade_paths_exist:
        return None
    return ComplianceReason(
        kind="missing_upgrade_path",
        detail=(
            f"no FirmwareUpgradePath chain on this platform reaches "
            f"target_version={env.target_version!r}"
        ),
    )


def is_discovery_drift(
    env: FirmwareComplianceEnvelope,
    *,
    latest_observation: DeviceObservation | None,
    now: dt.datetime,
    stale_after_days: int,
) -> ComplianceReason | None:
    """Latest observation older than threshold OR device has none.

    Returns a reason in two cases:
    1. ``missing_observation`` — no non-null ``observed_firmware`` is on
       file (zero observation rows, or rows exist but all lack firmware).
       F2 surfaces this as ``state=unknown`` with ``observed_version=None``.
    2. ``stale_observation`` — the latest observation exists but is
       older than ``stale_after_days``.
    """
    if env.observed_version is None:
        detail = (
            "device has no DeviceObservation rows on file"
            if latest_observation is None
            else "device has no observed_firmware on file"
        )
        return ComplianceReason(
            kind="missing_observation",
            detail=detail,
        )
    if latest_observation is None:
        return ComplianceReason(
            kind="missing_observation",
            detail="device has no DeviceObservation rows on file",
        )
    age = now - latest_observation.observed_at
    if age > dt.timedelta(days=stale_after_days):
        return ComplianceReason(
            kind="stale_observation",
            ref_type="DeviceObservation",
            ref_id=str(latest_observation.id),
            detail=(
                f"latest observation is {age.days} days old (>{stale_after_days} days threshold)"
            ),
        )
    return None


def is_evidence_drift(
    env: FirmwareComplianceEnvelope,
    *,
    latest_reeval_evidence_at: dt.datetime | None,
    now: dt.datetime,
    stale_after_days: int,
) -> ComplianceReason | None:
    """Compliant device has no recent re_evaluation LifecycleEvidence row.

    Only fires when the device's current envelope state is
    ``compliant`` — non-compliant devices already surface a primary
    drift; recording evidence_drift on top would be noise.

    NB: v1 has no v1 emitter of `re_evaluation` evidence (F4+ will add
    one), so this rule effectively fires for *every* compliant device
    when ``stale_after_days`` is small. The default of 90 days plus
    the F2 catalog-load evidence rows keep that quiet in practice.
    """
    if env.state != "compliant":
        return None
    if latest_reeval_evidence_at is None:
        return ComplianceReason(
            kind="stale_observation",
            detail=(
                "device has no re_evaluation LifecycleEvidence row; "
                "compliance verdict cannot be re-validated against a "
                "recent run"
            ),
        )
    age = now - latest_reeval_evidence_at
    if age > dt.timedelta(days=stale_after_days):
        return ComplianceReason(
            kind="stale_observation",
            detail=(
                f"latest re_evaluation evidence is {age.days} days old "
                f"(>{stale_after_days} days threshold)"
            ),
        )
    return None


def is_exception_drift(env: FirmwareComplianceEnvelope) -> ComplianceReason | None:
    """F5 forward-seam: always ``None`` in v1.

    F3 ships the contract surface so future features can flip this on
    without re-cutting the API. F5 will replace this body with a query
    against an ``Exception`` table; v1 returns no reason and the
    summary endpoint reports ``exception_drift = 0``.
    """
    _ = env
    return None
