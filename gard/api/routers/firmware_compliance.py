"""F2 firmware-compliance read endpoint (T031).

GET /api/v1/devices/{device_id}/firmware-compliance — given a device id,
resolve which FirmwareTarget applies (if any), compare to observed
firmware, and return the compliance envelope.

Idempotent on the read side: re-calling the endpoint against unchanged
state produces no audit emits (the controller short-circuits on
unchanged state). State transitions are written back to the device row
in the request transaction.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from gard.api.middleware.rbac import require
from gard.api.schemas.firmware_compliance import (
    FirmwareComplianceReasonModel,
    FirmwareComplianceResponse,
)
from gard.core import compliance_controller
from gard.core.rbac import Permission, Principal
from gard.db.session import get_append_only_session, get_session
from gard.models import Device
from gard.models._enums import ActorType

router = APIRouter(prefix="/api/v1/devices", tags=["firmware-compliance"])


@router.get(
    "/{device_id}/firmware-compliance",
    response_model=FirmwareComplianceResponse,
    summary="Resolve firmware-target compliance for one device",
)
def evaluate(
    device_id: uuid.UUID,
    principal: Principal = Depends(require(Permission.READ_FIRMWARE_CATALOG)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> FirmwareComplianceResponse:
    # 404 is only emitted when the device itself is missing — empty catalog
    # is a successful response carrying state=classified + reasons=[empty_catalog].
    if session.get(Device, device_id) is None:
        raise HTTPException(status_code=404, detail="device not found")

    env = compliance_controller.evaluate(
        session=session,
        audit_session=audit_session,
        device_id=device_id,
        actor=principal.subject,
        actor_type=ActorType(principal.actor_type),
    )
    return FirmwareComplianceResponse(
        state=env.state,
        summary=env.summary,
        target_ref=env.target_ref,
        target_version=env.target_version,
        observed_version=env.observed_version,
        facts=env.facts,
        reasons=[
            FirmwareComplianceReasonModel(
                kind=r.kind,
                ref=r.ref,
                detail=r.detail,
            )
            for r in env.reasons
        ],
        recommended_actions=env.recommended_actions,
        confidence=env.confidence,
        as_of=env.as_of,
        correlation_id=env.correlation_id,
    )
