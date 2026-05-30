"""`firmware_targets` — operator-authored firmware policy rows (F2).

A FirmwareTarget says: "Devices matching ``scope_selector`` on
``platform_family`` should be on ``target_version``." The row is a
read-through cache of a YAML file under
``gard-catalog/firmware/targets/``. Mutation is **never** by API call;
the loader is the only writer (insert / soft-delete / resurrect).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Date, DateTime, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from gard.models import Base, utcnow, uuid7_default


class FirmwareTarget(Base):
    __tablename__ = "firmware_targets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7_default)

    # Common catalog columns (data-model.md §1 preamble) -------------------
    loaded_from_git_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    loaded_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    removed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_file_relpath: Mapped[str] = mapped_column(String, nullable=False)
    catalog_schema_version: Mapped[str] = mapped_column(String(16), nullable=False)

    # Entity-specific columns ---------------------------------------------
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    platform_family: Mapped[str] = mapped_column(String, nullable=False)
    target_version: Mapped[str] = mapped_column(String, nullable=False)
    scope_selector: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # Policy window — calendar dates (not datetimes); matches release_date
    # convention on FirmwarePackage and the YAML fixtures.
    valid_from: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "ix_firmware_targets_platform_removed",
            "platform_family",
            "removed_at",
        ),
        Index(
            "uq_firmware_targets_name_live",
            "name",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
        Index("ix_firmware_targets_source_file", "source_file_relpath"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<FirmwareTarget id={self.id} name={self.name!r} "
            f"platform={self.platform_family} target={self.target_version}>"
        )
