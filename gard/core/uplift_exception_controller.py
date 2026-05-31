"""F5 uplift-exception controller (T059-T062).

Owns the exception lifecycle:

* :func:`file_exception` — validate ``blocked`` device + blocker in the
  latest F4 row; persist ``pending_review`` (no lifecycle change).
* :func:`approve_exception` / :func:`reject_exception` /
  :func:`withdraw_exception` — state-machine-guarded transitions.
* :func:`expire_overdue_exceptions` — lazy expiry sweep (R-6) invoked
  at the top of F4 :func:`evaluate`.

Every transition emits exactly one ``audit_events`` row.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from gard.core import uplift_state_machine as sm
from gard.core.audit import emit as audit_emit
from gard.core.logging import get_correlation_id, get_logger
from gard.core.settings import get_settings
from gard.models import Device, ReadinessEvaluation, UpliftException, utcnow
from gard.models._enums import ActorType, ExceptionState, LifecycleState

_log = get_logger(__name__)

_ACTIVE_EXCEPTION_STATES = frozenset(
    {ExceptionState.pending_review.value, ExceptionState.approved.value}
)


class ExceptionNotFound(Exception):  # noqa: N818
    def __init__(self, exception_id: uuid.UUID) -> None:
        self.exception_id = exception_id
        super().__init__(f"uplift exception not found: {exception_id}")


class DeviceNotBlocked(Exception):  # noqa: N818
    """Device is not in blocked lifecycle/readiness state (422)."""


class BlockerNotInLatestVerdict(Exception):  # noqa: N818
    """The cited blocker is absent from the latest F4 row (422)."""


class InvalidExceptionExpiry(Exception):  # noqa: N818
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class ExceptionAlreadyActive(Exception):  # noqa: N818
    def __init__(self, *, existing_id: uuid.UUID) -> None:
        self.existing_id = existing_id
        super().__init__(f"active exception already exists: {existing_id}")


class ExceptionStateMismatch(Exception):  # noqa: N818
    def __init__(self, *, expected: str, actual: str | None) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"exception state mismatch: expected {expected!r}, found {actual!r}")


@dataclass(frozen=True, slots=True)
class ExceptionListPage:
    exceptions: list[UpliftException]
    next_after_id: uuid.UUID | None


def _latest_readiness(session: Session, device_id: uuid.UUID) -> ReadinessEvaluation | None:
    return session.scalar(
        select(ReadinessEvaluation)
        .where(ReadinessEvaluation.device_id == device_id)
        .order_by(ReadinessEvaluation.evaluated_at.desc())
        .limit(1)
    )


def _blocker_key(*, blocker_rule_id: uuid.UUID | None, synthetic_kind: str | None) -> str:
    if blocker_rule_id is not None:
        return str(blocker_rule_id)
    if synthetic_kind is None:
        raise ValueError("synthetic_kind required when blocker_rule_id is absent")
    return synthetic_kind


def _blocker_in_readiness(
    latest: ReadinessEvaluation,
    *,
    blocker_rule_id: uuid.UUID | None,
    synthetic_kind: str | None,
) -> bool:
    for raw in latest.blockers or []:
        if blocker_rule_id is not None and raw.get("rule_id") == str(blocker_rule_id):
            return True
        if (
            synthetic_kind is not None
            and raw.get("rule_id") is None
            and raw.get("predicate_kind") == synthetic_kind
        ):
            return True
    return False


def _find_conflicting_active(
    session: Session,
    *,
    device_id: uuid.UUID,
    blocker_rule_id: uuid.UUID | None,
    synthetic_kind: str | None,
) -> UpliftException | None:
    q = (
        select(UpliftException)
        .where(UpliftException.device_id == device_id)
        .where(UpliftException.state.in_(_ACTIVE_EXCEPTION_STATES))
    )
    if blocker_rule_id is not None:
        q = q.where(UpliftException.blocker_rule_id == blocker_rule_id)
    else:
        q = q.where(UpliftException.synthetic_kind == synthetic_kind)
    return session.scalar(q.order_by(UpliftException.filed_at.desc()).limit(1))


def find_active_approved_exception(
    session: Session,
    device_id: uuid.UUID,
    *,
    now: dt.datetime | None = None,
) -> UpliftException | None:
    """Return a non-expired ``approved`` exception for ``device_id``, if any."""
    ts = now or utcnow()
    return session.scalar(
        select(UpliftException)
        .where(UpliftException.device_id == device_id)
        .where(UpliftException.state == ExceptionState.approved.value)
        .where(UpliftException.expires_at > ts)
        .order_by(UpliftException.approved_at.desc().nullslast())
        .limit(1)
    )


def _validate_expires_at(expires_at: dt.datetime, *, filed_at: dt.datetime) -> None:
    if expires_at.tzinfo is None:
        raise InvalidExceptionExpiry("expires_at must be timezone-aware (UTC)")
    settings = get_settings()
    now = utcnow()
    if expires_at <= now:
        raise InvalidExceptionExpiry("expires_at must be in the future")
    if expires_at <= filed_at:
        raise InvalidExceptionExpiry("expires_at must be after filed_at")
    max_end = filed_at + dt.timedelta(days=settings.exception_max_lifetime_days)
    if expires_at > max_end:
        raise InvalidExceptionExpiry(
            f"expires_at exceeds maximum lifetime of {settings.exception_max_lifetime_days} days"
        )


def _apply_state_guard(
    session: Session,
    *,
    exception_id: uuid.UUID,
    expected: ExceptionState,
    values: dict[str, object],
) -> UpliftException:
    stmt = (
        update(UpliftException)
        .where(UpliftException.id == exception_id, UpliftException.state == expected.value)
        .values(**values)
        .returning(UpliftException.id)
    )
    won = session.execute(stmt).first()
    if won is None:
        actual = session.get(UpliftException, exception_id)
        raise ExceptionStateMismatch(
            expected=expected.value,
            actual=actual.state if actual is not None else None,
        )
    session.expire_all()
    refreshed = session.get(UpliftException, exception_id)
    assert refreshed is not None  # noqa: S101
    return refreshed


def file_exception(
    *,
    session: Session,
    audit_session: Session,
    device_id: uuid.UUID,
    blocker_rule_id: uuid.UUID | None,
    synthetic_kind: str | None,
    justification: str,
    expires_at: dt.datetime,
    actor: str,
    actor_type: ActorType,
) -> UpliftException:
    if (blocker_rule_id is None) == (synthetic_kind is None):
        raise ValueError("exactly one of blocker_rule_id or synthetic_kind is required")

    device = session.get(Device, device_id)
    if device is None:
        raise ValueError(f"device not found: {device_id}")

    if device.lifecycle_state != LifecycleState.blocked:
        raise DeviceNotBlocked(
            f"device {device_id} lifecycle_state={device.lifecycle_state.value!r}; "
            "expected 'blocked'"
        )

    latest = _latest_readiness(session, device_id)
    if latest is None or latest.readiness_state != "blocked":
        raise DeviceNotBlocked(f"device {device_id} latest readiness_state is not 'blocked'")

    if not _blocker_in_readiness(
        latest, blocker_rule_id=blocker_rule_id, synthetic_kind=synthetic_kind
    ):
        raise BlockerNotInLatestVerdict(
            "cited blocker is not present in the latest readiness evaluation"
        )

    conflict = _find_conflicting_active(
        session,
        device_id=device_id,
        blocker_rule_id=blocker_rule_id,
        synthetic_kind=synthetic_kind,
    )
    if conflict is not None:
        raise ExceptionAlreadyActive(existing_id=conflict.id)

    filed_at = utcnow()
    _validate_expires_at(expires_at, filed_at=filed_at)
    correlation_id = get_correlation_id() or "unknown"

    exc = UpliftException(
        device_id=device_id,
        blocker_rule_id=blocker_rule_id,
        synthetic_kind=synthetic_kind,
        justification=justification,
        expires_at=expires_at,
        state=ExceptionState.pending_review.value,
        filed_by=actor,
        filed_at=filed_at,
        correlation_id=correlation_id,
    )
    session.add(exc)
    session.flush()

    audit_emit(
        session=audit_session,
        action="uplift_exception.filed",
        object_type="UpliftException",
        object_id=str(exc.id),
        actor=actor,
        actor_type=actor_type,
        before=None,
        after={
            "id": str(exc.id),
            "device_id": str(device_id),
            "blocker": _blocker_key(blocker_rule_id=blocker_rule_id, synthetic_kind=synthetic_kind),
            "state": ExceptionState.pending_review.value,
        },
        correlation_id=correlation_id,
    )
    _log.info("uplift_exception.filed", exception_id=str(exc.id), device_id=str(device_id))
    return exc


def approve_exception(
    *,
    session: Session,
    audit_session: Session,
    exception_id: uuid.UUID,
    actor: str,
    actor_type: ActorType,
) -> UpliftException:
    exc = session.get(UpliftException, exception_id)
    if exc is None:
        raise ExceptionNotFound(exception_id)

    sm.exception_decide(
        from_state=ExceptionState(exc.state),
        to_state=ExceptionState.approved,
        actor_kind="approver",
        actor_subject=actor,
        filer_subject=exc.filed_by,
    )

    device = session.get(Device, exc.device_id)
    if device is None or device.lifecycle_state != LifecycleState.blocked:
        raise DeviceNotBlocked("device must be blocked when approving an exception")

    now = utcnow()
    refreshed = _apply_state_guard(
        session,
        exception_id=exception_id,
        expected=ExceptionState.pending_review,
        values={
            "state": ExceptionState.approved.value,
            "approved_by": actor,
            "approved_at": now,
        },
    )
    device.lifecycle_state = LifecycleState.exception_approved

    audit_emit(
        session=audit_session,
        action="uplift_exception.approved",
        object_type="UpliftException",
        object_id=str(exception_id),
        actor=actor,
        actor_type=actor_type,
        before={"state": ExceptionState.pending_review.value},
        after={"state": ExceptionState.approved.value, "approved_by": actor},
        correlation_id=get_correlation_id(),
    )
    _log.info("uplift_exception.approved", exception_id=str(exception_id))
    return refreshed


def reject_exception(
    *,
    session: Session,
    audit_session: Session,
    exception_id: uuid.UUID,
    actor: str,
    actor_type: ActorType,
) -> UpliftException:
    exc = session.get(UpliftException, exception_id)
    if exc is None:
        raise ExceptionNotFound(exception_id)

    sm.exception_decide(
        from_state=ExceptionState(exc.state),
        to_state=ExceptionState.rejected,
        actor_kind="approver",
        actor_subject=actor,
        filer_subject=exc.filed_by,
    )

    now = utcnow()
    refreshed = _apply_state_guard(
        session,
        exception_id=exception_id,
        expected=ExceptionState.pending_review,
        values={
            "state": ExceptionState.rejected.value,
            "rejected_by": actor,
            "rejected_at": now,
        },
    )

    audit_emit(
        session=audit_session,
        action="uplift_exception.rejected",
        object_type="UpliftException",
        object_id=str(exception_id),
        actor=actor,
        actor_type=actor_type,
        before={"state": ExceptionState.pending_review.value},
        after={"state": ExceptionState.rejected.value},
        correlation_id=get_correlation_id(),
    )
    _log.info("uplift_exception.rejected", exception_id=str(exception_id))
    return refreshed


def withdraw_exception(
    *,
    session: Session,
    audit_session: Session,
    exception_id: uuid.UUID,
    actor: str,
    actor_type: ActorType,
) -> UpliftException:
    exc = session.get(UpliftException, exception_id)
    if exc is None:
        raise ExceptionNotFound(exception_id)

    current = ExceptionState(exc.state)
    sm.exception_decide(
        from_state=current,
        to_state=ExceptionState.withdrawn,
        actor_kind="filer",
        actor_subject=actor,
        filer_subject=exc.filed_by,
    )

    now = utcnow()
    refreshed = _apply_state_guard(
        session,
        exception_id=exception_id,
        expected=current,
        values={
            "state": ExceptionState.withdrawn.value,
            "withdrawn_by": actor,
            "withdrawn_at": now,
        },
    )

    if current == ExceptionState.approved:
        device = session.get(Device, exc.device_id)
        if device is not None and device.lifecycle_state == LifecycleState.exception_approved:
            device.lifecycle_state = LifecycleState.blocked

    audit_emit(
        session=audit_session,
        action="uplift_exception.withdrawn",
        object_type="UpliftException",
        object_id=str(exception_id),
        actor=actor,
        actor_type=actor_type,
        before={"state": current.value},
        after={"state": ExceptionState.withdrawn.value},
        correlation_id=get_correlation_id(),
    )
    _log.info("uplift_exception.withdrawn", exception_id=str(exception_id))
    return refreshed


def expire_overdue_exceptions(
    *,
    session: Session,
    audit_session: Session,
    device_id: uuid.UUID,
    actor: str = "system",
    actor_type: ActorType = ActorType.system,
) -> list[uuid.UUID]:
    """Transition approved-and-past-expiry rows to ``expired`` (R-6)."""
    now = utcnow()
    correlation_id = get_correlation_id() or "unknown"
    overdue = list(
        session.scalars(
            select(UpliftException)
            .where(UpliftException.device_id == device_id)
            .where(UpliftException.state == ExceptionState.approved.value)
            .where(UpliftException.expires_at < now)
        )
    )
    expired_ids: list[uuid.UUID] = []
    for exc in overdue:
        try:
            _apply_state_guard(
                session,
                exception_id=exc.id,
                expected=ExceptionState.approved,
                values={
                    "state": ExceptionState.expired.value,
                    "expired_at": now,
                },
            )
        except ExceptionStateMismatch:  # pragma: no cover - racing withdraw
            continue

        device = session.get(Device, device_id)
        if device is not None and device.lifecycle_state == LifecycleState.exception_approved:
            device.lifecycle_state = LifecycleState.blocked

        audit_emit(
            session=audit_session,
            action="uplift_exception.expired",
            object_type="UpliftException",
            object_id=str(exc.id),
            actor=actor,
            actor_type=actor_type,
            before={"state": ExceptionState.approved.value},
            after={"state": ExceptionState.expired.value},
            correlation_id=correlation_id,
        )
        expired_ids.append(exc.id)
        _log.info("uplift_exception.expired", exception_id=str(exc.id))

    return expired_ids


def get_exception(session: Session, exception_id: uuid.UUID) -> UpliftException | None:
    return session.get(UpliftException, exception_id)


def list_exceptions(
    session: Session,
    *,
    device_id: uuid.UUID | None = None,
    state: str | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
) -> ExceptionListPage:
    q = select(UpliftException)
    if device_id is not None:
        q = q.where(UpliftException.device_id == device_id)
    if state is not None:
        q = q.where(UpliftException.state == state)
    if after_id is not None:
        q = q.where(UpliftException.id < after_id)
    q = q.order_by(UpliftException.id.desc()).limit(limit)
    rows = list(session.scalars(q))
    next_after = rows[-1].id if len(rows) == limit else None
    return ExceptionListPage(exceptions=rows, next_after_id=next_after)


__all__ = [
    "BlockerNotInLatestVerdict",
    "DeviceNotBlocked",
    "ExceptionAlreadyActive",
    "ExceptionListPage",
    "ExceptionNotFound",
    "ExceptionStateMismatch",
    "InvalidExceptionExpiry",
    "approve_exception",
    "expire_overdue_exceptions",
    "file_exception",
    "find_active_approved_exception",
    "get_exception",
    "list_exceptions",
    "reject_exception",
    "withdraw_exception",
]
