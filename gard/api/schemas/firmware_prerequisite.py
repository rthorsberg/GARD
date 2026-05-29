"""Response models for firmware-prerequisite endpoints (F2 / T049)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PredicateKind = Literal[
    "min_ram_mb",
    "min_disk_mb",
    "min_current_version",
    "hardware_revision_in",
    "license_present",
    "intermediate_version_required",
    "not_in_state",
    "region_in",
    "tagged_with",
]

PrereqSeverity = Literal["required", "recommended"]


class FirmwarePrerequisiteResponse(BaseModel):
    """One prerequisite rule as returned by the read endpoint."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    applies_to: dict[str, Any]
    predicate_kind: PredicateKind
    predicate_args: dict[str, Any]
    severity: PrereqSeverity
    evaluable: bool = Field(
        description=(
            "False when the predicate references a fact GARD cannot yet "
            "resolve (currently only `tagged_with`). The loader still "
            "accepts the rule; the engine returns `predicate_deferred`."
        ),
    )
    loaded_at: dt.datetime
    loaded_from_git_sha: str | None = None
    source_file_relpath: str


class FirmwarePrerequisiteList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[FirmwarePrerequisiteResponse]
    total_returned: int
