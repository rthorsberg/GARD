"""F5 uplift-wave controller (T022-T023, T036-T039, T051).

Owns the wave lifecycle:

* :func:`draft_wave` — resolve a scope_selector against F4's latest
  ``ready_for_uplift`` verdicts, validate the change window + target
  version, and persist a ``draft`` wave + its device snapshot. Honours
  the ``Idempotency-Key`` contract (R-4 / ADR-0016 §E).
* :func:`submit` / :func:`approve` / :func:`reject` / :func:`cancel` —
  state-machine-guarded transitions applied with an optimistic
  ``UPDATE ... WHERE state=:expected`` (R-7 / ADR-0016 §D). Separation
  of duties (R-2) is enforced via the state machine.
* :func:`invalidate_affected_waves` — system-driven invalidation when
  F4 reverdicts or a target is retired (R-5). Called from the F2
  catalogue reload hook.

Every transition emits exactly one ``audit_events`` row. Device
``lifecycle_state`` transitions are written inside the same SQL
transaction as the wave transition.

All domain-rejection paths raise typed exceptions the router maps to
HTTP envelopes; nothing here knows about FastAPI.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from gard.core import scope_selector as sel
from gard.core import uplift_state_machine as sm
from gard.core.audit import emit as audit_emit
from gard.core.logging import get_correlation_id, get_logger
from gard.core.settings import get_settings
from gard.models import (
    Device,
    FirmwareTarget,
    ReadinessEvaluation,
    UpliftWave,
    UpliftWaveDevice,
    utcnow,
)
from gard.models._enums import ActorType, LifecycleState, WaveState

_log = get_logger(__name__)


# ---- typed domain errors (router maps each to an HTTP envelope) ----------


class WaveNotFound(Exception):  # noqa: N818
    def __init__(self, wave_id: uuid.UUID) -> None:
        self.wave_id = wave_id
        super().__init__(f"uplift wave not found: {wave_id}")


class EmptyWave(Exception):  # noqa: N818
    """Scope resolved to zero eligible devices (422 EMPTY_WAVE)."""


class IneligibleDevicesInScope(Exception):  # noqa: N818
    """mode=strict and the scope contained non-ready devices (422)."""

    def __init__(self, skipped: list[SkippedDevice]) -> None:
        self.skipped = skipped
        super().__init__(f"{len(skipped)} ineligible device(s) in scope (mode=strict)")


class InvalidChangeWindow(Exception):  # noqa: N818
    """Change window failed the grammar (422 INVALID_CHANGE_WINDOW)."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class TargetVersionNotLive(Exception):  # noqa: N818
    """No live FirmwareTarget matches (platform_family, target_version)."""

    def __init__(self, *, platform_family: str, target_version: str) -> None:
        self.platform_family = platform_family
        self.target_version = target_version
        super().__init__(
            f"target_version {target_version!r} is not live for platform {platform_family!r}"
        )


class WaveTooLarge(Exception):  # noqa: N818
    """Eligible device count exceeds the per-wave cap (413 WAVE_TOO_LARGE)."""

    def __init__(self, *, count: int, cap: int) -> None:
        self.count = count
        self.cap = cap
        super().__init__(f"wave would contain {count} devices, cap is {cap}")


class WaveStateMismatch(Exception):  # noqa: N818
    """Optimistic guard lost the race (409 WAVE_STATE_MISMATCH)."""

    def __init__(self, *, expected: str, actual: str | None) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"wave state mismatch: expected {expected!r}, found {actual!r}")


# ---- structured carriers -------------------------------------------------


@dataclass(frozen=True, slots=True)
class SkippedDevice:
    device_id: uuid.UUID
    reason: str
    current_readiness_state: str | None


@dataclass(slots=True)
class WaveDraftOutcome:
    wave: UpliftWave
    members: list[tuple[Device, UpliftWaveDevice]]
    skipped: list[SkippedDevice] = field(default_factory=list)
    replayed: bool = False


# ---- internal helpers ----------------------------------------------------


def _device_facts(device: Device) -> dict[str, object]:
    return {
        "vendor_normalized": device.vendor_normalized,
        "platform_family": device.platform_family,
        "region": device.region,
        "site": device.site,
        "role": device.role,
        "hardware_revision": device.hardware_revision,
        "lifecycle_state": device.lifecycle_state.value,
    }


def _validate_change_window(start: dt.datetime, end: dt.datetime) -> None:
    settings = get_settings()
    now = dt.datetime.now(dt.UTC)
    if start.tzinfo is None or end.tzinfo is None:
        raise InvalidChangeWindow("change_window timestamps must be timezone-aware (UTC)")
    if start <= now:
        raise InvalidChangeWindow("change_window_start must be in the future")
    if end <= start:
        raise InvalidChangeWindow("change_window_end must be after change_window_start")
    duration = end - start
    min_delta = dt.timedelta(minutes=settings.uplift_change_window_min_minutes)
    max_delta = dt.timedelta(hours=settings.uplift_change_window_max_hours)
    if duration < min_delta:
        raise InvalidChangeWindow(
            f"change_window must be at least {settings.uplift_change_window_min_minutes} minutes"
        )
    if duration > max_delta:
        raise InvalidChangeWindow(
            f"change_window must be at most {settings.uplift_change_window_max_hours} hours"
        )


def _assert_target_live(
    session: Session,
    *,
    platform_family: str,
    target_version: str,
) -> None:
    row = session.scalar(
        select(FirmwareTarget.id)
        .where(FirmwareTarget.removed_at.is_(None))
        .where(FirmwareTarget.platform_family == platform_family)
        .where(FirmwareTarget.target_version == target_version)
        .limit(1)
    )
    if row is None:
        raise TargetVersionNotLive(platform_family=platform_family, target_version=target_version)


def _latest_readiness(session: Session, device_id: uuid.UUID) -> ReadinessEvaluation | None:
    return session.scalar(
        select(ReadinessEvaluation)
        .where(ReadinessEvaluation.device_id == device_id)
        .order_by(ReadinessEvaluation.evaluated_at.desc())
        .limit(1)
    )


def load_wave_members(
    session: Session, wave_id: uuid.UUID
) -> list[tuple[Device, UpliftWaveDevice]]:
    """Return (device, join-row) tuples ordered by wave position."""
    q = (
        select(Device, UpliftWaveDevice)
        .join(UpliftWaveDevice, UpliftWaveDevice.device_id == Device.id)
        .where(UpliftWaveDevice.wave_id == wave_id)
        .order_by(UpliftWaveDevice.position)
    )
    return [(d, wd) for d, wd in session.execute(q).all()]


def _revert_pending_members_to_ready(session: Session, wave_id: uuid.UUID) -> None:
    """Devices still at ``approval_pending`` return to ``ready_for_uplift``.

    Used on reject / cancel / invalidate of a submitted wave. Devices
    that F4 already re-verdicted (e.g. to ``blocked``) are NOT touched —
    only those still parked at ``approval_pending`` by this wave's
    submit are reverted.
    """
    members = load_wave_members(session, wave_id)
    for device, _wd in members:
        if device.lifecycle_state == LifecycleState.approval_pending:
            device.lifecycle_state = LifecycleState.ready_for_uplift


def _apply_state_guard(
    session: Session,
    *,
    wave_id: uuid.UUID,
    expected: WaveState,
    values: dict[str, object],
) -> UpliftWave:
    """Optimistic ``UPDATE ... WHERE state=:expected`` (ADR-0016 §D).

    Returns the refreshed wave on success; raises
    :class:`WaveStateMismatch` when another caller won the race.
    """
    stmt = (
        update(UpliftWave)
        .where(UpliftWave.id == wave_id, UpliftWave.state == expected.value)
        .values(**values)
        .returning(UpliftWave.id)
    )
    won = session.execute(stmt).first()
    if won is None:
        actual = session.get(UpliftWave, wave_id)
        raise WaveStateMismatch(
            expected=expected.value,
            actual=actual.state if actual is not None else None,
        )
    session.expire_all()
    refreshed = session.get(UpliftWave, wave_id)
    assert refreshed is not None  # noqa: S101 — just updated it
    return refreshed


@dataclass(frozen=True, slots=True)
class WaveDraftPreview:
    """Read-shaped wave draft proposal (R-9) — no DB writes."""

    proposed_devices: int
    skipped: list[SkippedDevice]
    device_rows: list[dict[str, object]]
    change_window_valid: bool
    target_version_live: bool
    warnings: list[str]


def preview_wave_draft(
    session: Session,
    *,
    target_version: str,
    target_platform_family: str,
    scope_selector: dict[str, object],
    mode: str,
    change_window_start: dt.datetime,
    change_window_end: dt.datetime,
) -> WaveDraftPreview:
    """Resolve scope against F4 verdicts without persisting (R-9)."""
    warnings: list[str] = []
    change_window_valid = True
    target_version_live = True
    try:
        _validate_change_window(change_window_start, change_window_end)
    except InvalidChangeWindow as exc:
        change_window_valid = False
        warnings.append(str(exc))
    try:
        _assert_target_live(
            session,
            platform_family=target_platform_family,
            target_version=target_version,
        )
    except TargetVersionNotLive as exc:
        target_version_live = False
        warnings.append(str(exc))

    sel.validate_keys(scope_selector)
    devices = list(session.scalars(select(Device)))

    eligible: list[tuple[Device, ReadinessEvaluation | None]] = []
    skipped: list[SkippedDevice] = []
    for device in devices:
        if not sel.evaluate(scope_selector, _device_facts(device)).matched:
            continue
        latest = _latest_readiness(session, device.id)
        state = latest.readiness_state if latest is not None else None
        if state == "ready_for_uplift":
            eligible.append((device, latest))
        else:
            skipped.append(
                SkippedDevice(
                    device_id=device.id,
                    reason="not ready_for_uplift",
                    current_readiness_state=state,
                )
            )

    if mode == "strict" and skipped:
        warnings.append(f"{len(skipped)} ineligible device(s) in scope (mode=strict)")
    if not eligible:
        warnings.append("scope resolved to zero ready_for_uplift devices")

    eligible.sort(key=lambda pair: str(pair[0].id))
    device_rows: list[dict[str, object]] = []
    for device, latest in eligible:
        device_rows.append(
            {
                "device_id": str(device.id),
                "hostname": device.hostname,
                "readiness_state": latest.readiness_state if latest else None,
                "target_version": latest.target_version if latest else None,
                "observed_version": latest.observed_version if latest else None,
            }
        )

    return WaveDraftPreview(
        proposed_devices=len(eligible),
        skipped=skipped if mode != "strict" else [],
        device_rows=device_rows,
        change_window_valid=change_window_valid,
        target_version_live=target_version_live,
        warnings=warnings,
    )


# ---- draft (T022-T023) ---------------------------------------------------


def draft_wave(
    *,
    session: Session,
    audit_session: Session,
    plan_id: uuid.UUID,
    name: str,
    target_version: str,
    target_platform_family: str,
    scope_selector: dict[str, object],
    mode: str,
    change_window_start: dt.datetime,
    change_window_end: dt.datetime,
    idempotency_key: str | None,
    actor: str,
    actor_type: ActorType,
) -> WaveDraftOutcome:
    """Draft a wave from the ``ready_for_uplift`` pool (no lifecycle change)."""
    settings = get_settings()
    correlation_id = get_correlation_id() or "unknown"

    # R-4 idempotency: replay within TTL returns the original row.
    if idempotency_key is not None:
        existing = session.scalar(
            select(UpliftWave)
            .where(UpliftWave.plan_id == plan_id)
            .where(UpliftWave.idempotency_key == idempotency_key)
        )
        if existing is not None:
            now = dt.datetime.now(dt.UTC)
            age = (now - existing.drafted_at).total_seconds()
            if age <= settings.uplift_idempotency_ttl_seconds:
                return WaveDraftOutcome(
                    wave=existing,
                    members=load_wave_members(session, existing.id),
                    skipped=[],
                    replayed=True,
                )
            # Past TTL: free the unique key so a fresh wave can reuse it.
            existing.idempotency_key = None
            session.flush()

    _validate_change_window(change_window_start, change_window_end)
    _assert_target_live(
        session,
        platform_family=target_platform_family,
        target_version=target_version,
    )

    sel.validate_keys(scope_selector)
    devices = list(session.scalars(select(Device)))

    eligible: list[tuple[Device, ReadinessEvaluation | None]] = []
    skipped: list[SkippedDevice] = []
    for device in devices:
        if not sel.evaluate(scope_selector, _device_facts(device)).matched:
            continue
        latest = _latest_readiness(session, device.id)
        state = latest.readiness_state if latest is not None else None
        if state == "ready_for_uplift":
            eligible.append((device, latest))
        else:
            skipped.append(
                SkippedDevice(
                    device_id=device.id,
                    reason="not ready_for_uplift",
                    current_readiness_state=state,
                )
            )

    if mode == "strict" and skipped:
        raise IneligibleDevicesInScope(skipped)
    if mode == "strict":
        skipped = []  # strict + all-eligible: nothing skipped

    if not eligible:
        raise EmptyWave("scope_selector resolved to zero ready_for_uplift devices")

    if len(eligible) > settings.uplift_wave_max_devices:
        raise WaveTooLarge(count=len(eligible), cap=settings.uplift_wave_max_devices)

    # Deterministic ordering: sort eligible by device id for stable positions.
    eligible.sort(key=lambda pair: str(pair[0].id))

    wave = UpliftWave(
        plan_id=plan_id,
        name=name,
        target_version=target_version,
        target_platform_family=target_platform_family,
        change_window_start=change_window_start,
        change_window_end=change_window_end,
        state=WaveState.draft.value,
        drafted_by=actor,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )
    session.add(wave)
    session.flush()

    members: list[tuple[Device, UpliftWaveDevice]] = []
    for position, (device, latest) in enumerate(eligible, start=1):
        wd = UpliftWaveDevice(
            wave_id=wave.id,
            device_id=device.id,
            position=position,
            readiness_evaluation_ref=latest.id if latest is not None else None,
            snapshot_target_version=latest.target_version if latest is not None else None,
            snapshot_observed_version=(latest.observed_version if latest is not None else None),
        )
        session.add(wd)
        members.append((device, wd))
    session.flush()

    audit_emit(
        session=audit_session,
        action="uplift_wave.drafted",
        object_type="UpliftWave",
        object_id=str(wave.id),
        actor=actor,
        actor_type=actor_type,
        before=None,
        after={
            "id": str(wave.id),
            "plan_id": str(plan_id),
            "name": name,
            "target_version": target_version,
            "device_count": len(members),
            "skipped_count": len(skipped),
            "mode": mode,
        },
        correlation_id=correlation_id,
    )
    _log.info(
        "uplift_wave.drafted",
        wave_id=str(wave.id),
        device_count=len(members),
        skipped=len(skipped),
    )
    return WaveDraftOutcome(wave=wave, members=members, skipped=skipped, replayed=False)


# ---- submit (T036) -------------------------------------------------------


def submit(
    *,
    session: Session,
    audit_session: Session,
    wave_id: uuid.UUID,
    actor: str,
    actor_type: ActorType,
) -> UpliftWave:
    wave = session.get(UpliftWave, wave_id)
    if wave is None:
        raise WaveNotFound(wave_id)
    # State-machine validation (raises TransitionForbidden etc.).
    sm.wave_decide(
        from_state=WaveState(wave.state),
        to_state=WaveState.submitted,
        actor_kind="drafter",
        actor_subject=actor,
        drafter_subject=wave.drafted_by,
    )
    now = utcnow()
    refreshed = _apply_state_guard(
        session,
        wave_id=wave_id,
        expected=WaveState.draft,
        values={"state": WaveState.submitted.value, "submitted_by": actor, "submitted_at": now},
    )

    # Devices: ready_for_uplift → approval_pending.
    for device, _wd in load_wave_members(session, wave_id):
        if device.lifecycle_state == LifecycleState.ready_for_uplift:
            device.lifecycle_state = LifecycleState.approval_pending

    audit_emit(
        session=audit_session,
        action="uplift_wave.submitted",
        object_type="UpliftWave",
        object_id=str(wave_id),
        actor=actor,
        actor_type=actor_type,
        before={"state": WaveState.draft.value},
        after={"state": WaveState.submitted.value},
        correlation_id=get_correlation_id(),
    )
    _log.info("uplift_wave.submitted", wave_id=str(wave_id))
    return refreshed


# ---- approve (T037) ------------------------------------------------------


def approve(
    *,
    session: Session,
    audit_session: Session,
    wave_id: uuid.UUID,
    citation: str,
    actor: str,
    actor_type: ActorType,
) -> UpliftWave:
    wave = session.get(UpliftWave, wave_id)
    if wave is None:
        raise WaveNotFound(wave_id)
    # SoD + transition validation. Raises SelfApprovalForbidden (→403)
    # or TransitionForbidden (→409) before any write.
    sm.wave_decide(
        from_state=WaveState(wave.state),
        to_state=WaveState.approved,
        actor_kind="approver",
        actor_subject=actor,
        drafter_subject=wave.drafted_by,
    )
    now = utcnow()
    refreshed = _apply_state_guard(
        session,
        wave_id=wave_id,
        expected=WaveState.submitted,
        values={
            "state": WaveState.approved.value,
            "approved_by": actor,
            "approved_at": now,
            "approval_citation": citation,
        },
    )

    # Devices: approval_pending → approved.
    for device, _wd in load_wave_members(session, wave_id):
        if device.lifecycle_state == LifecycleState.approval_pending:
            device.lifecycle_state = LifecycleState.approved

    audit_emit(
        session=audit_session,
        action="uplift_wave.approved",
        object_type="UpliftWave",
        object_id=str(wave_id),
        actor=actor,
        actor_type=actor_type,
        before={"state": WaveState.submitted.value},
        after={
            "state": WaveState.approved.value,
            "approved_by": actor,
            "citation": citation,
        },
        correlation_id=get_correlation_id(),
    )
    _log.info("uplift_wave.approved", wave_id=str(wave_id), approver=actor)
    return refreshed


# ---- reject (T038) -------------------------------------------------------


def reject(
    *,
    session: Session,
    audit_session: Session,
    wave_id: uuid.UUID,
    citation: str,
    actor: str,
    actor_type: ActorType,
) -> UpliftWave:
    wave = session.get(UpliftWave, wave_id)
    if wave is None:
        raise WaveNotFound(wave_id)
    self_rejection = actor == wave.drafted_by
    sm.wave_decide(
        from_state=WaveState(wave.state),
        to_state=WaveState.rejected,
        actor_kind="drafter" if self_rejection else "approver",
        actor_subject=actor,
        drafter_subject=wave.drafted_by,
    )
    now = utcnow()
    refreshed = _apply_state_guard(
        session,
        wave_id=wave_id,
        expected=WaveState.submitted,
        values={
            "state": WaveState.rejected.value,
            "rejected_by": actor,
            "rejected_at": now,
            "rejection_citation": citation,
        },
    )
    _revert_pending_members_to_ready(session, wave_id)

    audit_emit(
        session=audit_session,
        action="uplift_wave.rejected",
        object_type="UpliftWave",
        object_id=str(wave_id),
        actor=actor,
        actor_type=actor_type,
        before={"state": WaveState.submitted.value},
        after={
            "state": WaveState.rejected.value,
            "rejected_by": actor,
            "citation": citation,
            "self_rejection": self_rejection,
        },
        correlation_id=get_correlation_id(),
    )
    _log.info("uplift_wave.rejected", wave_id=str(wave_id), self_rejection=self_rejection)
    return refreshed


# ---- cancel (T039) -------------------------------------------------------


def cancel(
    *,
    session: Session,
    audit_session: Session,
    wave_id: uuid.UUID,
    reason: str,
    actor: str,
    actor_type: ActorType,
) -> UpliftWave:
    """Cancel a draft or submitted wave.

    The router gates *who* may cancel (drafter OR ``APPROVE_UPLIFT_WAVE``
    holder); by the time we get here the caller is authorised, so we
    drive the state machine with ``actor_kind="drafter"``.
    """
    wave = session.get(UpliftWave, wave_id)
    if wave is None:
        raise WaveNotFound(wave_id)
    current = WaveState(wave.state)
    sm.wave_decide(
        from_state=current,
        to_state=WaveState.cancelled,
        actor_kind="drafter",
        actor_subject=actor,
        drafter_subject=wave.drafted_by,
    )
    now = utcnow()
    refreshed = _apply_state_guard(
        session,
        wave_id=wave_id,
        expected=current,
        values={
            "state": WaveState.cancelled.value,
            "cancelled_by": actor,
            "cancelled_at": now,
            "cancellation_reason": reason,
        },
    )
    if current == WaveState.submitted:
        _revert_pending_members_to_ready(session, wave_id)

    audit_emit(
        session=audit_session,
        action="uplift_wave.cancelled",
        object_type="UpliftWave",
        object_id=str(wave_id),
        actor=actor,
        actor_type=actor_type,
        before={"state": current.value},
        after={"state": WaveState.cancelled.value, "reason": reason},
        correlation_id=get_correlation_id(),
    )
    _log.info("uplift_wave.cancelled", wave_id=str(wave_id))
    return refreshed


# ---- invalidation hook (T051) --------------------------------------------


def invalidate_affected_waves(
    session: Session,
    audit_session: Session,
    *,
    affected_device_ids: set[uuid.UUID],
    actor: str = "system",
    actor_type: ActorType = ActorType.system,
) -> int:
    """Invalidate every non-terminal wave containing an affected device.

    Called from the F2 catalogue reload hook AFTER the F4 pass has
    already re-verdicted the affected devices. We do not re-derive
    device lifecycle here — F4 owns that — except to release any wave
    member still parked at ``approval_pending`` back to
    ``ready_for_uplift`` (devices the wave moved that F4 didn't touch).

    Returns the number of waves invalidated.
    """
    if not affected_device_ids:
        return 0

    non_terminal = (WaveState.draft.value, WaveState.submitted.value)
    candidate_wave_ids = set(
        session.scalars(
            select(UpliftWave.id)
            .join(UpliftWaveDevice, UpliftWaveDevice.wave_id == UpliftWave.id)
            .where(UpliftWave.state.in_(non_terminal))
            .where(UpliftWaveDevice.device_id.in_(affected_device_ids))
        )
    )
    if not candidate_wave_ids:
        return 0

    correlation_id = get_correlation_id()
    count = 0
    for wave_id in candidate_wave_ids:
        wave = session.get(UpliftWave, wave_id)
        if wave is None:
            continue
        current = WaveState(wave.state)
        if current not in (WaveState.draft, WaveState.submitted):
            continue
        # Reason: target retired if the wave's target_version is no
        # longer live, else an F4 reverdict triggered this.
        live = session.scalar(
            select(FirmwareTarget.id)
            .where(FirmwareTarget.removed_at.is_(None))
            .where(FirmwareTarget.platform_family == wave.target_platform_family)
            .where(FirmwareTarget.target_version == wave.target_version)
            .limit(1)
        )
        reason = "target_retired" if live is None else "f4_reverdict"
        now = utcnow()
        try:
            _apply_state_guard(
                session,
                wave_id=wave_id,
                expected=current,
                values={
                    "state": WaveState.invalidated.value,
                    "invalidated_at": now,
                    "invalidated_reason": reason,
                },
            )
        except WaveStateMismatch:  # pragma: no cover - racing terminal transition
            continue
        if current == WaveState.submitted:
            _revert_pending_members_to_ready(session, wave_id)

        audit_emit(
            session=audit_session,
            action="uplift_wave.invalidated",
            object_type="UpliftWave",
            object_id=str(wave_id),
            actor=actor,
            actor_type=actor_type,
            before={"state": current.value},
            after={"state": WaveState.invalidated.value, "reason": reason},
            correlation_id=correlation_id,
        )
        count += 1

    if count:
        _log.info("uplift_wave.invalidated_batch", waves=count)
    return count


# ---- reads ---------------------------------------------------------------


def get_wave(session: Session, wave_id: uuid.UUID) -> UpliftWave | None:
    return session.get(UpliftWave, wave_id)


def list_waves(
    session: Session,
    *,
    plan_id: uuid.UUID | None = None,
    state: str | None = None,
    target_version: str | None = None,
    region: str | None = None,
    site: str | None = None,
    platform_family: str | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
) -> tuple[list[UpliftWave], uuid.UUID | None]:
    """Page of waves (id-descending cursor).

    ``region`` / ``site`` filter on membership: a wave matches when at
    least one of its devices is in that region/site. ``platform_family``
    filters on the wave's own ``target_platform_family``.
    """
    q = select(UpliftWave)
    if plan_id is not None:
        q = q.where(UpliftWave.plan_id == plan_id)
    if state is not None:
        q = q.where(UpliftWave.state == state)
    if target_version is not None:
        q = q.where(UpliftWave.target_version == target_version)
    if platform_family is not None:
        q = q.where(UpliftWave.target_platform_family == platform_family)
    if region is not None or site is not None:
        member_q = (
            select(UpliftWaveDevice.wave_id)
            .join(Device, Device.id == UpliftWaveDevice.device_id)
            .distinct()
        )
        if region is not None:
            member_q = member_q.where(Device.region == region)
        if site is not None:
            member_q = member_q.where(Device.site == site)
        q = q.where(UpliftWave.id.in_(member_q))
    if after_id is not None:
        q = q.where(UpliftWave.id < after_id)
    q = q.order_by(UpliftWave.id.desc()).limit(limit)

    waves = list(session.scalars(q))
    next_after = waves[-1].id if len(waves) == limit else None
    return waves, next_after


__all__ = [
    "EmptyWave",
    "IneligibleDevicesInScope",
    "InvalidChangeWindow",
    "SkippedDevice",
    "TargetVersionNotLive",
    "WaveDraftOutcome",
    "WaveDraftPreview",
    "WaveNotFound",
    "WaveStateMismatch",
    "WaveTooLarge",
    "approve",
    "cancel",
    "draft_wave",
    "get_wave",
    "invalidate_affected_waves",
    "list_waves",
    "load_wave_members",
    "preview_wave_draft",
    "reject",
    "submit",
]
