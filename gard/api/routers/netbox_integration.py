"""F7/F10 NetBox integration router."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from gard.api.middleware.rbac import require
from gard.api.schemas.ipam_alignment import (
    IpamAlignmentEntryOut,
    IpamAlignmentFindingList,
    IpamAlignmentFindingOut,
    IpamAlignmentReportOut,
    IpamAlignmentSummaryOut,
)
from gard.api.schemas.netbox_integration import (
    NetboxSummaryEnvelope,
    NetboxSummaryOut,
    NetboxSyncEnvelope,
    NetboxSyncReportOut,
    NetboxSyncRunList,
    NetboxSyncRunOut,
    OrphanedDeviceOut,
    WritebackConflictOut,
    WritebackEntryOut,
    WritebackReportOut,
    WritebackSummaryOut,
)
from gard.core import ipam_alignment_controller as align_ctrl
from gard.core import netbox_sync_controller as ctrl
from gard.core.ipam_alignment_controller import IpamAlignmentReport
from gard.core.rbac import Permission, Principal
from gard.db.session import get_append_only_session, get_session
from gard.integrations.netbox.client import NetboxNotConfigured, NetboxUnreachable
from gard.integrations.netbox.writeback_publisher import WritebackReport
from gard.models import IpamAlignmentFinding, NetboxSyncRun
from gard.models._enums import AlignmentFindingSeverity

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


def _writeback_out(report: WritebackReport | None) -> WritebackReportOut | None:
    if report is None:
        return None
    return WritebackReportOut(
        phase=report.phase.value,
        summary=WritebackSummaryOut(
            updated=report.summary.updated,
            skipped=report.summary.skipped,
            unchanged=report.summary.unchanged,
            conflict=report.summary.conflict,
            failed=report.summary.failed,
            skipped_not_linked=report.summary.skipped_not_linked,
        ),
        entries=[
            WritebackEntryOut(
                device_id=e.device_id,
                netbox_device_id=e.netbox_device_id,
                status=e.status.value,
                message=e.message,
                conflicts=[
                    WritebackConflictOut(
                        field=c.field,
                        expected=c.expected,
                        actual=c.actual,
                    )
                    for c in e.conflicts
                ],
            )
            for e in report.entries
        ],
    )


def _alignment_out(report: IpamAlignmentReport | None) -> IpamAlignmentReportOut | None:
    if report is None:
        return None
    return IpamAlignmentReportOut(
        phase=report.phase.value,
        run_id=report.run_id,
        summary=IpamAlignmentSummaryOut(
            devices_checked=report.summary.devices_checked,
            aligned_count=report.summary.aligned_count,
            mismatch_count=report.summary.mismatch_count,
            error_count=report.summary.error_count,
            warning_count=report.summary.warning_count,
            info_count=report.summary.info_count,
            findings_by_kind=report.summary.findings_by_kind,
            l2vpn_available=report.summary.l2vpn_available,
        ),
        entries=[
            IpamAlignmentEntryOut(
                device_id=e.device_id,
                netbox_device_id=e.netbox_device_id,
                overall_status=e.overall_status,  # type: ignore[arg-type]
                finding_count=e.finding_count,
                top_kinds=e.top_kinds,
            )
            for e in report.entries
        ],
    )


def _finding_out(row: IpamAlignmentFinding) -> IpamAlignmentFindingOut:
    return IpamAlignmentFindingOut(
        id=row.id,
        run_id=row.run_id,
        device_id=row.device_id,
        kind=row.kind.value,
        severity=row.severity.value,
        status=row.status.value,
        interface_name=row.interface_name,
        netbox_observed=row.netbox_observed,
        gard_observed=row.gard_observed,
        remediation_hint=row.remediation_hint,
        created_at=row.created_at,
    )


@router.post("/sync", response_model=NetboxSyncEnvelope, summary="Trigger NetBox sync")
def trigger_sync(
    confirm_writeback: bool = Query(default=False),
    principal: Principal = Depends(require(Permission.SYNC_NETBOX)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> NetboxSyncEnvelope:
    try:
        outcome = ctrl.run_sync(
            session=session,
            audit_session=audit_session,
            principal=principal,
            writeback_confirm=confirm_writeback,
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
        writeback=_writeback_out(outcome.report.writeback),
        ipam_alignment=_alignment_out(outcome.report.ipam_alignment),
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


@router.get(
    "/alignment/findings",
    response_model=IpamAlignmentFindingList,
    summary="List IPAM alignment findings",
)
def list_alignment_findings(
    run_id: uuid.UUID | None = Query(default=None),
    device_id: uuid.UUID | None = Query(default=None),
    severity: AlignmentFindingSeverity | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    page_token: str | None = Query(default=None),
    _: Principal = Depends(require(Permission.READ_NETBOX)),
    session: Session = Depends(get_session),
) -> IpamAlignmentFindingList:
    offset = int(page_token) if page_token and page_token.isdigit() else 0
    rows, total = align_ctrl.list_findings(
        session,
        run_id=run_id,
        device_id=device_id,
        severity=severity,
        limit=limit,
        offset=offset,
    )
    next_token = str(offset + len(rows)) if len(rows) == limit else None
    return IpamAlignmentFindingList(
        items=[_finding_out(r) for r in rows],
        total_returned=total,
        next_page_token=next_token,
    )
