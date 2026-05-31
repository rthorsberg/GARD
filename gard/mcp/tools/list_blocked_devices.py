"""MCP tool: list_blocked_devices.

REST parity: ``GET /api/v1/readiness/devices?state=blocked``. Output
bounded to ``limit`` (max 500) and projected to a small payload an AI
agent can chew on.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from gard.api.schemas.readiness import BlockerPredicateKind
from gard.core import readiness_evaluation_controller as ctrl
from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission

TOOL_NAME = "list_blocked_devices"
REQUIRED_PERMISSION = Permission.READ_READINESS


class ListBlockedDevicesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region: str | None = None
    site: str | None = None
    platform_family: str | None = None
    vendor_normalized: str | None = None
    blocker_kind: BlockerPredicateKind | None = None
    limit: int = Field(default=100, ge=1, le=500)


class BlockedDeviceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: uuid.UUID
    hostname: str
    region: str | None = None
    site: str | None = None
    platform_family: str | None = None
    target_version: str | None = None
    observed_version: str | None = None
    primary_blocker_kind: BlockerPredicateKind
    primary_blocker_detail: str | None = None


class ListBlockedDevicesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[BlockedDeviceItem]
    total_returned: int = Field(ge=0)
    as_of: dt.datetime
    correlation_id: str


def invoke(
    *,
    session: Session,
    body: ListBlockedDevicesInput,
) -> ListBlockedDevicesOutput:
    rows = ctrl.fetch_device_list(
        session,
        state="blocked",
        blocker_kind=body.blocker_kind,
        region=body.region,
        site=body.site,
        platform_family=body.platform_family,
        vendor_normalized=body.vendor_normalized,
        limit=body.limit,
    )
    items: list[BlockedDeviceItem] = []
    for device, eval_row in rows:
        blockers = eval_row.blockers or []
        first = blockers[0] if blockers else {}
        if not isinstance(first, dict):
            continue
        kind = first.get("predicate_kind")
        if not isinstance(kind, str):
            continue
        detail_val = first.get("detail")
        items.append(
            BlockedDeviceItem(
                device_id=device.id,
                hostname=device.hostname,
                region=device.region,
                site=device.site,
                platform_family=device.platform_family,
                target_version=eval_row.target_version,
                observed_version=eval_row.observed_version,
                primary_blocker_kind=kind,  # type: ignore[arg-type]
                primary_blocker_detail=detail_val if isinstance(detail_val, str) else None,
            )
        )
    return ListBlockedDevicesOutput(
        items=items,
        total_returned=len(items),
        as_of=dt.datetime.now(dt.UTC),
        correlation_id=get_correlation_id() or "anonymous-correlation",
    )
