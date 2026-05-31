"""MCP tool: list_active_exceptions."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission
from gard.models import Device, UpliftException
from gard.models._enums import ExceptionState

TOOL_NAME = "list_active_exceptions"
REQUIRED_PERMISSION = Permission.READ_UPLIFT


class ListActiveExceptionsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region: str | None = None
    platform_family: str | None = None
    expires_within_days: int | None = Field(default=None, ge=1, le=365)
    limit: int = Field(default=100, ge=1, le=500)


class ActiveExceptionRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exception_id: uuid.UUID
    device_id: uuid.UUID
    hostname: str | None = None
    predicate_kind: str
    justification_excerpt: str
    expires_at: dt.datetime
    approved_by: str
    approved_at: dt.datetime


class ListActiveExceptionsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ActiveExceptionRow] = Field(default_factory=list)
    total_returned: int = Field(ge=0)
    correlation_id: str


def invoke(
    *,
    session: Session,
    body: ListActiveExceptionsInput,
) -> ListActiveExceptionsOutput:
    now = dt.datetime.now(dt.UTC)
    q = (
        select(UpliftException, Device)
        .join(Device, Device.id == UpliftException.device_id)
        .where(UpliftException.state == ExceptionState.approved.value)
        .where(UpliftException.expires_at > now)
        .order_by(UpliftException.expires_at.asc())
        .limit(body.limit)
    )
    if body.region is not None:
        q = q.where(Device.region == body.region)
    if body.platform_family is not None:
        q = q.where(Device.platform_family == body.platform_family)
    if body.expires_within_days is not None:
        horizon = now + dt.timedelta(days=body.expires_within_days)
        q = q.where(UpliftException.expires_at <= horizon)

    rows = list(session.execute(q))
    items: list[ActiveExceptionRow] = []
    for exc, device in rows:
        kind = exc.synthetic_kind or "catalog_rule"
        excerpt = exc.justification[:120]
        items.append(
            ActiveExceptionRow(
                exception_id=exc.id,
                device_id=exc.device_id,
                hostname=device.hostname,
                predicate_kind=kind,
                justification_excerpt=excerpt,
                expires_at=exc.expires_at,
                approved_by=exc.approved_by or "",
                approved_at=exc.approved_at or exc.filed_at,
            )
        )

    return ListActiveExceptionsOutput(
        items=items,
        total_returned=len(items),
        correlation_id=get_correlation_id() or "anonymous-correlation",
    )
