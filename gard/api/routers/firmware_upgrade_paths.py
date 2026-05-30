"""F2 firmware upgrade-path endpoints (T050).

Two surfaces:

- `GET /api/v1/firmware/upgrade-paths/edges?platform_family=X` — list
  raw edges (one row per declared `from_version → to_version` step).
- `GET /api/v1/firmware/upgrade-paths/chain?platform_family=X&from_version=A&to_version=B`
  — shortest-weight chain via Dijkstra on `networkx`. Returns 200
  with an empty chain + `reasons[0]` when no path exists or the
  platform isn't in the catalog (per FR-016..FR-019 — never 404 on
  semantic absence).

Auth: `READ_FIRMWARE_CATALOG` for both. No write surface.

The route fetches the platform's edge set fresh from the DB on each
chain query. Caching is delegated to the loader's
:class:`UpgradePathGraphCache` for non-HTTP callers; for the API we
keep request semantics stateless. This adds one query per request but
the edge sets are tiny (low hundreds at v1 scale) and Postgres caches
the index leaves.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.api.middleware.rbac import require
from gard.api.schemas.firmware_upgrade_path import (
    FirmwareUpgradePathEdgeList,
    FirmwareUpgradePathEdgeResponse,
    UpgradePathChainReason,
    UpgradePathChainResponse,
)
from gard.core.rbac import Permission, Principal
from gard.core.upgrade_path_graph import EdgeSpec, UpgradePathGraphCache
from gard.db.session import get_session
from gard.models import FirmwareUpgradePath

router = APIRouter(prefix="/api/v1/firmware/upgrade-paths", tags=["firmware-catalog"])


def _to_response(e: FirmwareUpgradePath) -> FirmwareUpgradePathEdgeResponse:
    return FirmwareUpgradePathEdgeResponse(
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


def _load_edges(session: Session, platform_family: str) -> list[FirmwareUpgradePath]:
    return list(
        session.scalars(
            select(FirmwareUpgradePath)
            .where(FirmwareUpgradePath.removed_at.is_(None))
            .where(FirmwareUpgradePath.platform_family == platform_family)
            .order_by(FirmwareUpgradePath.from_version, FirmwareUpgradePath.to_version)
        )
    )


@router.get(
    "/edges",
    response_model=FirmwareUpgradePathEdgeList,
    summary="List declared upgrade-path edges, optionally filtered by platform",
)
def list_edges(
    _: Principal = Depends(require(Permission.READ_FIRMWARE_CATALOG)),
    session: Session = Depends(get_session),
    platform_family: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> FirmwareUpgradePathEdgeList:
    stmt = (
        select(FirmwareUpgradePath)
        .where(FirmwareUpgradePath.removed_at.is_(None))
        .order_by(
            FirmwareUpgradePath.platform_family,
            FirmwareUpgradePath.from_version,
            FirmwareUpgradePath.to_version,
        )
        .limit(limit)
    )
    if platform_family is not None:
        stmt = stmt.where(FirmwareUpgradePath.platform_family == platform_family)

    rows = list(session.scalars(stmt))
    items = [_to_response(r) for r in rows]
    return FirmwareUpgradePathEdgeList(items=items, total_returned=len(items))


@router.get(
    "/chain",
    response_model=UpgradePathChainResponse,
    summary="Shortest-weight upgrade chain between two versions on a platform",
)
def chain(
    platform_family: str = Query(..., min_length=1),
    from_version: str = Query(..., min_length=1),
    to_version: str = Query(..., min_length=1),
    _: Principal = Depends(require(Permission.READ_FIRMWARE_CATALOG)),
    session: Session = Depends(get_session),
) -> UpgradePathChainResponse:
    rows = _load_edges(session, platform_family)
    cache = UpgradePathGraphCache()
    cache.rebuild(
        platform_family,
        [
            EdgeSpec(
                from_version=r.from_version,
                to_version=r.to_version,
                weight=r.weight,
            )
            for r in rows
        ],
    )
    # Edge case: zero edges but the query is zero-hop — return zero_hop
    # directly. The cache returns `platform_not_found` for non-zero-hop
    # queries on an empty platform, which is the right answer.
    result = cache.shortest_path(platform_family, from_version, to_version)
    return UpgradePathChainResponse(
        platform_family=platform_family,
        from_version=from_version,
        to_version=to_version,
        chain=list(result.chain),
        hop_count=result.hops,
        total_weight=result.total_weight,
        reasons=[
            UpgradePathChainReason(kind=r["kind"], detail=r.get("detail")) for r in result.reasons
        ],
    )
