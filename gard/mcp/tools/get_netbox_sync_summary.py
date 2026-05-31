"""MCP tool: get_netbox_sync_summary.

REST parity: ``GET /api/v1/integrations/netbox/summary``.

Auth: ``READ_NETBOX``. Returns linkage counts (netbox_linked, csv_only,
orphaned_in_gard, last_sync_at) — same ``data`` shape as the REST
endpoint wrapped with ``correlation_id`` for the MCP envelope.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from gard.core import netbox_sync_controller as ctrl
from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission

TOOL_NAME = "get_netbox_sync_summary"
REQUIRED_PERMISSION = Permission.READ_NETBOX


class GetNetboxSyncSummaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GetNetboxSyncSummaryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    netbox_linked: int = Field(ge=0)
    csv_only: int = Field(ge=0)
    orphaned_in_gard: int = Field(ge=0)
    last_sync_at: str | None = None
    correlation_id: str


def invoke(
    *,
    session: Session,
    body: GetNetboxSyncSummaryInput,
) -> GetNetboxSyncSummaryOutput:
    _ = body
    summary = ctrl.get_summary(session)
    last_sync = summary.last_sync_at.isoformat() if summary.last_sync_at is not None else None
    return GetNetboxSyncSummaryOutput(
        netbox_linked=summary.netbox_linked,
        csv_only=summary.csv_only,
        orphaned_in_gard=summary.orphaned_in_gard,
        last_sync_at=last_sync,
        correlation_id=get_correlation_id() or "anonymous-correlation",
    )
