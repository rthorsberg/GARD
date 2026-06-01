"""MCP tool: list_devices.

REST parity: ``GET /api/v1/devices`` with pagination via ``page_token``.
"""

from __future__ import annotations

import base64
import json
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.api.routers import devices as devices_router
from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission
from gard.models import Device
from gard.models._enums import LifecycleState

TOOL_NAME = "list_devices"
REQUIRED_PERMISSION = Permission.LIST_DEVICES


class ListDevicesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor_normalized: str | None = None
    model_normalized: str | None = None
    site: str | None = None
    region: str | None = None
    lifecycle_state: LifecycleState | None = None
    limit: int = Field(default=100, ge=1, le=500)
    page_token: str | None = None


class ListDevicesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[dict[str, Any]]
    next_page_token: str | None = None
    correlation_id: str


def _decode_offset(token: str | None) -> int:
    if not token:
        return 0
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        return int(payload.get("offset", 0))
    except (ValueError, json.JSONDecodeError, TypeError):
        return 0


def _encode_offset(offset: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"offset": offset}).encode("utf-8")).decode("ascii")


def invoke(*, session: Session, body: ListDevicesInput) -> ListDevicesOutput:
    offset = _decode_offset(body.page_token)
    stmt = select(Device).order_by(Device.created_at.desc())
    if body.vendor_normalized:
        stmt = stmt.where(Device.vendor_normalized.ilike(body.vendor_normalized))
    if body.model_normalized:
        stmt = stmt.where(Device.model_normalized.ilike(body.model_normalized))
    if body.site:
        stmt = stmt.where(Device.site.ilike(body.site))
    if body.region:
        stmt = stmt.where(Device.region.ilike(body.region))
    if body.lifecycle_state:
        stmt = stmt.where(Device.lifecycle_state == body.lifecycle_state)

    rows = list(session.scalars(stmt.offset(offset).limit(body.limit + 1)))
    has_more = len(rows) > body.limit
    page = rows[: body.limit]
    items = [devices_router._envelope_for(d, session).model_dump(mode="json") for d in page]
    next_token = _encode_offset(offset + body.limit) if has_more else None
    return ListDevicesOutput(
        items=items,
        next_page_token=next_token,
        correlation_id=get_correlation_id() or str(uuid.uuid4()),
    )
