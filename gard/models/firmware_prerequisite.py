"""`firmware_prerequisite_rules` — declarative rules consumed by F4's evaluator (F2)."""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from gard.models import Base, utcnow, uuid7_default


class PredicateKind(enum.StrEnum):
    min_ram_mb = "min_ram_mb"
    min_disk_mb = "min_disk_mb"
    min_current_version = "min_current_version"
    hardware_revision_in = "hardware_revision_in"
    license_present = "license_present"
    intermediate_version_required = "intermediate_version_required"
    not_in_state = "not_in_state"
    region_in = "region_in"
    tagged_with = "tagged_with"


class PrereqSeverity(enum.StrEnum):
    required = "required"
    recommended = "recommended"


class FirmwarePrerequisiteRule(Base):
    __tablename__ = "firmware_prerequisite_rules"

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
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    applies_to: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    predicate_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    predicate_args: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    severity: Mapped[str] = mapped_column(
        String(16), nullable=False, default="required", server_default=text("'required'")
    )
    evaluable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    __table_args__ = (
        CheckConstraint(
            "predicate_kind IN ('min_ram_mb', 'min_disk_mb', 'min_current_version', "
            "'hardware_revision_in', 'license_present', 'intermediate_version_required', "
            "'not_in_state', 'region_in', 'tagged_with')",
            name="firmware_prereq_predicate_kind",
        ),
        CheckConstraint(
            "severity IN ('required', 'recommended')",
            name="firmware_prereq_severity",
        ),
        Index("ix_firmware_prereq_kind_removed", "predicate_kind", "removed_at"),
        Index(
            "uq_firmware_prereq_name_live",
            "name",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<FirmwarePrerequisiteRule id={self.id} name={self.name!r} "
            f"kind={self.predicate_kind} evaluable={self.evaluable}>"
        )
