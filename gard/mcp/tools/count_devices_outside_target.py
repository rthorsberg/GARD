"""MCP tool: count_devices_outside_target.

REST parity: derived from ``GET /api/v1/compliance/summary`` —
returns ``counts_by_drift_type.target_drift`` as a single integer.
Designed for the "how bad is it?" daily-standup question from an AI
agent.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from gard.core import compliance_evaluation_controller as ctrl
from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission

TOOL_NAME = "count_devices_outside_target"
REQUIRED_PERMISSION = Permission.READ_COMPLIANCE


class CountDevicesOutsideTargetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region: str | None = None
    site: str | None = None
    platform_family: str | None = None
    vendor_normalized: str | None = None


class CountDevicesOutsideTargetOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=0)
    as_of: dt.datetime
    correlation_id: str


def invoke(
    *,
    session: Session,
    body: CountDevicesOutsideTargetInput,
) -> CountDevicesOutsideTargetOutput:
    summary = ctrl.fetch_summary(
        session,
        region=body.region,
        site=body.site,
        platform_family=body.platform_family,
        vendor_normalized=body.vendor_normalized,
    )
    # "outside_target" means state=outside_target — which always has
    # primary_drift=target_drift (with possibly rule/package as
    # secondary). The summary's target_drift counter captures it.
    return CountDevicesOutsideTargetOutput(
        count=summary.counts_by_drift_type.get("target_drift", 0),
        as_of=summary.as_of or dt.datetime.now(dt.UTC),
        correlation_id=get_correlation_id() or "anonymous-correlation",
    )
