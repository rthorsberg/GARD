"""`audit_events` + `audit_chain_heads` — append-only audit log."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Date, DateTime, Enum, Index, String, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from gard.models import Base, utcnow, uuid7_default
from gard.models._enums import ActorType, AuditResult


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7_default)
    timestamp: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    actor: Mapped[str] = mapped_column(String, nullable=False)
    actor_type: Mapped[ActorType] = mapped_column(
        Enum(ActorType, name="audit_actor_type", native_enum=False, length=16),
        nullable=False,
    )

    action: Mapped[str] = mapped_column(String(128), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str] = mapped_column(String(128), nullable=False)

    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    result: Mapped[AuditResult] = mapped_column(
        Enum(AuditResult, name="audit_result", native_enum=False, length=16),
        nullable=False,
    )

    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_ip: Mapped[str | None] = mapped_column(INET, nullable=True)

    row_hash: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("ix_audit_events_timestamp", "timestamp"),
        Index("ix_audit_events_object", "object_type", "object_id", "timestamp"),
        Index("ix_audit_events_correlation_id", "correlation_id"),
        Index("ix_audit_events_actor_timestamp", "actor", "timestamp"),
    )


class AuditChainHead(Base):
    __tablename__ = "audit_chain_heads"

    day: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    last_event_hash: Mapped[str] = mapped_column(Text, nullable=False)
    sealed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
