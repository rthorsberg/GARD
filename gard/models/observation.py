"""`device_observations` — append-only record of one observation."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from gard.models import Base, utcnow, uuid7_default
from gard.models._enums import Confidence


class DeviceObservation(Base):
    __tablename__ = "device_observations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7_default)
    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False
    )
    import_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("import_jobs.id", ondelete="RESTRICT"), nullable=False
    )

    observed_firmware: Mapped[str | None] = mapped_column(String, nullable=True)
    observed_bootloader: Mapped[str | None] = mapped_column(String, nullable=True)
    observed_hardware_revision: Mapped[str | None] = mapped_column(String, nullable=True)
    observed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_by: Mapped[str] = mapped_column(String, nullable=False)

    confidence: Mapped[Confidence] = mapped_column(
        Enum(
            Confidence,
            name="observation_confidence",
            native_enum=False,
            length=32,
            values_callable=lambda x: [m.value for m in Confidence],
        ),
        nullable=False,
    )
    confidence_source: Mapped[str | None] = mapped_column(String, nullable=True)

    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_device_observations_device_created", "device_id", "created_at"),
        Index("ix_device_observations_confidence", "confidence"),
        Index(
            "ix_device_observations_raw_payload_gin",
            "raw_payload",
            postgresql_using="gin",
            postgresql_ops={"raw_payload": "jsonb_path_ops"},
        ),
    )
