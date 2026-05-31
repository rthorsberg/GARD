"""MCP tool: explain_wave."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from gard.core import readiness_evaluation_controller as readiness_ctrl
from gard.core import uplift_wave_controller as wave_ctrl
from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission

TOOL_NAME = "explain_wave"
REQUIRED_PERMISSION = Permission.READ_UPLIFT


class ExplainWaveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wave_id: uuid.UUID


class ExplainWaveDeviceRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: uuid.UUID
    hostname: str
    readiness_state_at_draft: str | None = None
    readiness_state_now: str | None = None


class ExplainWaveOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wave_id: uuid.UUID
    plan_id: uuid.UUID
    name: str
    state: str
    target_version: str
    change_window: dict[str, str]
    drafted_by: str
    approved_by: str | None = None
    approval_citation: str | None = None
    invalidated_reason: str | None = None
    devices: list[ExplainWaveDeviceRow] = []
    correlation_id: str


def invoke(
    *,
    session: Session,
    body: ExplainWaveInput,
) -> ExplainWaveOutput:
    wave = wave_ctrl.get_wave(session, body.wave_id)
    if wave is None:
        raise ValueError(f"wave not found: {body.wave_id}")

    device_rows: list[ExplainWaveDeviceRow] = []
    for device, _wd in wave_ctrl.load_wave_members(session, body.wave_id):
        latest = readiness_ctrl.latest_evaluation_for(session, device.id)
        device_rows.append(
            ExplainWaveDeviceRow(
                device_id=device.id,
                hostname=device.hostname,
                readiness_state_at_draft="ready_for_uplift",
                readiness_state_now=latest.readiness_state if latest else None,
            )
        )

    return ExplainWaveOutput(
        wave_id=wave.id,
        plan_id=wave.plan_id,
        name=wave.name,
        state=wave.state,
        target_version=wave.target_version,
        change_window={
            "start": wave.change_window_start.isoformat(),
            "end": wave.change_window_end.isoformat(),
        },
        drafted_by=wave.drafted_by,
        approved_by=wave.approved_by,
        approval_citation=wave.approval_citation,
        invalidated_reason=wave.invalidated_reason,
        devices=device_rows,
        correlation_id=get_correlation_id() or "anonymous-correlation",
    )
