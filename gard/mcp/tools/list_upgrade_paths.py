"""MCP tool: list_upgrade_paths."""

from __future__ import annotations

import base64
import json
import uuid

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.api.schemas.firmware_upgrade_path import FirmwareUpgradePathEdgeResponse
from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission
from gard.models import FirmwareUpgradePath

TOOL_NAME = "list_upgrade_paths"
REQUIRED_PERMISSION = Permission.READ_FIRMWARE_CATALOG


class ListUpgradePathsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform_family: str | None = None
    limit: int = Field(default=200, ge=1, le=1000)
    page_token: str | None = None


class ListUpgradePathsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[FirmwareUpgradePathEdgeResponse]
    total_returned: int
    next_page_token: str | None = None
    correlation_id: str


def _offset(token: str | None) -> int:
    if not token:
        return 0
    try:
        return int(json.loads(base64.urlsafe_b64decode(token.encode()).decode()).get("offset", 0))
    except (ValueError, json.JSONDecodeError):
        return 0


def _token(offset: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"offset": offset}).encode()).decode()


def invoke(*, session: Session, body: ListUpgradePathsInput) -> ListUpgradePathsOutput:
    offset = _offset(body.page_token)
    stmt = (
        select(FirmwareUpgradePath)
        .where(FirmwareUpgradePath.removed_at.is_(None))
        .order_by(
            FirmwareUpgradePath.platform_family,
            FirmwareUpgradePath.from_version,
            FirmwareUpgradePath.to_version,
        )
    )
    if body.platform_family:
        stmt = stmt.where(FirmwareUpgradePath.platform_family == body.platform_family)
    rows = list(session.scalars(stmt.offset(offset).limit(body.limit + 1)))
    has_more = len(rows) > body.limit
    page = rows[: body.limit]
    items = [
        FirmwareUpgradePathEdgeResponse(
            id=e.id,
            platform_family=e.platform_family,
            from_version=e.from_version,
            to_version=e.to_version,
            weight=e.weight,
            notes=e.notes,
            loaded_at=e.loaded_at,
            loaded_from_git_sha=e.loaded_from_git_sha,
            source_file_relpath=e.source_file_relpath,
        )
        for e in page
    ]
    return ListUpgradePathsOutput(
        items=items,
        total_returned=len(items),
        next_page_token=_token(offset + body.limit) if has_more else None,
        correlation_id=get_correlation_id() or str(uuid.uuid4()),
    )
