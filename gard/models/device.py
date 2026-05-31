"""`devices` — canonical, deduplicated record per device."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET
from sqlalchemy.orm import Mapped, mapped_column

from gard.models import Base, utcnow, uuid7_default
from gard.models._enums import LifecycleState


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7_default)

    serial_number: Mapped[str | None] = mapped_column(String, nullable=True)
    hostname: Mapped[str] = mapped_column(String, nullable=False)
    site: Mapped[str] = mapped_column(String, nullable=False)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str | None] = mapped_column(String, nullable=True)
    management_ip: Mapped[str | None] = mapped_column(INET, nullable=True)

    vendor_raw: Mapped[str] = mapped_column(String, nullable=False)
    vendor_normalized: Mapped[str | None] = mapped_column(String, nullable=True)
    model_raw: Mapped[str] = mapped_column(String, nullable=False)
    model_normalized: Mapped[str | None] = mapped_column(String, nullable=True)
    platform_family: Mapped[str | None] = mapped_column(String, nullable=True)
    hardware_revision: Mapped[str | None] = mapped_column(String, nullable=True)

    # F2 — new optional observation columns (Constitution III: never coerced).
    ram_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    disk_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    licenses: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    # F7 — NetBox identity reference (read-only sync).
    netbox_device_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    netbox_last_synced_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    source_system: Mapped[str] = mapped_column(String, nullable=False)
    lifecycle_state: Mapped[LifecycleState] = mapped_column(
        Enum(
            LifecycleState,
            name="lifecycle_state",
            native_enum=False,
            length=32,
            values_callable=lambda x: [m.value for m in LifecycleState],
        ),
        nullable=False,
        default=LifecycleState.imported,
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
    )

    __table_args__ = (
        # Identity invariant from data-model.md §Device:
        CheckConstraint(
            "serial_number IS NOT NULL OR (hostname IS NOT NULL AND site IS NOT NULL)",
            name="device_identity_present",
        ),
        CheckConstraint(
            "length(vendor_raw) > 0 OR length(model_raw) > 0",
            name="device_vendor_or_model_present",
        ),
        # Partial unique on lower(serial_number) where present:
        Index(
            "uq_devices_serial_lower",
            text("lower(serial_number)"),
            unique=True,
            postgresql_where=text("serial_number IS NOT NULL"),
        ),
        # Partial unique on (lower(hostname), lower(site)) when serial absent:
        Index(
            "uq_devices_hostname_site_lower",
            text("lower(hostname)"),
            text("lower(site)"),
            unique=True,
            postgresql_where=text("serial_number IS NULL"),
        ),
        Index("ix_devices_vendor_model", "vendor_normalized", "model_normalized"),
        Index("ix_devices_lifecycle_state", "lifecycle_state"),
        Index(
            "uq_devices_netbox_device_id",
            "netbox_device_id",
            unique=True,
            postgresql_where=text("netbox_device_id IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Device id={self.id} hostname={self.hostname!r} site={self.site!r}>"
