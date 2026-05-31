"""MCP tool: get_ready_for_uplift_devices.

REST parity: ``GET /api/v1/readiness/devices?state=ready_for_uplift``.
F5's wave drafter is the primary upstream consumer.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from gard.core import readiness_evaluation_controller as ctrl
from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission

TOOL_NAME = "get_ready_for_uplift_devices"
REQUIRED_PERMISSION = Permission.READ_READINESS


class GetReadyForUpliftDevicesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region: str | None = None
    site: str | None = None
    platform_family: str | None = None
    vendor_normalized: str | None = None
    limit: int = Field(default=100, ge=1, le=500)


class ReadyForUpliftItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: uuid.UUID
    hostname: str
    region: str | None = None
    site: str | None = None
    platform_family: str | None = None
    target_version: str
    observed_version: str | None = None


class GetReadyForUpliftDevicesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ReadyForUpliftItem]
    total_returned: int = Field(ge=0)
    as_of: dt.datetime
    correlation_id: str


def invoke(
    *,
    session: Session,
    body: GetReadyForUpliftDevicesInput,
) -> GetReadyForUpliftDevicesOutput:
    rows = ctrl.fetch_device_list(
        session,
        state="ready_for_uplift",
        region=body.region,
        site=body.site,
        platform_family=body.platform_family,
        vendor_normalized=body.vendor_normalized,
        limit=body.limit,
    )
    items: list[ReadyForUpliftItem] = []
    for device, eval_row in rows:
        if eval_row.target_version is None:
            # ready_for_uplift implies target_version is set; defensive
            # skip protects against catalog races.
            continue
        items.append(
            ReadyForUpliftItem(
                device_id=device.id,
                hostname=device.hostname,
                region=device.region,
                site=device.site,
                platform_family=device.platform_family,
                target_version=eval_row.target_version,
                observed_version=eval_row.observed_version,
            )
        )
    return GetReadyForUpliftDevicesOutput(
        items=items,
        total_returned=len(items),
        as_of=dt.datetime.now(dt.UTC),
        correlation_id=get_correlation_id() or "anonymous-correlation",
    )
