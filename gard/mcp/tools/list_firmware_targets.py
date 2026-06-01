"""MCP tool: list_firmware_targets."""

from __future__ import annotations

import base64
import json
import uuid

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.api.schemas.firmware_target import FirmwareTargetResponse
from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission
from gard.models import FirmwareTarget

TOOL_NAME = "list_firmware_targets"
REQUIRED_PERMISSION = Permission.READ_FIRMWARE_CATALOG


class ListFirmwareTargetsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform_family: str | None = None
    vendor_normalized: str | None = None
    limit: int = Field(default=50, ge=1, le=500)
    page_token: str | None = None


class ListFirmwareTargetsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[FirmwareTargetResponse]
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


def invoke(*, session: Session, body: ListFirmwareTargetsInput) -> ListFirmwareTargetsOutput:
    offset = _offset(body.page_token)
    stmt = (
        select(FirmwareTarget)
        .where(FirmwareTarget.removed_at.is_(None))
        .order_by(FirmwareTarget.platform_family, FirmwareTarget.name)
    )
    if body.platform_family:
        stmt = stmt.where(FirmwareTarget.platform_family == body.platform_family)
    rows = list(session.scalars(stmt.offset(offset).limit(body.limit + 1)))
    has_more = len(rows) > body.limit
    page = rows[: body.limit]
    items = [
        FirmwareTargetResponse(
            id=t.id,
            name=t.name,
            platform_family=t.platform_family,
            target_version=t.target_version,
            scope_selector=t.scope_selector,
            valid_from=t.valid_from,
            valid_until=t.valid_until,
            notes=t.notes,
            loaded_at=t.loaded_at,
            loaded_from_git_sha=t.loaded_from_git_sha,
            source_file_relpath=t.source_file_relpath,
        )
        for t in page
    ]
    return ListFirmwareTargetsOutput(
        items=items,
        total_returned=len(items),
        next_page_token=_token(offset + body.limit) if has_more else None,
        correlation_id=get_correlation_id() or str(uuid.uuid4()),
    )
