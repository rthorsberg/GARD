"""Pydantic response models for the FirmwareTarget read API (F2 / T037).

`FirmwareTargetResponse` mirrors the public-facing fields of
`gard.models.FirmwareTarget`. The catalog tables carry a few internal
columns (`catalog_schema_version`) that are deliberately omitted from the
API surface — they're loader bookkeeping, not policy data.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FirmwareTargetResponse(BaseModel):
    """One firmware-target row as returned by GET /api/v1/firmware/targets."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    platform_family: str
    target_version: str
    scope_selector: dict[str, Any]
    valid_from: dt.date | None = None
    valid_until: dt.date | None = None
    notes: str | None = None
    loaded_at: dt.datetime
    loaded_from_git_sha: str | None = Field(
        default=None,
        description=(
            "Git SHA of the file at load time. Null only when the loader "
            "ran outside a git repo or against an uncommitted file."
        ),
    )
    source_file_relpath: str


class FirmwareTargetList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[FirmwareTargetResponse]
    total_returned: int
