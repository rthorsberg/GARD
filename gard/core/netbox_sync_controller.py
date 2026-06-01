"""NetBox sync / reconcile controller (F7)."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gard.core import audit as audit_emit
from gard.core import evidence as evidence_emit
from gard.core.device_controller import _find_by_identity
from gard.core.identity import DeviceIdentity
from gard.core.logging import get_correlation_id
from gard.core.rbac import Principal
from gard.core.settings import Settings, get_settings
from gard.integrations.netbox.client import (
    NetboxClient,
    NetboxDeviceRecord,
    NetboxNotConfigured,
    NetboxUnreachable,
)
from gard.integrations.netbox.write_client import NetboxWriteNotConfigured
from gard.integrations.netbox.writeback_publisher import (
    WritebackPhase,
    WritebackReport,
    WritebackSummary,
    run_writeback,
    skipped_writeback_report,
)
from gard.models import Device, NetboxSyncRun, utcnow
from gard.models._enums import AuditResult, EvidenceType, LifecycleState, NetboxSyncRunStatus


class NetboxAmbiguousIdentity(Exception):  # noqa: N818
    """Duplicate serial in NetBox or two NetBox rows match one GARD device."""

    def __init__(self, message: str, *, details: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.details = details


@dataclass
class OrphanedDevice:
    device_id: uuid.UUID
    hostname: str
    serial_number: str | None
    site: str | None
    reason: str


@dataclass
class NetboxSyncReport:
    matched_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    orphaned_count: int = 0
    orphaned_in_gard: list[OrphanedDevice] = field(default_factory=list)
    writeback: WritebackReport | None = None


@dataclass(frozen=True)
class NetboxSyncOutcome:
    run: NetboxSyncRun
    report: NetboxSyncReport


def client_from_settings(settings: Settings | None = None) -> NetboxClient:
    s = settings or get_settings()
    if s.netbox_url is None:
        raise NetboxNotConfigured("GARD_NETBOX_URL is not set")
    if not s.netbox_token:
        raise NetboxNotConfigured("GARD_NETBOX_TOKEN is not set")
    return NetboxClient(
        base_url=str(s.netbox_url),
        token=s.netbox_token,
        verify_tls=s.netbox_verify_tls,
        timeout_seconds=s.netbox_timeout_seconds,
        max_devices=s.netbox_sync_max_devices,
    )


def _identity_from_netbox(record: NetboxDeviceRecord) -> DeviceIdentity:
    serial = record.serial.lower() if record.serial else None
    if serial:
        return DeviceIdentity(serial_lower=serial, hostname_lower=None, site_lower=None)
    return DeviceIdentity(
        serial_lower=None,
        hostname_lower=record.name.lower(),
        site_lower=record.site.lower(),
    )


def _check_netbox_serial_duplicates(records: list[NetboxDeviceRecord]) -> None:
    by_serial: dict[str, list[int]] = {}
    for rec in records:
        if not rec.serial:
            continue
        key = rec.serial.lower()
        by_serial.setdefault(key, []).append(rec.id)
    conflicts = {k: ids for k, ids in by_serial.items() if len(ids) > 1}
    if conflicts:
        details = [
            {"serial_number": serial, "netbox_device_ids": ids}
            for serial, ids in sorted(conflicts.items())
        ]
        raise NetboxAmbiguousIdentity(
            "duplicate serial_number in NetBox",
            details=details,
        )


def _find_gard_device(session: Session, record: NetboxDeviceRecord) -> Device | None:
    by_nb = session.scalar(select(Device).where(Device.netbox_device_id == record.id))
    if by_nb is not None:
        return by_nb
    return _find_by_identity(session, _identity_from_netbox(record))


def _apply_netbox_fields(
    device: Device,
    record: NetboxDeviceRecord,
    *,
    now: dt.datetime,
) -> None:
    device.hostname = record.name
    device.site = record.site
    device.serial_number = record.serial
    device.role = record.role
    device.vendor_raw = record.vendor_raw
    device.model_raw = record.model_raw
    device.tags = list(record.tags)
    device.netbox_device_id = record.id
    device.netbox_last_synced_at = now
    device.source_system = "netbox"
    device.updated_at = now


def reconcile_devices(
    session: Session,
    records: list[NetboxDeviceRecord],
    *,
    now: dt.datetime | None = None,
) -> NetboxSyncReport:
    """Match NetBox rows to GARD devices; create missing; report orphans."""
    ts = now or utcnow()
    _check_netbox_serial_duplicates(records)

    report = NetboxSyncReport()
    matched_ids: set[uuid.UUID] = set()
    claimed_netbox_ids: set[int] = set()

    for record in records:
        if record.id in claimed_netbox_ids:
            raise NetboxAmbiguousIdentity(
                "duplicate netbox_device_id in NetBox payload",
                details=[{"netbox_device_id": record.id}],
            )
        claimed_netbox_ids.add(record.id)

        existing = _find_gard_device(session, record)
        if existing is None:
            existing = Device(
                id=uuid.uuid4(),
                hostname=record.name,
                site=record.site,
                serial_number=record.serial,
                vendor_raw=record.vendor_raw,
                model_raw=record.model_raw,
                source_system="netbox",
                lifecycle_state=LifecycleState.imported,
                created_at=ts,
                updated_at=ts,
            )
            session.add(existing)
            report.created_count += 1
        else:
            if existing.id in matched_ids:
                raise NetboxAmbiguousIdentity(
                    "two NetBox devices matched the same GARD device",
                    details=[
                        {
                            "device_id": str(existing.id),
                            "netbox_device_id": record.id,
                        }
                    ],
                )
            report.updated_count += 1

        _apply_netbox_fields(existing, record, now=ts)
        matched_ids.add(existing.id)
        report.matched_count += 1

    all_devices = list(session.scalars(select(Device)))
    for device in all_devices:
        if device.id in matched_ids:
            continue
        report.orphaned_in_gard.append(
            OrphanedDevice(
                device_id=device.id,
                hostname=device.hostname,
                serial_number=device.serial_number,
                site=device.site,
                reason="not_present_in_netbox",
            )
        )
    report.orphaned_count = len(report.orphaned_in_gard)
    session.flush()
    return report


def run_sync(
    *,
    session: Session,
    audit_session: Session,
    principal: Principal,
    client: NetboxClient | None = None,
    correlation_id: str | None = None,
    writeback_confirm: bool = False,
) -> NetboxSyncOutcome:
    """Pull NetBox devices and reconcile in one transaction."""
    cid = correlation_id or get_correlation_id() or str(uuid.uuid4())
    nb_client = client or client_from_settings()
    settings = get_settings()
    started = utcnow()

    audit_emit.emit(
        session=audit_session,
        action="netbox.sync.started",
        object_type="NetboxSyncRun",
        object_id="pending",
        principal=principal,
        correlation_id=cid,
        after={"correlation_id": cid},
    )

    try:
        records = nb_client.list_devices()
    except (NetboxNotConfigured, NetboxUnreachable) as exc:
        audit_emit.emit(
            session=audit_session,
            action="netbox.sync.failed",
            object_type="NetboxSyncRun",
            object_id="failed",
            principal=principal,
            result=AuditResult.failure,
            correlation_id=cid,
            after={"error": str(exc)},
        )
        raise

    run = NetboxSyncRun(
        id=uuid.uuid4(),
        status=NetboxSyncRunStatus.running,
        started_at=started,
        correlation_id=cid,
    )
    session.add(run)
    session.flush()

    try:
        report = reconcile_devices(session, records, now=started)
    except NetboxAmbiguousIdentity:
        session.rollback()
        audit_emit.emit(
            session=audit_session,
            action="netbox.sync.failed",
            object_type="NetboxSyncRun",
            object_id=str(run.id),
            principal=principal,
            result=AuditResult.failure,
            correlation_id=cid,
        )
        raise

    completed = utcnow()
    run.status = NetboxSyncRunStatus.completed
    run.completed_at = completed
    run.matched_count = report.matched_count
    run.created_count = report.created_count
    run.updated_count = report.updated_count
    run.orphaned_count = report.orphaned_count

    linked_devices = list(
        session.scalars(
            select(Device).where(
                Device.netbox_device_id.in_([r.id for r in records]),
            )
        )
    )

    writeback_report: WritebackReport
    if not settings.writeback_active():
        writeback_report = skipped_writeback_report(reason="write-back disabled or no write token")
    elif settings.netbox_url is not None and settings.requires_writeback_confirm(
        str(settings.netbox_url)
    ) and not writeback_confirm:
        writeback_report = skipped_writeback_report(
            reason="production/non-local NetBox requires confirm_writeback=true"
        )
    else:
        audit_emit.emit(
            session=audit_session,
            action="netbox.writeback.started",
            object_type="NetboxSyncRun",
            object_id=str(run.id),
            principal=principal,
            correlation_id=cid,
            after={"device_count": len(linked_devices)},
        )
        try:
            writeback_report = run_writeback(
                session=session,
                devices=linked_devices,
                settings=settings,
            )
        except NetboxWriteNotConfigured as exc:
            writeback_report = WritebackReport(
                phase=WritebackPhase.failed,
                summary=WritebackSummary(),
                entries=[],
            )
            audit_emit.emit(
                session=audit_session,
                action="netbox.writeback.failed",
                object_type="NetboxSyncRun",
                object_id=str(run.id),
                principal=principal,
                result=AuditResult.failure,
                correlation_id=cid,
                after={"error": str(exc)},
            )
        else:
            wb_action = (
                "netbox.writeback.completed"
                if writeback_report.phase
                in (WritebackPhase.completed, WritebackPhase.partial)
                else "netbox.writeback.failed"
            )
            audit_emit.emit(
                session=audit_session,
                action=wb_action,
                object_type="NetboxSyncRun",
                object_id=str(run.id),
                principal=principal,
                result=(
                    AuditResult.failure
                    if writeback_report.phase == WritebackPhase.failed
                    else AuditResult.success
                ),
                correlation_id=cid,
                after={
                    "phase": writeback_report.phase.value,
                    "updated": writeback_report.summary.updated,
                    "unchanged": writeback_report.summary.unchanged,
                    "conflict": writeback_report.summary.conflict,
                    "failed": writeback_report.summary.failed,
                },
            )

    report.writeback = writeback_report
    run.writeback_updated_count = writeback_report.summary.updated
    run.writeback_conflict_count = writeback_report.summary.conflict
    run.writeback_failed_count = writeback_report.summary.failed
    run.writeback_phase = writeback_report.phase.value

    audit_emit.emit(
        session=audit_session,
        action="netbox.sync.completed",
        object_type="NetboxSyncRun",
        object_id=str(run.id),
        principal=principal,
        correlation_id=cid,
        after={
            "matched_count": report.matched_count,
            "created_count": report.created_count,
            "updated_count": report.updated_count,
            "orphaned_count": report.orphaned_count,
        },
    )
    evidence_emit.emit(
        session=audit_session,
        evidence_type=EvidenceType.netbox_sync,
        subject_type="NetboxSyncRun",
        subject_id=str(run.id),
        principal=principal,
        after_state={
            "matched_count": report.matched_count,
            "created_count": report.created_count,
            "updated_count": report.updated_count,
            "orphaned_count": report.orphaned_count,
            "correlation_id": cid,
            "writeback": {
                "phase": writeback_report.phase.value,
                "updated": writeback_report.summary.updated,
                "unchanged": writeback_report.summary.unchanged,
                "conflict": writeback_report.summary.conflict,
                "failed": writeback_report.summary.failed,
            },
        },
        references={"netbox_device_count": len(records)},
    )
    session.flush()
    return NetboxSyncOutcome(run=run, report=report)


@dataclass(frozen=True)
class NetboxSummary:
    netbox_linked: int
    csv_only: int
    orphaned_in_gard: int
    last_sync_at: dt.datetime | None


def get_summary(session: Session) -> NetboxSummary:
    netbox_linked = (
        session.scalar(
            select(func.count()).select_from(Device).where(Device.netbox_device_id.is_not(None))
        )
        or 0
    )
    csv_only = (
        session.scalar(
            select(func.count()).select_from(Device).where(Device.netbox_device_id.is_(None))
        )
        or 0
    )
    last_run = session.scalar(
        select(NetboxSyncRun)
        .where(NetboxSyncRun.status == NetboxSyncRunStatus.completed)
        .order_by(NetboxSyncRun.completed_at.desc())
        .limit(1)
    )
    orphaned = last_run.orphaned_count if last_run is not None else 0
    last_sync_at = last_run.completed_at if last_run is not None else None
    return NetboxSummary(
        netbox_linked=netbox_linked,
        csv_only=csv_only,
        orphaned_in_gard=orphaned,
        last_sync_at=last_sync_at,
    )


def list_sync_runs(session: Session, *, limit: int = 20) -> list[NetboxSyncRun]:
    return list(
        session.scalars(
            select(NetboxSyncRun).order_by(NetboxSyncRun.started_at.desc()).limit(limit)
        )
    )


def get_sync_run(session: Session, run_id: uuid.UUID) -> NetboxSyncRun | None:
    return session.get(NetboxSyncRun, run_id)
