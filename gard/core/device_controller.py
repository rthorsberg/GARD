"""Device upsert / list / get (T076)."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from gard.api.schemas.csv_row import CsvRow
from gard.core.identity import DeviceIdentity, from_csv
from gard.core.normalization_engine import NormalizationResult
from gard.models import Device, utcnow
from gard.models._enums import Confidence, LifecycleState


@dataclass(frozen=True)
class UpsertResult:
    device: Device
    created: bool
    classified: bool


def _find_by_identity(session: Session, ident: DeviceIdentity) -> Device | None:
    if ident.serial_lower:
        return session.scalar(
            select(Device)
            .where(Device.serial_number.is_not(None))
            .where(Device.serial_number.ilike(ident.serial_lower))
        )
    return session.scalar(
        select(Device)
        .where(Device.serial_number.is_(None))
        .where(Device.hostname.ilike(ident.hostname_lower or ""))
        .where(Device.site.ilike(ident.site_lower or ""))
    )


def upsert_from_row(
    *,
    session: Session,
    row: CsvRow,
    normalization: NormalizationResult,
    source_system: str,
    now: dt.datetime | None = None,
) -> UpsertResult:
    """Insert a Device or update the latest-observation fields on an existing one."""
    ident = from_csv(row)
    existing = _find_by_identity(session, ident)
    ts = now or utcnow()

    classified = normalization.confidence != Confidence.manual_review_required
    target_state = LifecycleState.classified if classified else LifecycleState.imported

    if existing is None:
        device = Device(
            id=uuid.uuid4(),  # using v4 for ergonomics; UUID7 default is fine too
            serial_number=row.serial_number,
            hostname=row.hostname,
            site=row.site,
            region=row.region,
            role=row.role,
            management_ip=row.management_ip,
            vendor_raw=row.vendor_raw,
            vendor_normalized=normalization.output.get("vendor_normalized"),
            model_raw=row.model_raw,
            model_normalized=normalization.output.get("model_normalized"),
            platform_family=normalization.output.get("platform_family"),
            hardware_revision=row.hardware_revision,
            source_system=source_system,
            lifecycle_state=target_state,
            created_at=ts,
            updated_at=ts,
        )
        session.add(device)
        session.flush()
        return UpsertResult(device=device, created=True, classified=classified)

    existing.vendor_raw = row.vendor_raw
    existing.model_raw = row.model_raw
    if row.region is not None:
        existing.region = row.region
    if row.role is not None:
        existing.role = row.role
    if row.management_ip is not None:
        existing.management_ip = row.management_ip
    if row.hardware_revision is not None:
        existing.hardware_revision = row.hardware_revision

    if normalization.output:
        if "vendor_normalized" in normalization.output:
            existing.vendor_normalized = normalization.output["vendor_normalized"]
        if "model_normalized" in normalization.output:
            existing.model_normalized = normalization.output["model_normalized"]
        if "platform_family" in normalization.output:
            existing.platform_family = normalization.output["platform_family"]

    if classified and existing.lifecycle_state == LifecycleState.imported:
        existing.lifecycle_state = LifecycleState.classified

    existing.source_system = source_system
    existing.updated_at = ts
    session.flush()
    return UpsertResult(device=existing, created=False, classified=classified)


def list_devices(
    *,
    session: Session,
    vendor_normalized: str | None = None,
    model_normalized: str | None = None,
    site: str | None = None,
    region: str | None = None,
    lifecycle_state: LifecycleState | None = None,
    limit: int = 50,
) -> list[Device]:
    stmt = select(Device).order_by(Device.created_at.desc()).limit(limit)
    if vendor_normalized:
        stmt = stmt.where(Device.vendor_normalized.ilike(vendor_normalized))
    if model_normalized:
        stmt = stmt.where(Device.model_normalized.ilike(model_normalized))
    if site:
        stmt = stmt.where(Device.site.ilike(site))
    if region:
        stmt = stmt.where(or_(Device.region.is_(None), Device.region.ilike(region)))
    if lifecycle_state:
        stmt = stmt.where(Device.lifecycle_state == lifecycle_state)
    return list(session.scalars(stmt))


def get_device(session: Session, device_id: uuid.UUID) -> Device | None:
    return session.get(Device, device_id)
