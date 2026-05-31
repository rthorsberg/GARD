"""MCP tool: create_uplift_wave_draft (R-9 read-shaped proposal)."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from gard.core import uplift_wave_controller as wave_ctrl
from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission

TOOL_NAME = "create_uplift_wave_draft"
REQUIRED_PERMISSION = Permission.READ_UPLIFT


class CreateUpliftWaveDraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    target_version: str = Field(min_length=1, max_length=64)
    target_platform_family: str = Field(min_length=1, max_length=64)
    scope_selector: dict[str, object]
    change_window_start: dt.datetime
    change_window_end: dt.datetime
    mode: str = "strict"


class WaveDraftDeviceRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: uuid.UUID
    hostname: str
    readiness_state: str | None = None
    target_version: str | None = None
    observed_version: str | None = None


class CreateUpliftWaveDraftOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposed_devices: int = Field(ge=0)
    skipped: int = Field(ge=0)
    devices: list[WaveDraftDeviceRow] = Field(default_factory=list)
    change_window_valid: bool
    target_version_live: bool
    warnings: list[str] = Field(default_factory=list)
    correlation_id: str


def invoke(
    *,
    session: Session,
    body: CreateUpliftWaveDraftInput,
) -> CreateUpliftWaveDraftOutput:
    preview = wave_ctrl.preview_wave_draft(
        session,
        target_version=body.target_version,
        target_platform_family=body.target_platform_family,
        scope_selector=body.scope_selector,
        mode=body.mode,
        change_window_start=body.change_window_start,
        change_window_end=body.change_window_end,
    )
    devices = [
        WaveDraftDeviceRow(
            device_id=uuid.UUID(str(row["device_id"])),
            hostname=str(row["hostname"]),
            readiness_state=row.get("readiness_state"),  # type: ignore[arg-type]
            target_version=row.get("target_version"),  # type: ignore[arg-type]
            observed_version=row.get("observed_version"),  # type: ignore[arg-type]
        )
        for row in preview.device_rows
    ]
    return CreateUpliftWaveDraftOutput(
        proposed_devices=preview.proposed_devices,
        skipped=len(preview.skipped),
        devices=devices,
        change_window_valid=preview.change_window_valid,
        target_version_live=preview.target_version_live,
        warnings=preview.warnings,
        correlation_id=get_correlation_id() or "anonymous-correlation",
    )
