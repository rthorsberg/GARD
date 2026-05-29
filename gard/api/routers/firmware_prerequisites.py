"""F2 firmware prerequisite-rule read endpoint (T051).

`GET /api/v1/firmware/prerequisites` — list live rules. Optional
`predicate_kind` filter. Auth: `READ_FIRMWARE_CATALOG`. Per ADR-0011
there is no write surface — rules are loader-only.

Per FR-024 / spec.md §Assumptions the `tagged_with` predicate is
schema-valid and loadable but marked `evaluable=False`. The endpoint
surfaces both flag values; the F4 prerequisite engine will respect it
when wired up.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.api.middleware.rbac import require
from gard.api.schemas.firmware_prerequisite import (
    FirmwarePrerequisiteList,
    FirmwarePrerequisiteResponse,
)
from gard.core.rbac import Permission, Principal
from gard.db.session import get_session
from gard.models import FirmwarePrerequisiteRule

router = APIRouter(prefix="/api/v1/firmware/prerequisites", tags=["firmware-catalog"])


def _to_response(r: FirmwarePrerequisiteRule) -> FirmwarePrerequisiteResponse:
    return FirmwarePrerequisiteResponse(
        id=r.id,
        name=r.name,
        applies_to=r.applies_to,
        predicate_kind=r.predicate_kind,  # type: ignore[arg-type]
        predicate_args=r.predicate_args,
        severity=r.severity,  # type: ignore[arg-type]
        evaluable=r.evaluable,
        loaded_at=r.loaded_at,
        loaded_from_git_sha=r.loaded_from_git_sha,
        source_file_relpath=r.source_file_relpath,
    )


@router.get(
    "",
    response_model=FirmwarePrerequisiteList,
    summary="List live firmware prerequisite rules",
)
def list_(
    _: Principal = Depends(require(Permission.READ_FIRMWARE_CATALOG)),
    session: Session = Depends(get_session),
    predicate_kind: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> FirmwarePrerequisiteList:
    stmt = (
        select(FirmwarePrerequisiteRule)
        .where(FirmwarePrerequisiteRule.removed_at.is_(None))
        .order_by(FirmwarePrerequisiteRule.predicate_kind, FirmwarePrerequisiteRule.name)
        .limit(limit)
    )
    if predicate_kind is not None:
        stmt = stmt.where(FirmwarePrerequisiteRule.predicate_kind == predicate_kind)

    rows = list(session.scalars(stmt))
    items = [_to_response(r) for r in rows]
    return FirmwarePrerequisiteList(items=items, total_returned=len(items))
