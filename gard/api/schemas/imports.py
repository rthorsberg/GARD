"""Import DTOs (T077)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


class ImportTotals(BaseModel):
    rows_total: int = 0
    rows_accepted: int = 0
    rows_rejected: int = 0
    rows_manual_review: int = 0
    rows_duplicate: int = 0
    devices_created: int = 0
    devices_updated: int = 0


class ImportSummary(BaseModel):
    job_id: uuid.UUID
    status: Literal["completed", "failed"]
    totals: ImportTotals
    correlation_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
    csv_schema_version: str = "1.0.0"


class ImportJobAck(BaseModel):
    job_id: uuid.UUID
    status: Literal["pending", "processing"]
    poll_url: str
    correlation_id: str | None = None


class ImportJobOut(BaseModel):
    id: uuid.UUID
    filename: str
    file_sha256: str
    file_size: int
    status: str
    started_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None
    actor: str
    is_override: bool
    created_at: dt.datetime
    totals: ImportTotals | None = None


class ImportRowError(BaseModel):
    row_number: int
    code: str
    message: str
    raw: dict[str, Any] | None = None


class ImportReport(BaseModel):
    job_id: uuid.UUID
    row_errors: list[ImportRowError]
    truncated: bool = False
