"""Read-only audit endpoint (T046)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.api.middleware.rbac import require
from gard.core.rbac import Permission, Principal
from gard.db.session import get_session
from gard.models import AuditEvent

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


class AuditEventOut(BaseModel):
    id: uuid.UUID
    timestamp: dt.datetime
    actor: str
    actor_type: str
    action: str
    object_type: str
    object_id: str
    result: str
    correlation_id: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    source_ip: str | None = None


class AuditPage(BaseModel):
    items: list[AuditEventOut]
    next_cursor: str | None = None
    total_returned: int = Field(ge=0)


@router.get("", response_model=AuditPage)
def list_audit(
    _: Principal = Depends(require(Permission.READ_AUDIT)),
    session: Session = Depends(get_session),
    correlation_id: str | None = Query(default=None),
    object_type: str | None = Query(default=None),
    object_id: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> AuditPage:
    stmt = select(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(limit)
    if correlation_id:
        stmt = stmt.where(AuditEvent.correlation_id == correlation_id)
    if object_type:
        stmt = stmt.where(AuditEvent.object_type == object_type)
    if object_id:
        stmt = stmt.where(AuditEvent.object_id == object_id)
    if actor:
        stmt = stmt.where(AuditEvent.actor == actor)
    rows = session.scalars(stmt).all()
    items = [
        AuditEventOut(
            id=r.id,
            timestamp=r.timestamp,
            actor=r.actor,
            actor_type=r.actor_type.value,
            action=r.action,
            object_type=r.object_type,
            object_id=r.object_id,
            result=r.result.value,
            correlation_id=r.correlation_id,
            before=r.before,
            after=r.after,
            source_ip=r.source_ip,
        )
        for r in rows
    ]
    return AuditPage(items=items, total_returned=len(items))
