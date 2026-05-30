"""`firmware_upgrade_paths` — one row per directed edge in the upgrade graph (F2)."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from gard.models import Base, utcnow, uuid7_default


class FirmwareUpgradePath(Base):
    __tablename__ = "firmware_upgrade_paths"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7_default)

    # Common catalog columns ----------------------------------------------
    loaded_from_git_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    loaded_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    removed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_file_relpath: Mapped[str] = mapped_column(String, nullable=False)
    catalog_schema_version: Mapped[str] = mapped_column(String(16), nullable=False)

    # Entity-specific -----------------------------------------------------
    platform_family: Mapped[str] = mapped_column(String, nullable=False)
    from_version: Mapped[str] = mapped_column(String, nullable=False)
    to_version: Mapped[str] = mapped_column(String, nullable=False)
    weight: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("weight >= 1", name="firmware_upgrade_path_weight_min"),
        Index(
            "ix_firmware_upgrade_paths_platform_versions",
            "platform_family",
            "removed_at",
            "from_version",
            "to_version",
        ),
        Index(
            "uq_firmware_upgrade_paths_edge_live",
            "platform_family",
            "from_version",
            "to_version",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<FirmwareUpgradePath {self.platform_family} "
            f"{self.from_version}->{self.to_version} w={self.weight}>"
        )
