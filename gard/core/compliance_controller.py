"""F2 firmware-compliance evaluation controller.

Given a device, decide:

1. Which (if any) of the loaded ``firmware_targets`` rows applies, using
   :mod:`gard.core.scope_selector` for the AND-only grammar and tie-break
   on specificity → ``loaded_at DESC``.
2. Whether the device's last observed firmware matches the target's
   ``target_version``.
3. Map (target, observation) → one of five lifecycle states:
   - ``compliant``        target matched AND observed == target_version
   - ``outside_target``   target matched AND observed != target_version
   - ``unknown``          target matched AND observed is null/missing
   - ``target_defined``   reserved for "target exists but the catalog is
                          empty for this device's selectors" (currently
                          collapsed into ``classified`` per spec.md AC-1.4)
   - ``classified``       no live target matched OR the catalog is empty

The controller is the **single** writer of ``device.lifecycle_state`` for
F2-driven transitions. It emits one
``firmware_target.compliance_evaluated`` audit row whenever the state
actually changes — re-evaluations against unchanged inputs are silent
(idempotency contract, spec.md FR-014).

Per ADR-0011: this controller reads exclusively from live (not
soft-deleted) FirmwareTarget rows and never writes to the catalog
tables.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.core.audit import emit as audit_emit
from gard.core.envelope import (
    FirmwareComplianceEnvelope,
    FirmwareComplianceReason,
    build_firmware_compliance_envelope,
)
from gard.core.logging import get_correlation_id, get_logger
from gard.core.scope_selector import evaluate as evaluate_selector
from gard.core.scope_selector import specificity
from gard.models import Device, DeviceObservation, FirmwareTarget
from gard.models._enums import ActorType, LifecycleState

_log = get_logger(__name__)


# ---- domain types ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Candidate:
    """One target that matched the device's facts during evaluation."""

    target: FirmwareTarget
    specificity: int
    deferred_keys: frozenset[str]


# ---- helpers --------------------------------------------------------------


def _facts_for(device: Device) -> dict[str, Any]:
    """Build the fact dict the selector grammar consumes.

    Mapping is intentionally narrow — only the keys the selector vocabulary
    references, plus ``lifecycle_state`` (consumed by ``not_in_state``).
    Missing values become None (selector treats None as non-matching).
    """
    return {
        "vendor_normalized": device.vendor_normalized,
        "platform_family": device.platform_family,
        "region": device.region,
        "site": device.site,
        "role": device.role,
        "hardware_revision": device.hardware_revision,
        "lifecycle_state": device.lifecycle_state.value,
    }


def _active_targets(session: Session) -> list[FirmwareTarget]:
    """Every live target ordered by ``loaded_at DESC`` for stable tie-break."""
    return list(
        session.scalars(
            select(FirmwareTarget)
            .where(FirmwareTarget.removed_at.is_(None))
            .order_by(FirmwareTarget.loaded_at.desc())
        )
    )


def _latest_observed_firmware(session: Session, device_id: Any) -> str | None:
    """Return the device's most-recent non-null observed firmware (or None).

    Observations carry the firmware string per F1's CSV import contract;
    we walk the history in created_at DESC order and return the first
    non-null value. Returning None means "the device has no observation
    with a firmware string on file" — never coerced to a default per
    constitution III.
    """
    return session.scalar(
        select(DeviceObservation.observed_firmware)
        .where(DeviceObservation.device_id == device_id)
        .where(DeviceObservation.observed_firmware.is_not(None))
        .order_by(DeviceObservation.created_at.desc())
        .limit(1)
    )


def _summarize(
    state: str,
    device: Device,
    target: FirmwareTarget | None,
    observed: str | None,
) -> str:
    label = f"{device.hostname}/{device.site}"
    if state == "compliant" and target is not None:
        return f"{label} on firmware {observed!r} matches target {target.name!r}"
    if state == "outside_target" and target is not None:
        return (
            f"{label}: observed {observed!r} != target "
            f"{target.target_version!r} (target {target.name!r})"
        )
    if state == "unknown" and target is not None:
        return f"{label}: target {target.name!r} applies but no observed firmware is on file yet"
    if state == "classified":
        # F2 collapses "no target matched" + "empty catalog" + "device not
        # yet classified" into the F1 baseline state.
        return f"{label}: no firmware target applies; lifecycle remains 'classified'"
    return f"{label}: lifecycle_state={state}"


def _resolve_target(
    targets: list[FirmwareTarget],
    facts: dict[str, Any],
) -> tuple[_Candidate | None, list[_Candidate], frozenset[str]]:
    """Return (winner, runners_up, union_of_deferred_keys).

    Winner is the highest-specificity match; ties are broken by the order
    of the input (which is already ``loaded_at DESC`` from
    :func:`_active_targets`).

    ``deferred`` is the union of every candidate's deferred-key flag so
    callers can surface ``predicate_deferred`` reasons.
    """
    matched: list[_Candidate] = []
    deferred_union: set[str] = set()

    for t in targets:
        verdict = evaluate_selector(t.scope_selector, facts)
        deferred_union |= verdict.deferred_keys
        if not verdict.matched:
            continue
        matched.append(
            _Candidate(
                target=t,
                specificity=specificity(t.scope_selector),
                deferred_keys=verdict.deferred_keys,
            )
        )

    if not matched:
        return None, [], frozenset(deferred_union)

    matched.sort(key=lambda c: c.specificity, reverse=True)
    winner = matched[0]
    runners_up = matched[1:]
    return winner, runners_up, frozenset(deferred_union)


# ---- main entry point -----------------------------------------------------


def evaluate(
    *,
    session: Session,
    audit_session: Session,
    device_id: Any,
    actor: str = "system",
    actor_type: ActorType = ActorType.system,
) -> FirmwareComplianceEnvelope:
    """Evaluate firmware compliance for a single device.

    Returns a :class:`FirmwareComplianceEnvelope`. Side effects:

    - Updates ``device.lifecycle_state`` in-place on ``session`` when the
      computed state differs from the persisted one.
    - Emits exactly one ``firmware_target.compliance_evaluated`` audit row
      via ``audit_session`` when state changed. Unchanged evaluations
      emit nothing.

    Callers own the transaction boundary for both sessions; this function
    issues ``session.flush()`` only when the state actually changed and
    never commits.
    """
    device = session.get(Device, device_id)
    if device is None:
        raise ValueError(f"device not found: {device_id}")

    targets = _active_targets(session)
    facts = _facts_for(device)
    observed = _latest_observed_firmware(session, device.id)
    previous_state = device.lifecycle_state.value

    correlation_id = get_correlation_id()

    # Empty catalog branch ---------------------------------------------------
    if not targets:
        env = build_firmware_compliance_envelope(
            state="classified",
            summary=_summarize("classified", device, None, observed),
            observed_version=observed,
            reasons=[
                FirmwareComplianceReason(
                    kind="empty_catalog",
                    detail="no firmware_targets rows are live; falling back to classified.",
                )
            ],
            facts={"device_id": str(device.id), "hostname": device.hostname},
            correlation_id=correlation_id,
        )
        _maybe_transition(
            session=session,
            audit_session=audit_session,
            device=device,
            new_state=LifecycleState.classified,
            previous_state=previous_state,
            target=None,
            observed=observed,
            actor=actor,
            actor_type=actor_type,
            correlation_id=correlation_id,
            reason="empty_catalog",
        )
        return env

    winner, runners_up, deferred = _resolve_target(targets, facts)

    # No target matched -----------------------------------------------------
    if winner is None:
        reasons: list[FirmwareComplianceReason] = [
            FirmwareComplianceReason(
                kind="no_target_matched",
                detail=f"none of {len(targets)} live targets matched device facts",
            )
        ]
        if deferred:
            reasons.append(
                FirmwareComplianceReason(
                    kind="predicate_deferred",
                    detail=f"deferred selector keys: {sorted(deferred)}",
                )
            )
        env = build_firmware_compliance_envelope(
            state="classified",
            summary=_summarize("classified", device, None, observed),
            observed_version=observed,
            reasons=reasons,
            facts={"device_id": str(device.id), "hostname": device.hostname},
            correlation_id=correlation_id,
        )
        _maybe_transition(
            session=session,
            audit_session=audit_session,
            device=device,
            new_state=LifecycleState.classified,
            previous_state=previous_state,
            target=None,
            observed=observed,
            actor=actor,
            actor_type=actor_type,
            correlation_id=correlation_id,
            reason="no_target_matched",
        )
        return env

    target = winner.target

    # Target matched, classify on observation -------------------------------
    base_reasons: list[FirmwareComplianceReason] = [
        FirmwareComplianceReason(
            kind="target_matched",
            ref=str(target.id),
            detail=(
                f"target {target.name!r} matched (specificity={winner.specificity}, "
                f"loaded_at={target.loaded_at.isoformat()})"
            ),
        )
    ]
    for ru in runners_up[:3]:
        base_reasons.append(
            FirmwareComplianceReason(
                kind="target_runner_up",
                ref=str(ru.target.id),
                detail=(
                    f"runner-up {ru.target.name!r} also matched (specificity={ru.specificity})"
                ),
            )
        )

    if observed is None:
        state_str = "unknown"
        new_state = LifecycleState.unknown
        base_reasons.append(
            FirmwareComplianceReason(
                kind="missing_observation",
                detail="device has no observed_firmware on file",
            )
        )
    elif observed == target.target_version:
        state_str = "compliant"
        new_state = LifecycleState.compliant
        base_reasons.append(
            FirmwareComplianceReason(
                kind="version_match",
                detail=f"observed_firmware == target_version ({target.target_version!r})",
            )
        )
    else:
        state_str = "outside_target"
        new_state = LifecycleState.outside_target
        base_reasons.append(
            FirmwareComplianceReason(
                kind="version_mismatch",
                detail=(
                    f"observed_firmware={observed!r} != target_version={target.target_version!r}"
                ),
            )
        )

    env = build_firmware_compliance_envelope(
        state=state_str,  # type: ignore[arg-type]
        summary=_summarize(state_str, device, target, observed),
        target_ref=str(target.id),
        target_version=target.target_version,
        observed_version=observed,
        reasons=base_reasons,
        facts={
            "device_id": str(device.id),
            "hostname": device.hostname,
            "target_name": target.name,
        },
        correlation_id=correlation_id,
    )
    _maybe_transition(
        session=session,
        audit_session=audit_session,
        device=device,
        new_state=new_state,
        previous_state=previous_state,
        target=target,
        observed=observed,
        actor=actor,
        actor_type=actor_type,
        correlation_id=correlation_id,
        reason=state_str,
    )
    return env


# ---- transition + audit helper -------------------------------------------


def _maybe_transition(
    *,
    session: Session,
    audit_session: Session,
    device: Device,
    new_state: LifecycleState,
    previous_state: str,
    target: FirmwareTarget | None,
    observed: str | None,
    actor: str,
    actor_type: ActorType,
    correlation_id: str | None,
    reason: str,
) -> None:
    """Persist state change + emit audit. No-op when state is unchanged."""
    if new_state.value == previous_state:
        return
    device.lifecycle_state = new_state
    device.updated_at = dt.datetime.now(dt.UTC)
    session.flush()

    audit_emit(
        session=audit_session,
        action="firmware_target.compliance_evaluated",
        object_type="Device",
        object_id=str(device.id),
        actor=actor,
        actor_type=actor_type,
        before={"lifecycle_state": previous_state},
        after={
            "lifecycle_state": new_state.value,
            "target_ref": str(target.id) if target is not None else None,
            "target_version": target.target_version if target is not None else None,
            "observed_firmware": observed,
            "reason": reason,
        },
        correlation_id=correlation_id,
    )
    _log.info(
        "firmware_compliance.transition",
        device_id=str(device.id),
        from_state=previous_state,
        to_state=new_state.value,
        target_ref=str(target.id) if target is not None else None,
        reason=reason,
    )
