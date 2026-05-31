"""`uplift_wave_devices` — (wave, device) join with F4 snapshot (F5).

Composite-PK join table. Snapshots the F4 readiness verdict at draft
time so a later F4 re-evaluation (which may produce a different
verdict) does not silently rewrite history. The wave's audit chain
references back to the snapshot via `readiness_evaluation_ref`; if
that F4 row is later pruned, the FK ON DELETE SET NULL keeps the
position + snapshot strings intact.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from gard.models import Base, utcnow


class UpliftWaveDevice(Base):
    __tablename__ = "uplift_wave_devices"

    wave_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("uplift_waves.id", ondelete="RESTRICT"), nullable=False
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False
    )

    # 1-based display order within the wave; (wave_id, position) is unique.
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    readiness_evaluation_ref: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("readiness_evaluations.id", ondelete="SET NULL"), nullable=True
    )
    snapshot_target_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    snapshot_observed_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    added_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    __table_args__ = (
        PrimaryKeyConstraint("wave_id", "device_id", name="pk_uplift_wave_devices"),
        CheckConstraint("position >= 1", name="ck_uplift_wave_devices_position_pos"),
        Index("ix_uplift_wave_devices_device", "device_id"),
        Index(
            "uq_uplift_wave_devices_wave_position",
            "wave_id",
            "position",
            unique=True,
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<UpliftWaveDevice wave={self.wave_id} device={self.device_id} pos={self.position}>"
