"""F7 NetBox integration router (read-only sync)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from gard.api.middleware.rbac import require
from gard.api.schemas.netbox_integration import (
    NetboxSummaryEnvelope,
    NetboxSummaryOut,
    NetboxSyncEnvelope,
    NetboxSyncReportOut,
    NetboxSyncRunList,
    NetboxSyncRunOut,
    OrphanedDeviceOut,
)
from gard.core import netbox_sync_controller as ctrl
from gard.core.rbac import Permission, Principal
from gard.db.session import get_append_only_session, get_session
from gard.integrations.netbox.client import NetboxNotConfigured, NetboxUnreachable
from gard.models import NetboxSyncRun

router = APIRouter(prefix="/api/v1/integrations/netbox", tags=["netbox"])


def _run_out(run: NetboxSyncRun) -> NetboxSyncRunOut:
    return NetboxSyncRunOut(
        id=run.id,
        status=run.status.value,
        started_at=run.started_at,
        completed_at=run.completed_at,
        correlation_id=run.correlation_id,
        matched_count=run.matched_count,
        created_count=run.created_count,
        updated_count=run.updated_count,
        orphaned_count=run.orphaned_count,
        error_summary=run.error_summary,
    )


@router.post("/sync", response_model=NetboxSyncEnvelope, summary="Trigger NetBox sync")
def trigger_sync(
    principal: Principal = Depends(require(Permission.SYNC_NETBOX)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> NetboxSyncEnvelope:
    try:
        outcome = ctrl.run_sync(
            session=session,
            audit_session=audit_session,
            principal=principal,
        )
    except NetboxNotConfigured as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "NETBOX_NOT_CONFIGURED",
                    "message": str(exc),
                }
            },
        ) from exc
    except NetboxUnreachable as exc:
        session.rollback()
        audit_session.commit()
        raise HTTPException(
            status_code=502,
            detail={
                "error": {
                    "code": "NETBOX_UNREACHABLE",
                    "message": str(exc),
                }
            },
        ) from exc
    except ctrl.NetboxAmbiguousIdentity as exc:
        session.rollback()
        audit_session.commit()
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "NETBOX_AMBIGUOUS_IDENTITY",
                    "message": str(exc),
                    "details": {"conflicts": exc.details},
                }
            },
        ) from exc

    session.commit()
    audit_session.commit()

    report = NetboxSyncReportOut(
        matched_count=outcome.report.matched_count,
        created_count=outcome.report.created_count,
        updated_count=outcome.report.updated_count,
        orphaned_count=outcome.report.orphaned_count,
        orphaned_in_gard=[
            OrphanedDeviceOut(
                device_id=o.device_id,
                hostname=o.hostname,
                serial_number=o.serial_number,
                site=o.site,
                reason=o.reason,
            )
            for o in outcome.report.orphaned_in_gard
        ],
    )
    return NetboxSyncEnvelope(
        data={
            "run": _run_out(outcome.run).model_dump(mode="json"),
            "report": report.model_dump(mode="json"),
        }
    )


@router.get("/summary", response_model=NetboxSummaryEnvelope, summary="NetBox linkage summary")
def get_summary(
    _: Principal = Depends(require(Permission.READ_NETBOX)),
    session: Session = Depends(get_session),
) -> NetboxSummaryEnvelope:
    summary = ctrl.get_summary(session)
    return NetboxSummaryEnvelope(
        data=NetboxSummaryOut(
            netbox_linked=summary.netbox_linked,
            csv_only=summary.csv_only,
            orphaned_in_gard=summary.orphaned_in_gard,
            last_sync_at=summary.last_sync_at,
        )
    )


@router.get("/sync-runs", response_model=NetboxSyncRunList, summary="List NetBox sync runs")
def list_sync_runs(
    limit: int = 20,
    _: Principal = Depends(require(Permission.READ_NETBOX)),
    session: Session = Depends(get_session),
) -> NetboxSyncRunList:
    runs = ctrl.list_sync_runs(session, limit=min(max(limit, 1), 100))
    return NetboxSyncRunList(
        data=[_run_out(r) for r in runs],
        pagination={"next_page_token": None},
    )


@router.get(
    "/sync-runs/{run_id}",
    response_model=NetboxSyncEnvelope,
    summary="Get a NetBox sync run",
)
def get_sync_run(
    run_id: uuid.UUID,
    _: Principal = Depends(require(Permission.READ_NETBOX)),
    session: Session = Depends(get_session),
) -> NetboxSyncEnvelope:
    run = ctrl.get_sync_run(session, run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "NOT_FOUND",
                    "message": "sync run not found",
                }
            },
        )
    return NetboxSyncEnvelope(data={"run": _run_out(run).model_dump(mode="json")})
