"""F2 firmware-target read endpoints (T038).

`GET /api/v1/firmware/targets` — paginated list of live firmware targets.
`GET /api/v1/firmware/targets/{id}` — single target by UUID.

Both filter `removed_at IS NULL` (soft-deleted rows never surface in
the read API). Auth: `READ_FIRMWARE_CATALOG`. No write surface — per
ADR-0011 the catalog is only mutated by the loader.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.api.middleware.rbac import require
from gard.api.schemas.firmware_target import (
    FirmwareTargetList,
    FirmwareTargetResponse,
)
from gard.core.rbac import Permission, Principal
from gard.db.session import get_session
from gard.models import FirmwareTarget

router = APIRouter(prefix="/api/v1/firmware/targets", tags=["firmware-catalog"])


def _to_response(t: FirmwareTarget) -> FirmwareTargetResponse:
    return FirmwareTargetResponse(
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


@router.get(
    "",
    response_model=FirmwareTargetList,
    summary="List live firmware targets",
)
def list_(
    _: Principal = Depends(require(Permission.READ_FIRMWARE_CATALOG)),
    session: Session = Depends(get_session),
    platform_family: str | None = Query(
        default=None,
        description="Exact match filter; case-sensitive.",
    ),
    name: str | None = Query(
        default=None,
        description="Exact match on the target's `name` field.",
    ),
    limit: int = Query(default=50, ge=1, le=500),
) -> FirmwareTargetList:
    stmt = (
        select(FirmwareTarget)
        .where(FirmwareTarget.removed_at.is_(None))
        .order_by(FirmwareTarget.platform_family, FirmwareTarget.name)
        .limit(limit)
    )
    if platform_family is not None:
        stmt = stmt.where(FirmwareTarget.platform_family == platform_family)
    if name is not None:
        stmt = stmt.where(FirmwareTarget.name == name)

    rows = list(session.scalars(stmt))
    items = [_to_response(r) for r in rows]
    return FirmwareTargetList(items=items, total_returned=len(items))


@router.get(
    "/{target_id}",
    response_model=FirmwareTargetResponse,
    summary="Fetch a single firmware target by id",
)
def get_(
    target_id: uuid.UUID,
    _: Principal = Depends(require(Permission.READ_FIRMWARE_CATALOG)),
    session: Session = Depends(get_session),
) -> FirmwareTargetResponse:
    t = session.scalar(
        select(FirmwareTarget)
        .where(FirmwareTarget.id == target_id)
        .where(FirmwareTarget.removed_at.is_(None))
    )
    if t is None:
        raise HTTPException(status_code=404, detail="firmware target not found")
    return _to_response(t)
