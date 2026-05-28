"""`manual_mappings` — explicit operator-supplied normalization."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from gard.models import Base, utcnow, uuid7_default


class ManualMapping(Base):
    __tablename__ = "manual_mappings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7_default)
    observation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("device_observations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    vendor_normalized: Mapped[str] = mapped_column(String, nullable=False)
    model_normalized: Mapped[str] = mapped_column(String, nullable=False)
    platform_family: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("observation_id", name="uq_manual_mappings_observation"),)
