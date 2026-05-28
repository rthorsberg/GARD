"""`lifecycle_evidence` — append-only proof of lifecycle-relevant events."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import DateTime, Enum, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from gard.models import Base, utcnow, uuid7_default
from gard.models._enums import EvidenceType


class LifecycleEvidence(Base):
    __tablename__ = "lifecycle_evidence"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7_default)
    evidence_type: Mapped[EvidenceType] = mapped_column(
        Enum(EvidenceType, name="evidence_type", native_enum=False, length=32),
        nullable=False,
    )
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)

    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    actor: Mapped[str] = mapped_column(String, nullable=False)
    system: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    source_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    references: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    row_hash: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("ix_lifecycle_evidence_subject", "subject_type", "subject_id", "timestamp"),
        Index("ix_lifecycle_evidence_type", "evidence_type"),
        Index("ix_lifecycle_evidence_timestamp", "timestamp"),
    )
