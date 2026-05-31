"""MCP tool: get_compliance_summary.

REST parity: ``GET /api/v1/compliance/summary``.

Auth: ``READ_COMPLIANCE``. Returns the same SummaryResponse shape as
the REST endpoint — the MCP transport feature (F008) will register
this delegate directly.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from gard.api.schemas.compliance import DriftCounts, SummaryResponse
from gard.core import compliance_evaluation_controller as ctrl
from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission

TOOL_NAME = "get_compliance_summary"
REQUIRED_PERMISSION = Permission.READ_COMPLIANCE


class GetComplianceSummaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region: str | None = None
    site: str | None = None
    platform_family: str | None = None
    vendor_normalized: str | None = None


class GetComplianceSummaryOutput(SummaryResponse):
    """Adds ``correlation_id`` for the MCP envelope."""

    model_config = ConfigDict(extra="forbid")

    correlation_id: str


def invoke(
    *,
    session: Session,
    body: GetComplianceSummaryInput,
) -> GetComplianceSummaryOutput:
    counts = ctrl.fetch_summary(
        session,
        region=body.region,
        site=body.site,
        platform_family=body.platform_family,
        vendor_normalized=body.vendor_normalized,
    )
    return GetComplianceSummaryOutput(
        total_evaluated=counts.total_evaluated,
        compliant_count=counts.compliant_count,
        unknown_count=counts.unknown_count,
        counts_by_drift_type=DriftCounts(**counts.counts_by_drift_type),
        filters_applied=counts.filters_applied,
        as_of=counts.as_of or dt.datetime.now(dt.UTC),
        correlation_id=get_correlation_id() or "anonymous-correlation",
    )
