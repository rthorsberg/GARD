"""F4 readiness evaluation controller.

Composes the F3 :mod:`gard.core.compliance_evaluation_controller`,
F2's :mod:`gard.core.scope_selector` + :mod:`gard.core.upgrade_path_graph`,
and the F4 :mod:`gard.core.prereq_predicates` predicate dispatch into a
single per-device readiness verdict.

R-3 pipeline:

1. Read the latest F3 ComplianceEvaluation for the device. None or
   stale (older than ``GARD_READINESS_STALE_DAYS``) → handled per R-8.
2. If F3 state is not `outside_target`, return `not_applicable` with
   the corresponding carve-out reason kind (ADR-0015 §D).
3. Resolve every live ``FirmwarePrerequisiteRule`` whose ``applies_to``
   scope selector matches the device's facts.
4. Dispatch each matched rule through ``prereq_predicates.evaluate_rule``.
   Each call yields a Blocker or None.
5. Check upgrade-path reachability via the F2 graph cache. Cap on
   cumulative edge weight = ``GARD_READINESS_UPGRADE_WEIGHT_CAP``.
   When no chain or chain too heavy, emit a synthetic
   ``missing_upgrade_path`` Blocker.
6. Sort blockers per R-1, decide state per ADR-0015 §A.
7. Build recommended actions keyed off the primary blocker (R-2).
8. Idempotency check (R-5): if the verdict matches the latest persisted
   row, return the envelope without INSERTing or auditing.
9. Otherwise INSERT a new ``ReadinessEvaluation`` row + emit
   ``readiness.evaluated`` audit + flip ``devices.lifecycle_state``
   atomically.

Public surface:
- :func:`evaluate`: single-device evaluation.
- :func:`evaluate_many`: bounded batch.
- :func:`latest_evaluation_for`: read-only fetch of the live verdict.
- :func:`fetch_summary`: estate-wide readiness counters.
- :func:`fetch_device_list`: paginated devices + envelopes.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from gard.core import (
    compliance_evaluation_controller as f3_controller,
)
from gard.core import (
    prereq_predicates,
    recommended_actions,
    scope_selector,
    upgrade_path_graph,
)
from gard.core import uplift_exception_controller as exc_ctrl
from gard.core.audit import emit as audit_emit
from gard.core.envelope import (
    Blocker,
    BlockerPredicateKind,
    ComplianceReason,
    ReadinessEnvelope,
    ReadinessState,
    RecommendedAction,
    build_readiness_envelope,
)
from gard.core.logging import get_correlation_id, get_logger
from gard.core.settings import get_settings
from gard.models import (
    ComplianceEvaluation,
    Device,
    DeviceObservation,
    FirmwarePrerequisiteRule,
    ReadinessEvaluation,
)
from gard.models._enums import ActorType, LifecycleState
from gard.models.firmware_upgrade_path import FirmwareUpgradePath

_log = get_logger(__name__)


class ReadinessInputStale(Exception):  # noqa: N818  # public sentinel, see R-8
    """The latest F3 compliance row for the device is older than the
    configured staleness threshold; the per-device router translates
    this into a 409 ``READINESS_INPUT_STALE`` envelope (R-8)."""

    def __init__(
        self,
        *,
        device_id: uuid.UUID,
        latest_compliance_evaluated_at: dt.datetime,
        stale_threshold_days: int,
    ) -> None:
        self.device_id = device_id
        self.latest_compliance_evaluated_at = latest_compliance_evaluated_at
        self.stale_threshold_days = stale_threshold_days
        super().__init__(
            f"compliance_evaluation for {device_id} is older than "
            f"{stale_threshold_days} days (last at "
            f"{latest_compliance_evaluated_at.isoformat()})"
        )


# Carve-out reasons map (ADR-0015 §D). Keys = F3 compliance_state values.
_NOT_APPLICABLE_REASON: dict[str, str] = {
    "compliant": "already_compliant",
    "classified": "no_target_resolved",
    "target_defined": "no_observation_to_verify",
    "unknown": "lifecycle_unknown",
}


@dataclass(frozen=True, slots=True)
class ReadinessOutcome:
    """Result of a single device evaluation."""

    envelope: ReadinessEnvelope
    evaluation_id: uuid.UUID | None  # None when verdict unchanged
    state_changed: bool


@dataclass(frozen=True, slots=True)
class ReadinessBatchOutcome:
    """Result of :func:`evaluate_many`."""

    requested_count: int
    evaluated_count: int
    unchanged_count: int
    not_applicable_count: int
    correlation_id: str


@dataclass(frozen=True, slots=True)
class ReadinessSummary:
    total_outside_target: int
    ready_for_uplift_count: int
    blocked_count: int
    not_applicable_count: int
    top_blocker_categories: list[tuple[str, int]]
    filters_applied: dict[str, str]
    as_of: dt.datetime


# ---- internal helpers ----------------------------------------------------


def _device_facts(device: Device) -> dict[str, object]:
    """Facts dict consumed by F2 scope_selector.

    Mirrors the shape the F2 compliance_controller uses when picking
    targets — keeps the selector grammar identical across F2/F3/F4.
    """
    return {
        "vendor_normalized": device.vendor_normalized,
        "platform_family": device.platform_family,
        "region": device.region,
        "site": device.site,
        "role": device.role,
        "hardware_revision": device.hardware_revision,
        "lifecycle_state": device.lifecycle_state.value,
        "tags": device.tags,
    }


def _matching_rules(
    session: Session,
    device: Device,
) -> list[FirmwarePrerequisiteRule]:
    """Live prereq rules whose ``applies_to`` matches this device."""
    rules = list(
        session.scalars(
            select(FirmwarePrerequisiteRule)
            .where(FirmwarePrerequisiteRule.removed_at.is_(None))
            .where(FirmwarePrerequisiteRule.evaluable.is_(True))
            .order_by(FirmwarePrerequisiteRule.id)
        )
    )
    facts = _device_facts(device)
    return [r for r in rules if scope_selector.evaluate(r.applies_to, facts).matched]


def _platform_edges(
    session: Session,
    platform_family: str,
) -> list[upgrade_path_graph.EdgeSpec]:
    """Live upgrade-path edges for a platform_family."""
    rows = session.scalars(
        select(FirmwareUpgradePath)
        .where(FirmwareUpgradePath.removed_at.is_(None))
        .where(FirmwareUpgradePath.platform_family == platform_family)
    ).all()
    return [
        upgrade_path_graph.EdgeSpec(
            from_version=r.from_version,
            to_version=r.to_version,
            weight=r.weight,
        )
        for r in rows
    ]


def _latest_observation(
    session: Session,
    device_id: uuid.UUID,
) -> DeviceObservation | None:
    return session.scalar(
        select(DeviceObservation)
        .where(DeviceObservation.device_id == device_id)
        .order_by(DeviceObservation.observed_at.desc())
        .limit(1)
    )


def _latest_readiness(
    session: Session,
    device_id: uuid.UUID,
) -> ReadinessEvaluation | None:
    return session.scalar(
        select(ReadinessEvaluation)
        .where(ReadinessEvaluation.device_id == device_id)
        .order_by(ReadinessEvaluation.evaluated_at.desc())
        .limit(1)
    )


def _verdict_unchanged(
    prev: ReadinessEvaluation | None,
    *,
    readiness_state: ReadinessState,
    blockers: list[Blocker],
    actions: list[RecommendedAction],
    upgrade_path_exists: bool,
    applicable_rules_count: int,
    target_version: str | None,
    observed_version: str | None,
) -> bool:
    """R-5 idempotency: same verdict as the latest persisted row?"""
    if prev is None:
        return False
    if prev.readiness_state != readiness_state:
        return False
    if prev.upgrade_path_exists != upgrade_path_exists:
        return False
    if prev.applicable_rules_count != applicable_rules_count:
        return False
    if prev.target_version != target_version:
        return False
    if prev.observed_version != observed_version:
        return False
    prev_blockers = [
        {
            "rule_id": b.get("rule_id"),
            "predicate_kind": b.get("predicate_kind"),
            "severity": b.get("severity"),
            "required": b.get("required"),
            "observed": b.get("observed"),
            "detail": b.get("detail"),
        }
        for b in (prev.blockers or [])
    ]
    new_blockers = [
        {
            "rule_id": b.rule_id,
            "predicate_kind": b.predicate_kind,
            "severity": b.severity,
            "required": b.required,
            "observed": b.observed,
            "detail": b.detail,
        }
        for b in blockers
    ]
    if prev_blockers != new_blockers:
        return False
    prev_actions = sorted(
        prev.recommended_actions or [],
        key=lambda a: (a.get("kind", ""), str(a)),
    )
    new_actions = sorted(
        [a.model_dump(mode="json") for a in actions],
        key=lambda a: (a.get("kind", ""), str(a)),
    )
    return prev_actions == new_actions


def _build_actions(
    *,
    device: Device,
    state: ReadinessState,
    blockers: list[Blocker],
    target_version: str | None,
    target_platform_family: str | None,
) -> list[RecommendedAction]:
    """R-7 action composition keyed off the primary blocker."""
    actions: list[RecommendedAction] = []
    if state == "ready_for_uplift":
        actions.append(
            recommended_actions.schedule_uplift_wave(
                device_id=device.id,
                target_version=target_version,
                target_platform_family=target_platform_family,
            )
        )
        return sorted(actions, key=lambda a: (a.kind, a.model_dump_json()))

    if not blockers:
        return actions

    primary = blockers[0]
    kind = primary.predicate_kind
    if kind in ("min_ram_mb", "min_disk_mb", "hardware_revision_in"):
        actions.append(
            recommended_actions.hardware_refresh(
                device_id=device.id,
                detail=primary.detail,
            )
        )
    elif kind == "license_present":
        actions.append(
            recommended_actions.license_acquire(
                device_id=device.id,
                detail=primary.detail,
            )
        )
    elif kind in (
        "min_current_version",
        "intermediate_version_required",
        "missing_upgrade_path",
    ):
        actions.append(
            recommended_actions.firmware_intermediate_step(
                device_id=device.id,
                target_version=target_version,
                target_platform_family=target_platform_family,
                detail=primary.detail,
            )
        )
    elif kind == "missing_observation_field":
        actions.append(
            recommended_actions.import_observation(
                device_id=device.id,
                detail=primary.detail,
            )
        )
    else:
        # not_in_state / region_in / tagged_with — operational, no
        # automatable suggestion. Fallback escalation.
        actions.append(
            recommended_actions.escalate_to_catalog_owner(
                device_id=device.id,
                detail=primary.detail,
            )
        )

    return sorted(actions, key=lambda a: (a.kind, a.model_dump_json()))


def _summary_text(
    state: ReadinessState,
    blockers: list[Blocker],
) -> str:
    if state == "ready_for_uplift":
        return "device is ready for uplift"
    if state == "not_applicable":
        return "readiness is not applicable for this device"
    req = sum(1 for b in blockers if b.severity == "required")
    rec = sum(1 for b in blockers if b.severity == "recommended")
    return f"blocked: {req} required + {rec} recommended blocker(s)"


# ---- single-device evaluation -------------------------------------------


def evaluate(
    *,
    session: Session,
    audit_session: Session,
    device_id: uuid.UUID,
    actor: str = "system",
    actor_type: ActorType = ActorType.system,
) -> ReadinessOutcome:
    """Evaluate one device, persisting a new row only on verdict change."""
    device = session.get(Device, device_id)
    if device is None:
        raise ValueError(f"device not found: {device_id}")

    settings = get_settings()
    now = dt.datetime.now(dt.UTC)
    correlation_id = get_correlation_id() or "unknown"

    # 0. Lazy exception expiry (R-6 / ADR-0016 §C) -----------------------
    exc_ctrl.expire_overdue_exceptions(
        session=session,
        audit_session=audit_session,
        device_id=device_id,
        actor=actor,
        actor_type=actor_type,
    )

    # 1. Latest F3 row + staleness check ---------------------------------
    f3_row = f3_controller.latest_evaluation_for(session, device_id)
    if f3_row is None:
        return _emit_not_applicable(
            session=session,
            audit_session=audit_session,
            device=device,
            reason_kind="no_compliance_evaluation",
            reason_detail=(
                "device has no compliance_evaluation row; call "
                "POST /api/v1/compliance/evaluate first"
            ),
            f3_row=None,
            now=now,
            correlation_id=correlation_id,
            actor=actor,
            actor_type=actor_type,
        )

    age_days = (now - f3_row.evaluated_at).days
    if age_days > settings.readiness_stale_days:
        raise ReadinessInputStale(
            device_id=device_id,
            latest_compliance_evaluated_at=f3_row.evaluated_at,
            stale_threshold_days=settings.readiness_stale_days,
        )

    # 2. Carve-out for non-outside_target states -------------------------
    if f3_row.compliance_state != "outside_target":
        reason_kind = _NOT_APPLICABLE_REASON.get(f3_row.compliance_state)
        if reason_kind is None:
            # Defensive — F3 enum changed under us.
            reason_kind = "lifecycle_unknown"
        return _emit_not_applicable(
            session=session,
            audit_session=audit_session,
            device=device,
            reason_kind=reason_kind,
            reason_detail=(
                f"latest compliance_state={f3_row.compliance_state!r}; readiness not applicable"
            ),
            f3_row=f3_row,
            now=now,
            correlation_id=correlation_id,
            actor=actor,
            actor_type=actor_type,
        )

    # 2.5 Active exception carve-out (ADR-0016 §C / FR-012) --------------
    active_exc = exc_ctrl.find_active_approved_exception(session, device_id, now=now)
    if active_exc is not None:
        return _emit_active_exception(
            session=session,
            audit_session=audit_session,
            device=device,
            exception_id=active_exc.id,
            f3_row=f3_row,
            now=now,
            correlation_id=correlation_id,
            actor=actor,
            actor_type=actor_type,
        )

    # 3+4. Resolve matching rules, fire predicates -----------------------
    rules = _matching_rules(session, device)
    observation = _latest_observation(session, device_id)
    raw_blockers: list[Blocker] = []
    for rule in rules:
        b = prereq_predicates.evaluate_rule(rule, device, observation)
        if b is not None:
            raw_blockers.append(b)

    # 5. Upgrade-path reachability --------------------------------------
    target_version = f3_row.target_version
    observed_version = f3_row.observed_version
    upgrade_path_exists = False
    if (
        device.platform_family is not None
        and target_version is not None
        and observed_version is not None
    ):
        cache = upgrade_path_graph.UpgradePathGraphCache()
        edges = _platform_edges(session, device.platform_family)
        result = cache.with_edges(
            device.platform_family,
            edges,
            from_version=observed_version,
            to_version=target_version,
        )
        if result.chain and (
            result.total_weight is None
            or result.total_weight <= settings.readiness_upgrade_weight_cap
        ):
            upgrade_path_exists = True

    if not upgrade_path_exists and target_version is not None:
        raw_blockers.append(
            Blocker(
                rule_id=None,
                rule_name=None,
                predicate_kind="missing_upgrade_path",
                severity="required",
                required={
                    "target_version": target_version,
                    "platform_family": device.platform_family,
                },
                observed={"observed_version": observed_version},
                detail=(
                    f"no upgrade-path chain from {observed_version!r} to "
                    f"{target_version!r} on platform "
                    f"{device.platform_family!r} (or all chains exceed "
                    f"weight cap {settings.readiness_upgrade_weight_cap})"
                ),
            )
        )

    # 6. Sort + decide verdict ------------------------------------------
    blockers = prereq_predicates.sort_blockers(raw_blockers)
    has_required = any(b.severity == "required" for b in blockers)
    state: ReadinessState = "blocked" if has_required else "ready_for_uplift"

    # 7. Recommended actions --------------------------------------------
    actions = _build_actions(
        device=device,
        state=state,
        blockers=blockers,
        target_version=target_version,
        target_platform_family=device.platform_family,
    )

    envelope = build_readiness_envelope(
        state=state,
        summary=_summary_text(state, blockers),
        target_version=target_version,
        observed_version=observed_version,
        upgrade_path_exists=upgrade_path_exists,
        applicable_rules_count=len(rules),
        blockers=blockers,
        recommended_actions=actions,
        reasons=[],
        compliance_evaluation_ref=str(f3_row.id),
        confidence=1.0,
        evaluated_at=now,
        correlation_id=correlation_id,
    )

    # 8. Idempotency check ----------------------------------------------
    prev = _latest_readiness(session, device_id)
    if _verdict_unchanged(
        prev,
        readiness_state=state,
        blockers=blockers,
        actions=actions,
        upgrade_path_exists=upgrade_path_exists,
        applicable_rules_count=len(rules),
        target_version=target_version,
        observed_version=observed_version,
    ):
        envelope.evaluation_id = str(prev.id) if prev is not None else None
        return ReadinessOutcome(
            envelope=envelope,
            evaluation_id=None,
            state_changed=False,
        )

    # 9. Persist + audit + lifecycle write ------------------------------
    row = ReadinessEvaluation(
        device_id=device_id,
        compliance_evaluation_ref=f3_row.id,
        readiness_state=state,
        target_version=target_version,
        observed_version=observed_version,
        upgrade_path_exists=upgrade_path_exists,
        applicable_rules_count=len(rules),
        blockers=[b.model_dump(mode="json") for b in blockers],
        recommended_actions=[a.model_dump(mode="json") for a in actions],
        reasons=[],
        confidence=decimal.Decimal("1.00"),
        evaluated_at=now,
        correlation_id=correlation_id,
        actor=actor,
    )
    session.add(row)
    session.flush()

    # Atomically transition the device's lifecycle_state — the F3
    # carve-out path doesn't reach here, so device.lifecycle_state is
    # `outside_target` (or a previously-set F4 verdict).
    new_lifecycle = (
        LifecycleState.ready_for_uplift if state == "ready_for_uplift" else LifecycleState.blocked
    )
    prev_lifecycle = device.lifecycle_state.value
    device.lifecycle_state = new_lifecycle

    envelope.evaluation_id = str(row.id)

    audit_emit(
        session=audit_session,
        action="readiness.evaluated",
        object_type="Device",
        object_id=str(device_id),
        actor=actor,
        actor_type=actor_type,
        before={
            "readiness_state": prev.readiness_state if prev is not None else None,
            "lifecycle_state": prev_lifecycle,
        },
        after={
            "device_id": str(device_id),
            "readiness_state": state,
            "lifecycle_state": new_lifecycle.value,
            "blocker_count": len(blockers),
            "primary_blocker_kind": blockers[0].predicate_kind if blockers else None,
            "upgrade_path_exists": upgrade_path_exists,
            "evaluation_id": str(row.id),
        },
        correlation_id=correlation_id,
    )

    _log.info(
        "readiness.evaluated",
        device_id=str(device_id),
        readiness_state=state,
        blocker_count=len(blockers),
        evaluation_id=str(row.id),
    )

    return ReadinessOutcome(
        envelope=envelope,
        evaluation_id=row.id,
        state_changed=True,
    )


def _emit_active_exception(
    *,
    session: Session,
    audit_session: Session,
    device: Device,
    exception_id: uuid.UUID,
    f3_row: ComplianceEvaluation,
    now: dt.datetime,
    correlation_id: str,
    actor: str,
    actor_type: ActorType,
) -> ReadinessOutcome:
    """Carve-out: approved active exception → ``not_applicable`` (FR-012)."""
    reason = ComplianceReason(
        kind="active_exception",
        ref_type="UpliftException",
        ref_id=str(exception_id),
        detail="device has an approved active exception",
    )
    reason_json = reason.model_dump(mode="json")

    envelope = build_readiness_envelope(
        state="not_applicable",
        summary="readiness is not applicable for this device",
        target_version=f3_row.target_version,
        observed_version=f3_row.observed_version,
        upgrade_path_exists=False,
        applicable_rules_count=0,
        blockers=[],
        recommended_actions=[],
        reasons=[reason],
        compliance_evaluation_ref=str(f3_row.id),
        confidence=1.0,
        evaluated_at=now,
        correlation_id=correlation_id,
    )

    prev = _latest_readiness(session, device.id)
    if (
        prev is not None
        and prev.readiness_state == "not_applicable"
        and not prev.blockers
        and (prev.reasons or []) == [reason_json]
    ):
        envelope.evaluation_id = str(prev.id)
        return ReadinessOutcome(
            envelope=envelope,
            evaluation_id=None,
            state_changed=False,
        )

    row = ReadinessEvaluation(
        device_id=device.id,
        compliance_evaluation_ref=f3_row.id,
        readiness_state="not_applicable",
        target_version=f3_row.target_version,
        observed_version=f3_row.observed_version,
        upgrade_path_exists=False,
        applicable_rules_count=0,
        blockers=[],
        recommended_actions=[],
        reasons=[reason_json],
        confidence=decimal.Decimal("1.00"),
        evaluated_at=now,
        correlation_id=correlation_id,
        actor=actor,
    )
    session.add(row)
    session.flush()
    envelope.evaluation_id = str(row.id)

    audit_emit(
        session=audit_session,
        action="readiness.evaluated",
        object_type="Device",
        object_id=str(device.id),
        actor=actor,
        actor_type=actor_type,
        before={
            "readiness_state": prev.readiness_state if prev is not None else None,
            "lifecycle_state": device.lifecycle_state.value,
        },
        after={
            "device_id": str(device.id),
            "readiness_state": "not_applicable",
            "reason_kind": "active_exception",
            "exception_id": str(exception_id),
            "evaluation_id": str(row.id),
        },
        correlation_id=correlation_id,
    )

    return ReadinessOutcome(
        envelope=envelope,
        evaluation_id=row.id,
        state_changed=True,
    )


def _emit_not_applicable(
    *,
    session: Session,
    audit_session: Session,
    device: Device,
    reason_kind: str,
    reason_detail: str,
    f3_row: ComplianceEvaluation | None,
    now: dt.datetime,
    correlation_id: str,
    actor: str,
    actor_type: ActorType,
) -> ReadinessOutcome:
    """Build + persist a `not_applicable` verdict (lifecycle untouched)."""
    reason = ComplianceReason(
        # Reusing the F3 ComplianceReasonKind union — we extend `kind`
        # by storing the F4 carve-out in `detail` and using the
        # closest-fit F3 kind for the typed field. v2 will widen the
        # ComplianceReasonKind enum to include carve-out kinds natively.
        kind="predicate_deferred",
        detail=f"[{reason_kind}] {reason_detail}",
    )

    envelope = build_readiness_envelope(
        state="not_applicable",
        summary="readiness is not applicable for this device",
        target_version=f3_row.target_version if f3_row is not None else None,
        observed_version=f3_row.observed_version if f3_row is not None else None,
        upgrade_path_exists=False,
        applicable_rules_count=0,
        blockers=[],
        recommended_actions=[],
        reasons=[reason],
        compliance_evaluation_ref=str(f3_row.id) if f3_row is not None else None,
        confidence=1.0,
        evaluated_at=now,
        correlation_id=correlation_id,
    )

    prev = _latest_readiness(session, device.id)
    if (
        prev is not None
        and prev.readiness_state == "not_applicable"
        and not prev.blockers
        and (prev.reasons or []) == [reason.model_dump(mode="json")]
    ):
        envelope.evaluation_id = str(prev.id)
        return ReadinessOutcome(
            envelope=envelope,
            evaluation_id=None,
            state_changed=False,
        )

    row = ReadinessEvaluation(
        device_id=device.id,
        compliance_evaluation_ref=f3_row.id if f3_row is not None else None,
        readiness_state="not_applicable",
        target_version=f3_row.target_version if f3_row is not None else None,
        observed_version=f3_row.observed_version if f3_row is not None else None,
        upgrade_path_exists=False,
        applicable_rules_count=0,
        blockers=[],
        recommended_actions=[],
        reasons=[reason.model_dump(mode="json")],
        confidence=decimal.Decimal("1.00"),
        evaluated_at=now,
        correlation_id=correlation_id,
        actor=actor,
    )
    session.add(row)
    session.flush()
    envelope.evaluation_id = str(row.id)

    audit_emit(
        session=audit_session,
        action="readiness.evaluated",
        object_type="Device",
        object_id=str(device.id),
        actor=actor,
        actor_type=actor_type,
        before={
            "readiness_state": prev.readiness_state if prev is not None else None,
        },
        after={
            "device_id": str(device.id),
            "readiness_state": "not_applicable",
            "reason_kind": reason_kind,
            "evaluation_id": str(row.id),
        },
        correlation_id=correlation_id,
    )

    return ReadinessOutcome(
        envelope=envelope,
        evaluation_id=row.id,
        state_changed=True,
    )


# ---- batch + reads -------------------------------------------------------


def evaluate_many(
    *,
    session: Session,
    audit_session: Session,
    device_ids: Iterable[uuid.UUID],
    actor: str = "system",
    actor_type: ActorType = ActorType.system,
) -> ReadinessBatchOutcome:
    """Evaluate a bounded set of devices.

    Stale-input devices contribute to ``not_applicable_count`` (the
    summary path's R-8 behaviour) — the per-device endpoint raises
    instead.
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
    not_applicable = 0
    for did in ids:
        try:
            outcome = evaluate(
                session=session,
                audit_session=audit_session,
                device_id=did,
                actor=actor,
                actor_type=actor_type,
            )
        except ReadinessInputStale:
            # Treat as not_applicable in the batch path (R-8 summary
            # semantics extend to evaluate_many for symmetry).
            not_applicable += 1
            continue
        if outcome.state_changed:
            evaluated += 1
        else:
            unchanged += 1
        if outcome.envelope.state == "not_applicable":
            not_applicable += 1

    audit_emit(
        session=audit_session,
        action="readiness.evaluation_triggered",
        object_type="ReadinessEvaluationBatch",
        object_id=correlation_id,
        actor=actor,
        actor_type=actor_type,
        before=None,
        after={
            "requested_device_count": requested,
            "evaluated_count": evaluated,
            "unchanged_count": unchanged,
            "not_applicable_count": not_applicable,
            "first_device_ids": [str(d) for d in ids[:100]],
        },
        correlation_id=correlation_id,
    )

    return ReadinessBatchOutcome(
        requested_count=requested,
        evaluated_count=evaluated,
        unchanged_count=unchanged,
        not_applicable_count=not_applicable,
        correlation_id=correlation_id,
    )


def latest_evaluation_for(
    session: Session,
    device_id: uuid.UUID,
) -> ReadinessEvaluation | None:
    """Return the most recent persisted readiness row for the device."""
    return _latest_readiness(session, device_id)


def fetch_summary(
    session: Session,
    *,
    region: str | None = None,
    site: str | None = None,
    platform_family: str | None = None,
    vendor_normalized: str | None = None,
) -> ReadinessSummary:
    """Compute the estate-wide readiness summary.

    Reads from the latest ReadinessEvaluation per device using DISTINCT
    ON. ``top_blocker_categories`` is computed from the JSONB
    ``blockers->0->>'predicate_kind'`` (the partial expression index
    backs this query).
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

    latest_subq = (
        select(
            ReadinessEvaluation.id,
            ReadinessEvaluation.device_id,
            ReadinessEvaluation.readiness_state,
            ReadinessEvaluation.blockers,
        )
        .distinct(ReadinessEvaluation.device_id)
        .order_by(
            ReadinessEvaluation.device_id,
            ReadinessEvaluation.evaluated_at.desc(),
        )
        .subquery()
    )

    q = select(
        latest_subq.c.readiness_state,
        latest_subq.c.blockers,
    ).select_from(latest_subq.join(Device, Device.id == latest_subq.c.device_id))
    if region is not None:
        q = q.where(Device.region == region)
    if site is not None:
        q = q.where(Device.site == site)
    if platform_family is not None:
        q = q.where(Device.platform_family == platform_family)
    if vendor_normalized is not None:
        q = q.where(Device.vendor_normalized == vendor_normalized)

    ready = 0
    blocked = 0
    not_applicable = 0
    kind_counts: dict[str, int] = {}
    for state, blockers in session.execute(q):
        if state == "ready_for_uplift":
            ready += 1
        elif state == "blocked":
            blocked += 1
        elif state == "not_applicable":
            not_applicable += 1
        if state == "blocked" and blockers:
            first = blockers[0] if isinstance(blockers, list) and blockers else None
            if isinstance(first, dict):
                kind = first.get("predicate_kind")
                if isinstance(kind, str):
                    kind_counts[kind] = kind_counts.get(kind, 0) + 1

    # Sort by count desc, then kind asc; cap at 10.
    top = sorted(kind_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]

    total_outside_target = ready + blocked  # devices F4 has a verdict on
    return ReadinessSummary(
        total_outside_target=total_outside_target,
        ready_for_uplift_count=ready,
        blocked_count=blocked,
        not_applicable_count=not_applicable,
        top_blocker_categories=top,
        filters_applied=filters_applied,
        as_of=dt.datetime.now(dt.UTC),
    )


def fetch_device_list(
    session: Session,
    *,
    state: ReadinessState | None = None,
    blocker_kind: BlockerPredicateKind | None = None,
    region: str | None = None,
    site: str | None = None,
    platform_family: str | None = None,
    vendor_normalized: str | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
) -> list[tuple[Device, ReadinessEvaluation]]:
    """Page of (device, latest readiness row) tuples.

    Cursor keyed on ReadinessEvaluation.id descending — matches F3's
    pagination shape so callers can share helper code.
    """
    latest_subq = (
        select(ReadinessEvaluation)
        .distinct(ReadinessEvaluation.device_id)
        .order_by(
            ReadinessEvaluation.device_id,
            ReadinessEvaluation.evaluated_at.desc(),
        )
        .subquery()
    )
    re = ReadinessEvaluation
    q = (
        select(Device, re)
        .join(latest_subq, latest_subq.c.id == re.id)
        .join(Device, Device.id == latest_subq.c.device_id)
    )
    if state is not None:
        q = q.where(re.readiness_state == state)
    if blocker_kind is not None:
        # Filter on the primary blocker's predicate_kind. JSONB path:
        # blockers->0->>'predicate_kind'.
        q = q.where(
            and_(
                func.jsonb_array_length(re.blockers) > 0,
                re.blockers[0]["predicate_kind"].astext == blocker_kind,
            )
        )
    if region is not None:
        q = q.where(Device.region == region)
    if site is not None:
        q = q.where(Device.site == site)
    if platform_family is not None:
        q = q.where(Device.platform_family == platform_family)
    if vendor_normalized is not None:
        q = q.where(Device.vendor_normalized == vendor_normalized)
    if after_id is not None:
        q = q.where(re.id < after_id)
    q = q.order_by(re.id.desc()).limit(limit)

    return [(d, e) for d, e in session.execute(q).all()]


__all__ = [
    "ReadinessBatchOutcome",
    "ReadinessInputStale",
    "ReadinessOutcome",
    "ReadinessSummary",
    "evaluate",
    "evaluate_many",
    "fetch_device_list",
    "fetch_summary",
    "latest_evaluation_for",
]
