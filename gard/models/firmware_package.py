"""`firmware_packages` — installer artefact metadata + optional blob pointer (F2).

A FirmwarePackage declares: "Here is an installer for (vendor, platform_family,
version) whose SHA-256 is X and byte_size is N." The blob itself (if uploaded)
lives in the BlobStore, content-addressed by SHA. The DB row carries metadata
and a ``blob_present`` flag indicating whether bytes have been stored.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from gard.models import Base, utcnow, uuid7_default


class FirmwarePackage(Base):
    __tablename__ = "firmware_packages"

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
    vendor: Mapped[str] = mapped_column(String, nullable=False)
    platform_family: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[str] = mapped_column(String, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    signed_by: Mapped[str] = mapped_column(String, nullable=False)
    release_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    download_url: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    blob_present: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    blob_stored_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint("length(sha256) = 64", name="firmware_package_sha256_len"),
        CheckConstraint("byte_size > 0", name="firmware_package_byte_size_positive"),
        Index(
            "ix_firmware_packages_vendor_platform_version",
            "vendor",
            "platform_family",
            "version",
            "removed_at",
        ),
        Index(
            "uq_firmware_packages_natural_live",
            "vendor",
            "platform_family",
            "version",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
        Index("ix_firmware_packages_source_file", "source_file_relpath"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<FirmwarePackage id={self.id} {self.vendor}/{self.platform_family}/"
            f"{self.version} blob={self.blob_present}>"
        )
