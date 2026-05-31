"""MCP tool: list_open_waves."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from gard.core import uplift_wave_controller as wave_ctrl
from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission

TOOL_NAME = "list_open_waves"
REQUIRED_PERMISSION = Permission.READ_UPLIFT


class ListOpenWavesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: uuid.UUID | None = None
    region: str | None = None
    platform_family: str | None = None
    limit: int = Field(default=100, ge=1, le=500)


class OpenWaveRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wave_id: uuid.UUID
    plan_id: uuid.UUID
    name: str
    state: str
    target_version: str
    device_count: int = Field(ge=0)
    change_window_start: str
    drafted_by: str
    drafted_at: str


class ListOpenWavesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OpenWaveRow] = Field(default_factory=list)
    total_returned: int = Field(ge=0)
    correlation_id: str


def invoke(
    *,
    session: Session,
    body: ListOpenWavesInput,
) -> ListOpenWavesOutput:
    items: list[OpenWaveRow] = []
    for state in ("draft", "submitted"):
        waves, _ = wave_ctrl.list_waves(
            session,
            plan_id=body.plan_id,
            state=state,
            region=body.region,
            platform_family=body.platform_family,
            limit=body.limit,
        )
        for wave in waves:
            members = wave_ctrl.load_wave_members(session, wave.id)
            items.append(
                OpenWaveRow(
                    wave_id=wave.id,
                    plan_id=wave.plan_id,
                    name=wave.name,
                    state=wave.state,
                    target_version=wave.target_version,
                    device_count=len(members),
                    change_window_start=wave.change_window_start.isoformat(),
                    drafted_by=wave.drafted_by,
                    drafted_at=wave.drafted_at.isoformat(),
                )
            )
            if len(items) >= body.limit:
                break
        if len(items) >= body.limit:
            break

    return ListOpenWavesOutput(
        items=items[: body.limit],
        total_returned=min(len(items), body.limit),
        correlation_id=get_correlation_id() or "anonymous-correlation",
    )
