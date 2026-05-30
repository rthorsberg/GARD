"""Response models for firmware-package endpoints (F2 / T056)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PackageVendor = Literal["cisco", "juniper", "nokia"]


class FirmwarePackageResponse(BaseModel):
    """One firmware-package row as returned by the read endpoints."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    vendor: PackageVendor
    platform_family: str
    version: str
    sha256: str = Field(min_length=64, max_length=64, description="Hex-encoded SHA-256.")
    byte_size: int = Field(ge=1)
    signed_by: str
    release_date: dt.date | None = None
    download_url: str | None = None
    notes: str | None = None
    blob_present: bool = Field(
        description="True iff bytes have been uploaded and verified against the declared sha256.",
    )
    blob_stored_at: dt.datetime | None = None
    loaded_at: dt.datetime
    loaded_from_git_sha: str | None = None
    source_file_relpath: str


class FirmwarePackageList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[FirmwarePackageResponse]
    total_returned: int


class BlobUploadReceipt(BaseModel):
    """Response body for a successful POST .../blob."""

    model_config = ConfigDict(extra="forbid")

    package_id: uuid.UUID
    computed_sha256: str = Field(min_length=64, max_length=64)
    bytes_written: int = Field(ge=1)
    stored_at: dt.datetime
    correlation_id: str | None = None
