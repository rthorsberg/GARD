"""`import_jobs` — record of one CSV ingest attempt."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from gard.models import Base, utcnow, uuid7_default
from gard.models._enums import ImportStatus


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7_default)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)

    row_count_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_count_accepted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_count_rejected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_count_manual_review: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_count_duplicate: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[ImportStatus] = mapped_column(
        Enum(
            ImportStatus,
            name="import_status",
            native_enum=False,
            length=16,
            values_callable=lambda x: [m.value for m in ImportStatus],
        ),
        nullable=False,
        default=ImportStatus.pending,
    )
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    error_report: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    actor: Mapped[str] = mapped_column(String, nullable=False)
    is_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "uq_import_jobs_file_sha256",
            "file_sha256",
            unique=True,
            postgresql_where=text("is_override = false"),
        ),
        Index("ix_import_jobs_status_created", "status", "created_at"),
    )
