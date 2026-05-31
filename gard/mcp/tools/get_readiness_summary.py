"""MCP tool: get_readiness_summary.

REST parity: ``GET /api/v1/readiness/summary``.

Auth: ``READ_READINESS``. Returns the same SummaryResponse shape as the
REST endpoint — the MCP transport feature (F008) will register this
delegate directly.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from gard.api.schemas.readiness import BlockerCategoryCount, SummaryResponse
from gard.core import readiness_evaluation_controller as ctrl
from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission

TOOL_NAME = "get_readiness_summary"
REQUIRED_PERMISSION = Permission.READ_READINESS


class GetReadinessSummaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region: str | None = None
    site: str | None = None
    platform_family: str | None = None
    vendor_normalized: str | None = None


GetReadinessSummaryOutput = SummaryResponse


def invoke(
    *,
    session: Session,
    body: GetReadinessSummaryInput,
) -> GetReadinessSummaryOutput:
    summary = ctrl.fetch_summary(
        session,
        region=body.region,
        site=body.site,
        platform_family=body.platform_family,
        vendor_normalized=body.vendor_normalized,
    )
    correlation_id = get_correlation_id() or "anonymous-correlation"
    return SummaryResponse(
        total_outside_target=summary.total_outside_target,
        ready_for_uplift_count=summary.ready_for_uplift_count,
        blocked_count=summary.blocked_count,
        not_applicable_count=summary.not_applicable_count,
        top_blocker_categories=[
            BlockerCategoryCount(predicate_kind=k, count=c)  # type: ignore[arg-type]
            for k, c in summary.top_blocker_categories
        ],
        filters_applied=summary.filters_applied,
        as_of=summary.as_of or dt.datetime.now(dt.UTC),
        correlation_id=correlation_id,
    )
