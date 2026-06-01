"""MCP tool: get_target_firmware.

REST parity: ``GET /api/v1/devices/{id}/firmware-compliance``.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from gard.api.schemas.firmware_compliance import FirmwareComplianceReasonModel
from gard.core import compliance_controller
from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission
from gard.models import Device
from gard.models._enums import ActorType

TOOL_NAME = "get_target_firmware"
REQUIRED_PERMISSION = Permission.READ_FIRMWARE_CATALOG


class GetTargetFirmwareInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: uuid.UUID


class GetTargetFirmwareOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str
    summary: str
    target_ref: str | None = None
    target_version: str | None = None
    observed_version: str | None = None
    facts: dict[str, Any]
    reasons: list[FirmwareComplianceReasonModel]
    recommended_actions: list[dict[str, Any]]
    confidence: float
    as_of: str
    correlation_id: str


def invoke(*, session: Session, body: GetTargetFirmwareInput) -> GetTargetFirmwareOutput:
    if session.get(Device, body.device_id) is None:
        from gard.core.envelope import FirmwareComplianceReason, build_firmware_compliance_envelope

        env = build_firmware_compliance_envelope(
            state="classified",
            summary="Device not found — cannot resolve firmware target",
            observed_version=None,
            reasons=[
                FirmwareComplianceReason(
                    kind="missing_input",  # type: ignore[arg-type]
                    ref=str(body.device_id),
                    detail="device not found in GARD inventory",
                )
            ],
            confidence=0.0,
            correlation_id=get_correlation_id(),
        )
    else:
        env = compliance_controller.evaluate(
            session=session,
            audit_session=session,
            device_id=body.device_id,
            actor="mcp",
            actor_type=ActorType.mcp_client,
        )
    return GetTargetFirmwareOutput(
        state=env.state,
        summary=env.summary,
        target_ref=env.target_ref,
        target_version=env.target_version,
        observed_version=env.observed_version,
        facts=env.facts,
        reasons=[
            FirmwareComplianceReasonModel(kind=r.kind, ref=r.ref, detail=r.detail)
            for r in env.reasons
        ],
        recommended_actions=env.recommended_actions,
        confidence=env.confidence,
        as_of=env.as_of.isoformat(),
        correlation_id=get_correlation_id() or env.correlation_id or str(uuid.uuid4()),
    )
