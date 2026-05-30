"""Response models for the firmware-compliance read endpoint (F2 / T030).

Mirrors :class:`gard.core.envelope.FirmwareComplianceEnvelope` 1:1.
Kept separate so the API surface owns its own Pydantic models — the
core envelope can evolve internally without forcing an OpenAPI bump
unless we choose to.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FirmwareComplianceState = Literal[
    "classified",
    "target_defined",
    "compliant",
    "outside_target",
    "unknown",
]

FirmwareComplianceReasonKind = Literal[
    "target_matched",
    "target_runner_up",
    "version_match",
    "version_mismatch",
    "missing_observation",
    "no_target_matched",
    "empty_catalog",
    "predicate_deferred",
]


class FirmwareComplianceReasonModel(BaseModel):
    """One explanatory leaf in the envelope's ``reasons[]`` array."""

    model_config = ConfigDict(extra="forbid")

    kind: FirmwareComplianceReasonKind
    ref: str | None = Field(
        default=None,
        description="Stable id of the referenced entity (FirmwareTarget UUID, etc.).",
    )
    detail: str | None = Field(
        default=None,
        description="Human-readable narrative for the operator UI.",
    )


class FirmwareComplianceResponse(BaseModel):
    """Response shape for GET /api/v1/devices/{id}/firmware-compliance."""

    model_config = ConfigDict(extra="forbid")

    state: FirmwareComplianceState
    summary: str
    target_ref: str | None = Field(
        default=None,
        description="UUID of the matched FirmwareTarget (null when no target resolved).",
    )
    target_version: str | None = None
    observed_version: str | None = None
    facts: dict[str, Any] = Field(default_factory=dict)
    reasons: list[FirmwareComplianceReasonModel] = Field(default_factory=list)
    recommended_actions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Always [] in F2; populated by F3 (drift taxonomy + actions).",
    )
    confidence: float = Field(ge=0.0, le=1.0)
    as_of: dt.datetime
    correlation_id: str | None = None
