"""MCP tool: list_devices_outside_target.

REST parity: ``GET /api/v1/compliance/devices?state=outside_target
&drift_type=target_drift``. Output bounded to ``limit`` (max 500) and
projected to the small payload an AI agent can chew on.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from gard.core import compliance_evaluation_controller as ctrl
from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission

TOOL_NAME = "list_devices_outside_target"
REQUIRED_PERMISSION = Permission.READ_COMPLIANCE


class ListDevicesOutsideTargetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region: str | None = None
    site: str | None = None
    platform_family: str | None = None
    vendor_normalized: str | None = None
    limit: int = Field(default=100, ge=1, le=500)


class OutsideTargetItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: uuid.UUID
    hostname: str
    region: str | None = None
    site: str | None = None
    observed_version: str | None = None
    target_version: str | None = None
    drift_type: str = "target_drift"


class ListDevicesOutsideTargetOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OutsideTargetItem]
    total_returned: int = Field(ge=0)
    as_of: dt.datetime
    correlation_id: str


def invoke(
    *,
    session: Session,
    body: ListDevicesOutsideTargetInput,
) -> ListDevicesOutsideTargetOutput:
    rows = ctrl.fetch_device_list(
        session,
        drift_type="target_drift",
        state="outside_target",
        region=body.region,
        site=body.site,
        platform_family=body.platform_family,
        vendor_normalized=body.vendor_normalized,
        limit=body.limit,
    )
    items = [
        OutsideTargetItem(
            device_id=d.id,
            hostname=d.hostname,
            region=d.region,
            site=d.site,
            observed_version=e.observed_version,
            target_version=e.target_version,
        )
        for d, e in rows
    ]
    return ListDevicesOutsideTargetOutput(
        items=items,
        total_returned=len(items),
        as_of=dt.datetime.now(dt.UTC),
        correlation_id=get_correlation_id() or "anonymous-correlation",
    )
