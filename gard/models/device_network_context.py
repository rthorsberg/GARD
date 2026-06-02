"""F12 device network context snapshot ORM model."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from gard.models import Base, utcnow, uuid7_default


class DeviceNetworkContext(Base):
    __tablename__ = "device_network_contexts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7_default)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ipam_alignment_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    netbox_device_id: Mapped[int] = mapped_column(Integer, nullable=False)
    primary_ip4: Mapped[str | None] = mapped_column(String(64), nullable=True)
    primary_ip6: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_mgmt_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mgmt_resolution_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    interfaces: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    overlay_bindings: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    captured_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
