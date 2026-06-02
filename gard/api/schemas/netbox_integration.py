"""F7/F10 NetBox integration REST DTOs."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from gard.api.schemas.ipam_alignment import IpamAlignmentReportOut


class OrphanedDeviceOut(BaseModel):
    device_id: uuid.UUID
    hostname: str
    serial_number: str | None = None
    site: str | None = None
    reason: str


class WritebackConflictOut(BaseModel):
    field: str
    expected: str
    actual: str


class WritebackEntryOut(BaseModel):
    device_id: uuid.UUID
    netbox_device_id: int
    status: Literal["updated", "skipped", "unchanged", "conflict", "failed"]
    message: str | None = None
    conflicts: list[WritebackConflictOut] = Field(default_factory=list)


class WritebackSummaryOut(BaseModel):
    updated: int = Field(ge=0)
    skipped: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    conflict: int = Field(ge=0)
    failed: int = Field(ge=0)
    skipped_not_linked: int = Field(ge=0)


class WritebackReportOut(BaseModel):
    phase: Literal["completed", "partial", "failed", "skipped"]
    summary: WritebackSummaryOut
    entries: list[WritebackEntryOut] = Field(default_factory=list)


class NetboxSyncReportOut(BaseModel):
    matched_count: int = Field(ge=0)
    created_count: int = Field(ge=0)
    updated_count: int = Field(ge=0)
    orphaned_count: int = Field(ge=0)
    orphaned_in_gard: list[OrphanedDeviceOut] = Field(default_factory=list)
    ipam_alignment: IpamAlignmentReportOut | None = None
    writeback: WritebackReportOut | None = None


class NetboxSyncRunOut(BaseModel):
    id: uuid.UUID
    status: str
    started_at: dt.datetime
    completed_at: dt.datetime | None = None
    correlation_id: str
    matched_count: int = Field(ge=0)
    created_count: int = Field(ge=0)
    updated_count: int = Field(ge=0)
    orphaned_count: int = Field(ge=0)
    error_summary: str | None = None


class NetboxSyncEnvelope(BaseModel):
    data: dict[str, object]


class NetboxSummaryOut(BaseModel):
    netbox_linked: int = Field(ge=0)
    csv_only: int = Field(ge=0)
    orphaned_in_gard: int = Field(ge=0)
    last_sync_at: dt.datetime | None = None


class NetboxSummaryEnvelope(BaseModel):
    data: NetboxSummaryOut


class NetboxSyncRunList(BaseModel):
    data: list[NetboxSyncRunOut]
    pagination: dict[str, str | None]
