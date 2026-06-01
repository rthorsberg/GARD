"""MCP tool: list_firmware_packages."""

from __future__ import annotations

import base64
import json
import uuid

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.api.schemas.firmware_package import FirmwarePackageResponse
from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission
from gard.models import FirmwarePackage

TOOL_NAME = "list_firmware_packages"
REQUIRED_PERMISSION = Permission.READ_FIRMWARE_CATALOG


class ListFirmwarePackagesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform_family: str | None = None
    limit: int = Field(default=50, ge=1, le=500)
    page_token: str | None = None


class ListFirmwarePackagesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[FirmwarePackageResponse]
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


def invoke(*, session: Session, body: ListFirmwarePackagesInput) -> ListFirmwarePackagesOutput:
    offset = _offset(body.page_token)
    stmt = (
        select(FirmwarePackage)
        .where(FirmwarePackage.removed_at.is_(None))
        .order_by(FirmwarePackage.platform_family, FirmwarePackage.version)
    )
    if body.platform_family:
        stmt = stmt.where(FirmwarePackage.platform_family == body.platform_family)
    rows = list(session.scalars(stmt.offset(offset).limit(body.limit + 1)))
    has_more = len(rows) > body.limit
    page = rows[: body.limit]
    items = [
        FirmwarePackageResponse(
            id=p.id,
            vendor=p.vendor,  # type: ignore[arg-type]
            platform_family=p.platform_family,
            version=p.version,
            sha256=p.sha256,
            byte_size=p.byte_size,
            signed_by=p.signed_by,
            release_date=p.release_date,
            download_url=p.download_url,
            notes=p.notes,
            blob_present=p.blob_present,
            blob_stored_at=p.blob_stored_at,
            loaded_at=p.loaded_at,
            loaded_from_git_sha=p.loaded_from_git_sha,
            source_file_relpath=p.source_file_relpath,
        )
        for p in page
    ]
    return ListFirmwarePackagesOutput(
        items=items,
        total_returned=len(items),
        next_page_token=_token(offset + body.limit) if has_more else None,
        correlation_id=get_correlation_id() or str(uuid.uuid4()),
    )
