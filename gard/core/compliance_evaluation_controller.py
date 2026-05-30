"""F3 compliance evaluation controller.

Composes F2's :mod:`gard.core.compliance_controller` with the F3 drift
rules and recommended-actions catalogue. Persists results as
append-only ``ComplianceEvaluation`` rows and emits audit/log records
on every state-or-drift transition. Silent (no row, no audit) when an
evaluation produces the same verdict as the most recent persisted row
(idempotency contract, ADR-0014, R-4).

Public surface:

- :func:`evaluate`: single-device evaluation, returns a
  :class:`ComplianceEnvelope`.
- :func:`evaluate_many`: bounded batch (5,000 cap by default).
- :func:`latest_evaluation_for`: read-only fetch of the live verdict.
- :func:`fetch_summary`: estate-wide drift counts for the summary
  endpoint.

This module is the only writer of ``compliance_evaluations``.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gard.core import (
    compliance_controller as f2_controller,
)
from gard.core import (
    drift_rules,
    recommended_actions,
)
from gard.core.audit import emit as audit_emit
from gard.core.envelope import (
    ComplianceEnvelope,
    ComplianceReason,
    DriftType,
    RecommendedAction,
    build_compliance_envelope,
)
from gard.core.logging import get_correlation_id, get_logger
from gard.core.settings import get_settings
from gard.models import (
    ComplianceEvaluation,
    Device,
    DeviceObservation,
    FirmwarePackage,
    LifecycleEvidence,
)
from gard.models._enums import ActorType, EvidenceType
from gard.models.firmware_upgrade_path import FirmwareUpgradePath

_log = get_logger(__name__)


# Drift types that the summary endpoint reports. Listed explicitly so
# the response shape is stable even when one type happens to count
# zero across the entire estate.
_DRIFT_TYPES_REPORTED: tuple[DriftType, ...] = (
    "target_drift",
    "catalog_drift",
    "package_drift",
    "rule_drift",
    "evidence_drift",
    "discovery_drift",
    "exception_drift",
)


@dataclass(frozen=True, slots=True)
class EvaluationOutcome:
    """Result of a single device evaluation."""

    envelope: ComplianceEnvelope
    evaluation_id: uuid.UUID | None  # None when verdict unchanged (silent)
    state_changed: bool


@dataclass(frozen=True, slots=True)
class BatchOutcome:
    """Result of :func:`evaluate_many`."""

    requested_count: int
    evaluated_count: int
    unchanged_count: int
    correlation_id: str


@dataclass(frozen=True, slots=True)
class SummaryCounts:
    total_evaluated: int
    compliant_count: int
    unknown_count: int
    counts_by_drift_type: dict[DriftType, int]
    filters_applied: dict[str, str]
    as_of: dt.datetime


# ---- internal helpers ---------------------------------------------------


def _resolve_package(
    session: Session,
    *,
    device: Device,
    target_version: str,
) -> FirmwarePackage | None:
    """Pick the live FirmwarePackage row for (vendor, platform, version).

    Vendor mapping mirrors F2's loader: package rows carry the
    normalized vendor string, devices carry it under
    ``vendor_normalized``. Returns the first row seen ordered by
    ``loaded_at DESC`` (live rows only).
    """
    if device.vendor_normalized is None or device.platform_family is None:
        return None
    return session.scalar(
        select(FirmwarePackage)
        .where(FirmwarePackage.removed_at.is_(None))
        .where(FirmwarePackage.vendor == device.vendor_normalized)
        .where(FirmwarePackage.platform_family == device.platform_family)
        .where(FirmwarePackage.version == target_version)
        .order_by(FirmwarePackage.loaded_at.desc())
        .limit(1)
    )


def _upgrade_paths_exist(
    session: Session,
    *,
    platform_family: str | None,
    target_version: str,
) -> bool:
    """True iff any live UpgradePath edge ends at the target version.

    v1 is intentionally loose: we don't traverse the graph here, only
    confirm at least one edge points at the target on this platform.
    Full reachability is F4's job (it uses the cache in
    :mod:`gard.core.upgrade_path_graph`).
    """
    if platform_family is None:
        return False
    return (
        session.scalar(
            select(func.count())
            .select_from(FirmwareUpgradePath)
            .where(FirmwareUpgradePath.removed_at.is_(None))
            .where(FirmwareUpgradePath.platform_family == platform_family)
            .where(FirmwareUpgradePath.to_version == target_version)
        )
        or 0
    ) > 0


def _latest_observation(session: Session, device_id: uuid.UUID) -> DeviceObservation | None:
    return session.scalar(
        select(DeviceObservation)
        .where(DeviceObservation.device_id == device_id)
        .order_by(DeviceObservation.observed_at.desc())
        .limit(1)
    )


def _latest_reeval_evidence_at(session: Session, device_id: uuid.UUID) -> dt.datetime | None:
    return session.scalar(
        select(LifecycleEvidence.timestamp)
        .where(LifecycleEvidence.evidence_type == EvidenceType.re_evaluation)
        .where(LifecycleEvidence.subject_type == "Device")
        .where(LifecycleEvidence.subject_id == str(device_id))
        .order_by(LifecycleEvidence.timestamp.desc())
        .limit(1)
    )


def _latest_evaluation(session: Session, device_id: uuid.UUID) -> ComplianceEvaluation | None:
    return session.scalar(
        select(ComplianceEvaluation)
        .where(ComplianceEvaluation.device_id == device_id)
        .order_by(ComplianceEvaluation.evaluated_at.desc())
        .limit(1)
    )


def _verdict_unchanged(
    prev: ComplianceEvaluation | None,
    *,
    compliance_state: str,
    primary_drift: DriftType | None,
    secondary_drifts: list[DriftType],
    target_ref: str | None,
    target_version: str | None,
    observed_version: str | None,
    reasons: list[ComplianceReason],
    actions: list[RecommendedAction],
) -> bool:
    """Idempotency check: same verdict as the latest persisted row?

    Compares structurally — same state, drift types, refs, and the
    payload of every reason + action. We avoid comparing on
    correlation_id, evaluated_at, evaluation id (which all change every
    call by definition).
    """
    if prev is None:
        return False
    if prev.compliance_state != compliance_state:
        return False
    if prev.primary_drift_type != primary_drift:
        return False
    if list(prev.secondary_drift_types) != secondary_drifts:
        return False
    if (str(prev.target_ref) if prev.target_ref else None) != target_ref:
        return False
    if prev.target_version != target_version:
        return False
    if prev.observed_version != observed_version:
        return False
    prev_reasons = [
        {"kind": r.get("kind"), "ref_id": r.get("ref_id"), "detail": r.get("detail")}
        for r in (prev.reasons or [])
    ]
    new_reasons = [{"kind": r.kind, "ref_id": r.ref_id, "detail": r.detail} for r in reasons]
    if prev_reasons != new_reasons:
        return False
    prev_actions = sorted(prev.recommended_actions or [], key=lambda a: a.get("kind", ""))
    new_actions = sorted(
        [a.model_dump(mode="json") for a in actions],
        key=lambda a: a.get("kind", ""),
    )
    return prev_actions == new_actions


def _f3_state_from_f2(state: str) -> str:
    """Pass-through — F3 storage uses the F2 vocabulary verbatim."""
    return state


# ---- single-device evaluation -------------------------------------------


def evaluate(
    *,
    session: Session,
    audit_session: Session,
    device_id: uuid.UUID,
    actor: str = "system",
    actor_type: ActorType = ActorType.system,
) -> EvaluationOutcome:
    """Evaluate one device, persisting a new row only on verdict change.

    Side effects (only when verdict changed):
    - INSERT one ``ComplianceEvaluation`` row.
    - Emit one ``compliance.evaluated`` audit row.
    - The F2 controller may also write through to ``devices.lifecycle_state``
      and emit ``firmware_target.compliance_evaluated`` audit — this is
      desired and the F3 controller piggybacks on it.

    Idempotent on the read side: re-calling against unchanged inputs
    produces no DB write, no audit, but still returns the envelope.
    """
    device = session.get(Device, device_id)
    if device is None:
        raise ValueError(f"device not found: {device_id}")

    settings = get_settings()
    now = dt.datetime.now(dt.UTC)
    correlation_id = get_correlation_id() or "unknown"

    # Delegate the F2 question (target + observed_firmware) -----------------
    f2_envelope = f2_controller.evaluate(
        session=session,
        audit_session=audit_session,
        device_id=device_id,
        actor=actor,
        actor_type=actor_type,
    )

    # Resolve drift-rule auxiliary inputs (cheap; same row count per device).
    target_version = f2_envelope.target_version
    package: FirmwarePackage | None = None
    if target_version is not None:
        package = _resolve_package(session, device=device, target_version=target_version)
    paths_exist = (
        _upgrade_paths_exist(
            session,
            platform_family=device.platform_family,
            target_version=target_version,
        )
        if target_version is not None
        else False
    )
    latest_obs = _latest_observation(session, device_id)
    latest_reeval = _latest_reeval_evidence_at(session, device_id)

    # Fire each drift rule. Reasons accumulate; the F2 envelope's own
    # reasons (target_matched, version_mismatch, etc.) are appended.
    drift_reasons: list[tuple[DriftType, ComplianceReason]] = []

    cat = drift_rules.is_catalog_drift(f2_envelope)
    if cat is not None:
        drift_reasons.append(("catalog_drift", cat))

    rule = drift_rules.is_rule_drift(f2_envelope, upgrade_paths_exist=paths_exist)
    if rule is not None:
        drift_reasons.append(("rule_drift", rule))

    pkg = drift_rules.is_package_drift(f2_envelope, package=package)
    if pkg is not None:
        drift_reasons.append(("package_drift", pkg))

    tgt = drift_rules.is_target_drift(f2_envelope)
    if tgt is not None:
        drift_reasons.append(("target_drift", tgt))

    disc = drift_rules.is_discovery_drift(
        f2_envelope,
        latest_observation=latest_obs,
        now=now,
        stale_after_days=settings.discovery_stale_days,
    )
    if disc is not None:
        drift_reasons.append(("discovery_drift", disc))

    evd = drift_rules.is_evidence_drift(
        f2_envelope,
        latest_reeval_evidence_at=latest_reeval,
        now=now,
        stale_after_days=settings.evidence_stale_days,
    )
    if evd is not None:
        drift_reasons.append(("evidence_drift", evd))

    exc = drift_rules.is_exception_drift(f2_envelope)
    if exc is not None:
        drift_reasons.append(("exception_drift", exc))

    drift_set: list[DriftType] = drift_rules.sort_by_precedence([d for d, _ in drift_reasons])
    primary: DriftType | None = drift_rules.primary_of(drift_set)
    secondary: list[DriftType] = [d for d in drift_set if d != primary]

    # Build the F3 envelope. The F2 envelope already carries:
    # - state (compliant/outside_target/unknown/classified/target_defined)
    # - target_ref / target_version / observed_version
    # - reasons (target_matched, version_mismatch, etc.)
    # We append F3's drift reasons and overlay the typed actions.

    base_reasons: list[ComplianceReason] = []
    for r in f2_envelope.reasons:
        # F2's FirmwareComplianceReason has fields kind/ref/detail —
        # F3's ComplianceReason carries kind/ref_id/ref_type/detail.
        base_reasons.append(
            ComplianceReason(
                kind=r.kind,
                ref_id=r.ref,
                ref_type=None,
                detail=r.detail,
            )
        )
    for _, dr_reason in drift_reasons:
        base_reasons.append(dr_reason)

    actions = recommended_actions.build_actions_for(
        device=device,
        envelope=f2_envelope,
        drifts=drift_set,
    )

    # Biconditional: state == compliant <=> no primary drift
    # F2 owns the state value; we trust it. If F2 says compliant and we
    # found discovery/evidence drift, the DB CHECK in 0007 would reject
    # the row. Suppress secondary-only "compliant + discovery_drift"
    # cases by keeping primary=None when state is compliant per ADR-0014.
    if f2_envelope.state == "compliant":
        # Compliant devices may still surface secondary drift kinds via
        # the envelope, but the *primary_drift_type* DB column must be
        # null to satisfy the biconditional CHECK. We split the
        # in-memory secondary list off; persistence drops it on
        # compliant.
        persisted_primary: DriftType | None = None
        persisted_secondary: list[DriftType] = []
    else:
        persisted_primary = primary
        persisted_secondary = secondary

    envelope = build_compliance_envelope(
        state=f2_envelope.state,
        summary=f2_envelope.summary,
        drift_type=persisted_primary,
        secondary_drift_types=persisted_secondary,
        target_ref=f2_envelope.target_ref,
        target_version=f2_envelope.target_version,
        observed_version=f2_envelope.observed_version,
        observation_ref=str(latest_obs.id) if latest_obs is not None else None,
        facts=f2_envelope.facts,
        reasons=base_reasons,
        recommended_actions=actions,
        confidence=f2_envelope.confidence,
        evaluated_at=now,
        correlation_id=correlation_id,
    )

    prev = _latest_evaluation(session, device_id)
    if _verdict_unchanged(
        prev,
        compliance_state=f2_envelope.state,
        primary_drift=persisted_primary,
        secondary_drifts=persisted_secondary,
        target_ref=f2_envelope.target_ref,
        target_version=f2_envelope.target_version,
        observed_version=f2_envelope.observed_version,
        reasons=base_reasons,
        actions=actions,
    ):
        envelope.evaluation_id = str(prev.id) if prev is not None else None
        return EvaluationOutcome(
            envelope=envelope,
            evaluation_id=None,
            state_changed=False,
        )

    # Persist a new evaluation row. -------------------------------------
    row = ComplianceEvaluation(
        device_id=device_id,
        target_ref=uuid.UUID(f2_envelope.target_ref) if f2_envelope.target_ref else None,
        observation_ref=latest_obs.id if latest_obs is not None else None,
        compliance_state=f2_envelope.state,
        primary_drift_type=persisted_primary,
        secondary_drift_types=list(persisted_secondary),
        target_version=f2_envelope.target_version,
        observed_version=f2_envelope.observed_version,
        reasons=[r.model_dump(mode="json") for r in base_reasons],
        recommended_actions=[a.model_dump(mode="json") for a in actions],
        confidence=decimal.Decimal(str(round(float(f2_envelope.confidence), 2))),
        evaluated_at=now,
        correlation_id=correlation_id,
        actor=actor,
    )
    session.add(row)
    session.flush()

    envelope.evaluation_id = str(row.id)

    audit_emit(
        session=audit_session,
        action="compliance.evaluated",
        object_type="Device",
        object_id=str(device_id),
        actor=actor,
        actor_type=actor_type,
        before={
            "compliance_state": prev.compliance_state if prev is not None else None,
            "primary_drift_type": prev.primary_drift_type if prev is not None else None,
        },
        after={
            "device_id": str(device_id),
            "compliance_state": f2_envelope.state,
            "primary_drift_type": persisted_primary,
            "secondary_drift_types": persisted_secondary,
            "target_ref": f2_envelope.target_ref,
            "observed_version": f2_envelope.observed_version,
            "confidence": float(f2_envelope.confidence),
            "evaluation_id": str(row.id),
        },
        correlation_id=correlation_id,
    )

    _log.info(
        "compliance.evaluated",
        device_id=str(device_id),
        compliance_state=f2_envelope.state,
        primary_drift_type=persisted_primary,
        secondary_count=len(persisted_secondary),
        evaluation_id=str(row.id),
    )

    return EvaluationOutcome(
        envelope=envelope,
        evaluation_id=row.id,
        state_changed=True,
    )


# ---- batch evaluation ----------------------------------------------------


def evaluate_many(
    *,
    session: Session,
    audit_session: Session,
    device_ids: Iterable[uuid.UUID],
    actor: str = "system",
    actor_type: ActorType = ActorType.system,
) -> BatchOutcome:
    """Evaluate a bounded set of devices.

    Caller is responsible for resolving the set (REST router calls
    ``scope_selector.evaluate`` for the scope_selector path). The cap
    is enforced here too as defence-in-depth.
    """
    settings = get_settings()
    correlation_id = get_correlation_id() or "unknown"
    ids = list(device_ids)
    requested = len(ids)
    if requested > settings.compliance_evaluate_max_batch:
        raise ValueError(
            f"too many devices: requested={requested}, cap={settings.compliance_evaluate_max_batch}"
        )

    evaluated = 0
    unchanged = 0
    for did in ids:
        outcome = evaluate(
            session=session,
            audit_session=audit_session,
            device_id=did,
            actor=actor,
            actor_type=actor_type,
        )
        if outcome.state_changed:
            evaluated += 1
        else:
            unchanged += 1

    audit_emit(
        session=audit_session,
        action="compliance.evaluation_triggered",
        object_type="ComplianceEvaluationBatch",
        object_id=correlation_id,
        actor=actor,
        actor_type=actor_type,
        before=None,
        after={
            "requested_device_count": requested,
            "evaluated_count": evaluated,
            "unchanged_count": unchanged,
            "first_device_ids": [str(d) for d in ids[:100]],
        },
        correlation_id=correlation_id,
    )

    return BatchOutcome(
        requested_count=requested,
        evaluated_count=evaluated,
        unchanged_count=unchanged,
        correlation_id=correlation_id,
    )


# ---- read paths ---------------------------------------------------------


def latest_evaluation_for(
    session: Session,
    device_id: uuid.UUID,
) -> ComplianceEvaluation | None:
    """Return the most recent persisted evaluation for the device."""
    return _latest_evaluation(session, device_id)


def fetch_summary(
    session: Session,
    *,
    region: str | None = None,
    site: str | None = None,
    platform_family: str | None = None,
    vendor_normalized: str | None = None,
) -> SummaryCounts:
    """Compute the estate-wide drift summary.

    Implementation strategy (R-3): one query using DISTINCT ON to
    materialise the latest evaluation per device, joined to ``devices``
    for filter predicates, then aggregated in Python because the
    per-drift-type counts list is short (8) and JSON-serialising in
    Postgres adds no value at this scale. Re-visit if the device count
    exceeds ~50,000.
    """
    filters_applied: dict[str, str] = {}
    if region is not None:
        filters_applied["region"] = region
    if site is not None:
        filters_applied["site"] = site
    if platform_family is not None:
        filters_applied["platform_family"] = platform_family
    if vendor_normalized is not None:
        filters_applied["vendor_normalized"] = vendor_normalized

    # DISTINCT ON gives us the latest row per device.
    latest_subq = (
        select(
            ComplianceEvaluation.id,
            ComplianceEvaluation.device_id,
            ComplianceEvaluation.compliance_state,
            ComplianceEvaluation.primary_drift_type,
        )
        .distinct(ComplianceEvaluation.device_id)
        .order_by(
            ComplianceEvaluation.device_id,
            ComplianceEvaluation.evaluated_at.desc(),
        )
        .subquery()
    )

    q = select(
        latest_subq.c.compliance_state,
        latest_subq.c.primary_drift_type,
        func.count().label("n"),
    ).select_from(latest_subq.join(Device, Device.id == latest_subq.c.device_id))
    if region is not None:
        q = q.where(Device.region == region)
    if site is not None:
        q = q.where(Device.site == site)
    if platform_family is not None:
        q = q.where(Device.platform_family == platform_family)
    if vendor_normalized is not None:
        q = q.where(Device.vendor_normalized == vendor_normalized)
    q = q.group_by(latest_subq.c.compliance_state, latest_subq.c.primary_drift_type)

    counts: dict[DriftType, int] = {d: 0 for d in _DRIFT_TYPES_REPORTED}
    compliant = 0
    unknown = 0
    total = 0
    for state, drift, n in session.execute(q):
        total += n
        if state == "compliant":
            compliant += n
        if state == "unknown":
            unknown += n
        # Ignore drift types outside the reported set (defensive against
        # future enum additions).
        if drift is not None and drift in counts:
            counts[drift] += n

    return SummaryCounts(
        total_evaluated=total,
        compliant_count=compliant,
        unknown_count=unknown,
        counts_by_drift_type=counts,
        filters_applied=filters_applied,
        as_of=dt.datetime.now(dt.UTC),
    )


def fetch_device_list(
    session: Session,
    *,
    drift_type: DriftType | None = None,
    state: str | None = None,
    region: str | None = None,
    site: str | None = None,
    platform_family: str | None = None,
    vendor_normalized: str | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
) -> list[tuple[Device, ComplianceEvaluation]]:
    """Page of (device, latest evaluation) tuples.

    Pagination uses the evaluation row's id as the keyset cursor
    (descending). Caller serialises the cursor.
    """
    # DISTINCT ON cannot be combined directly with arbitrary WHERE on the
    # device side without a subquery — so we do the same materialise.
    latest_subq = (
        select(ComplianceEvaluation)
        .distinct(ComplianceEvaluation.device_id)
        .order_by(
            ComplianceEvaluation.device_id,
            ComplianceEvaluation.evaluated_at.desc(),
        )
        .subquery()
    )
    ce = ComplianceEvaluation
    q = (
        select(Device, ce)
        .join(latest_subq, latest_subq.c.id == ce.id)
        .join(Device, Device.id == latest_subq.c.device_id)
    )
    if drift_type is not None:
        q = q.where(ce.primary_drift_type == drift_type)
    if state is not None:
        q = q.where(ce.compliance_state == state)
    if region is not None:
        q = q.where(Device.region == region)
    if site is not None:
        q = q.where(Device.site == site)
    if platform_family is not None:
        q = q.where(Device.platform_family == platform_family)
    if vendor_normalized is not None:
        q = q.where(Device.vendor_normalized == vendor_normalized)
    if after_id is not None:
        q = q.where(ce.id < after_id)
    q = q.order_by(ce.id.desc()).limit(limit)

    return [(d, e) for d, e in session.execute(q).all()]
