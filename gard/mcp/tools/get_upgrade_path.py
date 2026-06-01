"""MCP tool: get_upgrade_path.

REST parity: ``GET /api/v1/firmware/upgrade-paths/chain``.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.api.schemas.firmware_upgrade_path import UpgradePathChainReason
from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission
from gard.core.upgrade_path_graph import EdgeSpec, UpgradePathGraphCache
from gard.models import FirmwareUpgradePath

TOOL_NAME = "get_upgrade_path"
REQUIRED_PERMISSION = Permission.READ_FIRMWARE_CATALOG


class GetUpgradePathInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform_family: str = Field(min_length=1)
    from_version: str = Field(min_length=1)
    to_version: str = Field(min_length=1)


class GetUpgradePathOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform_family: str
    from_version: str
    to_version: str
    chain: list[str]
    hop_count: int
    total_weight: int
    reasons: list[UpgradePathChainReason]
    correlation_id: str


def invoke(*, session: Session, body: GetUpgradePathInput) -> GetUpgradePathOutput:
    rows = list(
        session.scalars(
            select(FirmwareUpgradePath)
            .where(FirmwareUpgradePath.removed_at.is_(None))
            .where(FirmwareUpgradePath.platform_family == body.platform_family)
        )
    )
    cache = UpgradePathGraphCache()
    cache.rebuild(
        body.platform_family,
        [
            EdgeSpec(from_version=r.from_version, to_version=r.to_version, weight=r.weight)
            for r in rows
        ],
    )
    result = cache.shortest_path(body.platform_family, body.from_version, body.to_version)
    return GetUpgradePathOutput(
        platform_family=body.platform_family,
        from_version=body.from_version,
        to_version=body.to_version,
        chain=list(result.chain),
        hop_count=result.hops,
        total_weight=result.total_weight or 0,
        reasons=[
            UpgradePathChainReason(kind=r["kind"], detail=r.get("detail")) for r in result.reasons
        ],
        correlation_id=get_correlation_id() or str(uuid.uuid4()),
    )
