"""Response models for upgrade-path endpoints (F2 / T048)."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field


class FirmwareUpgradePathEdgeResponse(BaseModel):
    """One edge in the upgrade graph, as returned by the edges list endpoint."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    platform_family: str
    from_version: str
    to_version: str
    weight: int = Field(ge=1)
    notes: str | None = None
    loaded_at: dt.datetime
    loaded_from_git_sha: str | None = None
    source_file_relpath: str


class FirmwareUpgradePathEdgeList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[FirmwareUpgradePathEdgeResponse]
    total_returned: int


class UpgradePathChainReason(BaseModel):
    """One explanatory leaf for a chain result.

    Mirrors :class:`gard.core.upgrade_path_graph.ChainResult.reasons`.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str
    detail: str | None = None


class UpgradePathChainResponse(BaseModel):
    """Shortest-path query result.

    Per FR-016..FR-019:
    - ``from == to`` → ``chain=[from]``, ``hop_count=0``, ``total_weight=0``.
    - ``platform_family`` not in catalog → empty chain, ``reasons[0].kind="platform_not_found"``.
    - No path → empty chain, ``reasons[0].kind="no_path"``.
    """

    model_config = ConfigDict(extra="forbid")

    platform_family: str
    from_version: str
    to_version: str
    chain: list[str]
    hop_count: int = Field(ge=0)
    total_weight: int | None = None
    reasons: list[UpgradePathChainReason] = Field(default_factory=list)
