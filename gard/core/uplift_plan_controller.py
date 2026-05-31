"""F5 uplift-plan controller (T021).

Plans are the lightweight grouping for waves. They carry no state
machine beyond ``archived_at`` (a soft delete) and no device list, so
this controller is thin: create, archive, list, get, plus a
``count_waves`` helper the router uses to populate ``PlanEnvelope``.

Every mutation emits exactly one ``audit_events`` row through the
append-only session (ADR-0009). Reads do not audit here — the router
emits ``uplift_plan.read`` at the edge so the audit row carries the
caller's principal + correlation id.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gard.core.audit import emit as audit_emit
from gard.core.logging import get_correlation_id, get_logger
from gard.models import UpliftPlan, UpliftWave, utcnow
from gard.models._enums import ActorType

_log = get_logger(__name__)


class PlanNotFound(Exception):  # noqa: N818  # public sentinel
    """No plan with the given id (router maps to 404)."""

    def __init__(self, plan_id: uuid.UUID) -> None:
        self.plan_id = plan_id
        super().__init__(f"uplift plan not found: {plan_id}")


@dataclass(frozen=True, slots=True)
class PlanListPage:
    plans: list[tuple[UpliftPlan, int]]  # (plan, wave_count)
    next_after_id: uuid.UUID | None


def create_plan(
    *,
    session: Session,
    audit_session: Session,
    name: str,
    description: str | None,
    actor: str,
    actor_type: ActorType,
) -> UpliftPlan:
    """Create a plan + emit ``uplift_plan.created``."""
    correlation_id = get_correlation_id() or "unknown"
    plan = UpliftPlan(
        name=name,
        description=description,
        created_by=actor,
    )
    session.add(plan)
    session.flush()

    audit_emit(
        session=audit_session,
        action="uplift_plan.created",
        object_type="UpliftPlan",
        object_id=str(plan.id),
        actor=actor,
        actor_type=actor_type,
        before=None,
        after={"id": str(plan.id), "name": name},
        correlation_id=correlation_id,
    )
    _log.info("uplift_plan.created", plan_id=str(plan.id), name=name)
    return plan


def archive_plan(
    *,
    session: Session,
    audit_session: Session,
    plan_id: uuid.UUID,
    actor: str,
    actor_type: ActorType,
) -> UpliftPlan:
    """Soft-delete a plan + emit ``uplift_plan.archived``.

    Idempotent: archiving an already-archived plan is a no-op that
    returns the row without a second audit write.
    """
    plan = session.get(UpliftPlan, plan_id)
    if plan is None:
        raise PlanNotFound(plan_id)
    if plan.archived_at is not None:
        return plan

    correlation_id = get_correlation_id() or "unknown"
    plan.archived_at = utcnow()
    plan.archived_by = actor
    session.flush()

    audit_emit(
        session=audit_session,
        action="uplift_plan.archived",
        object_type="UpliftPlan",
        object_id=str(plan.id),
        actor=actor,
        actor_type=actor_type,
        before={"archived_at": None},
        after={"archived_at": plan.archived_at.isoformat()},
        correlation_id=correlation_id,
    )
    _log.info("uplift_plan.archived", plan_id=str(plan.id))
    return plan


def get_plan(session: Session, plan_id: uuid.UUID) -> UpliftPlan | None:
    return session.get(UpliftPlan, plan_id)


def count_waves(session: Session, plan_id: uuid.UUID) -> int:
    return int(session.scalar(select(func.count()).where(UpliftWave.plan_id == plan_id)) or 0)


def list_plans(
    session: Session,
    *,
    include_archived: bool = False,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
) -> PlanListPage:
    """Page of plans (id-descending cursor) with their wave counts.

    The ``region`` query parameter in the contract is accepted at the
    router but is a no-op here — plans are not region-scoped (waves
    carry the platform/region detail). It exists for forward
    compatibility with a v2 region-tagged plan model.
    """
    q = select(UpliftPlan)
    if not include_archived:
        q = q.where(UpliftPlan.archived_at.is_(None))
    if after_id is not None:
        q = q.where(UpliftPlan.id < after_id)
    q = q.order_by(UpliftPlan.id.desc()).limit(limit)

    plans = list(session.scalars(q))
    out: list[tuple[UpliftPlan, int]] = [(p, count_waves(session, p.id)) for p in plans]
    next_after = plans[-1].id if len(plans) == limit else None
    return PlanListPage(plans=out, next_after_id=next_after)


__all__ = [
    "PlanListPage",
    "PlanNotFound",
    "archive_plan",
    "count_waves",
    "create_plan",
    "get_plan",
    "list_plans",
]
