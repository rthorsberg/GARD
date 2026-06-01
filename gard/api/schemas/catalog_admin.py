"""Request/response models for the lab catalog editor API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CatalogReloadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    normalization_loaded: int
    normalization_errors: list[str]
    firmware_loaded: int
    firmware_removed: int
    devices_reevaluated: int


class UpsertFirmwareTargetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=63)
    platform_family: str = Field(min_length=1)
    target_version: str = Field(min_length=1)
    scope_selector: dict[str, Any]
    notes: str | None = None
    reload: bool = True


class AddUpgradePathEdgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform_family: str = Field(min_length=1)
    from_version: str = Field(min_length=1)
    to_version: str = Field(min_length=1)
    weight: int = Field(default=1, ge=1)
    notes: str | None = None
    file_stem: str | None = None
    reload: bool = True


class CreateNormalizationRuleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_pattern: str = Field(
        min_length=1,
        description="Regex matched against model_raw (e.g. (?i)ISR1121)",
    )
    vendor_normalized: str = Field(min_length=1)
    platform_family: str = Field(min_length=1)
    model_normalized: str | None = None
    priority: int = Field(default=200, ge=1)
    notes: str | None = None
    renormalize: bool = True


class NormalizationRuleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    priority: int
    match: dict[str, Any]
    output: dict[str, Any]
    confidence: str
    enabled: bool
    notes: str | None = None


class NormalizationRuleList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[NormalizationRuleResponse]
    total_returned: int


class RenormalizeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    devices_updated: int
