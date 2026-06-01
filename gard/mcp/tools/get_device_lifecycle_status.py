"""MCP tool: get_device_lifecycle_status.

REST parity: ``GET /api/v1/devices/{id}`` envelope shape.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.api.routers import devices as devices_router
from gard.api.schemas.devices import DeviceFacts
from gard.core.envelope import Reason, build_envelope
from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission
from gard.models import Device, DeviceObservation

TOOL_NAME = "get_device_lifecycle_status"
REQUIRED_PERMISSION = Permission.READ_DEVICE


class GetDeviceLifecycleStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_ref: dict[str, Any]


class GetDeviceLifecycleStatusOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device: DeviceFacts | None = None
    latest_observation: dict[str, Any] | None = None
    envelope: dict[str, Any]
    correlation_id: str


def _resolve_device(session: Session, ref: dict[str, Any]) -> Device | None:
    if "id" in ref:
        return session.get(Device, uuid.UUID(str(ref["id"])))
    if "serial_number" in ref:
        return session.scalar(
            select(Device).where(Device.serial_number.ilike(str(ref["serial_number"])))
        )
    if "hostname" in ref and "site" in ref:
        return session.scalar(
            select(Device)
            .where(Device.hostname.ilike(str(ref["hostname"])))
            .where(Device.site.ilike(str(ref["site"])))
        )
    return None


def invoke(
    *, session: Session, body: GetDeviceLifecycleStatusInput
) -> GetDeviceLifecycleStatusOutput:
    ref = body.device_ref
    device = _resolve_device(session, ref)
    cid = get_correlation_id() or str(uuid.uuid4())

    if device is None:
        env = build_envelope(
            state="unknown",
            summary="Device not found in GARD inventory",
            facts={"device_ref": ref},
            reasons=[
                Reason(
                    kind="missing_input",
                    ref="device_ref",
                    detail="no device matches the supplied identity keys",
                )
            ],
            confidence=0.0,
        )
        return GetDeviceLifecycleStatusOutput(
            device=None,
            latest_observation=None,
            envelope=env.model_dump(mode="json"),
            correlation_id=cid,
        )

    wrapped = devices_router._envelope_for(device, session)
    latest_row = session.scalar(
        select(DeviceObservation)
        .where(DeviceObservation.device_id == device.id)
        .order_by(DeviceObservation.created_at.desc())
        .limit(1)
    )
    latest = None
    if latest_row is not None:
        latest = {
            "id": str(latest_row.id),
            "observed_firmware": latest_row.observed_firmware,
            "observed_at": latest_row.observed_at.isoformat(),
            "confidence": latest_row.confidence.value,
            "confidence_source": latest_row.confidence_source,
        }
    return GetDeviceLifecycleStatusOutput(
        device=wrapped.facts,
        latest_observation=latest,
        envelope=wrapped.envelope.model_dump(mode="json"),
        correlation_id=cid,
    )
