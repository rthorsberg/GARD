"""Device REST router (T081)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.api.middleware.rbac import require
from gard.api.schemas.devices import DeviceFacts, DeviceList, DeviceWithEnvelope
from gard.core import device_controller
from gard.core.envelope import Reason, build_envelope, confidence_from_level
from gard.core.rbac import Permission, Principal
from gard.db.session import get_session
from gard.models import Device, DeviceObservation
from gard.models._enums import LifecycleState

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


def _to_facts(d: Device) -> DeviceFacts:
    return DeviceFacts(
        id=d.id,
        serial_number=d.serial_number,
        hostname=d.hostname,
        site=d.site,
        region=d.region,
        role=d.role,
        management_ip=d.management_ip,
        vendor_raw=d.vendor_raw,
        vendor_normalized=d.vendor_normalized,
        model_raw=d.model_raw,
        model_normalized=d.model_normalized,
        platform_family=d.platform_family,
        hardware_revision=d.hardware_revision,
        lifecycle_state=d.lifecycle_state.value,
        source_system=d.source_system,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def _envelope_for(d: Device, session: Session) -> DeviceWithEnvelope:
    facts = _to_facts(d)
    latest = session.scalar(
        select(DeviceObservation)
        .where(DeviceObservation.device_id == d.id)
        .order_by(DeviceObservation.created_at.desc())
        .limit(1)
    )

    if d.lifecycle_state == LifecycleState.classified:
        state = "classified"
        summary = (
            f"{d.vendor_normalized or d.vendor_raw} {d.model_normalized or d.model_raw} "
            f"@ {d.hostname}/{d.site}"
        )
        if latest is not None and latest.confidence_source:
            reasons = [
                Reason(
                    kind="rule_match",
                    ref=latest.confidence_source,
                    detail=f"latest observation classified by {latest.confidence_source}",
                )
            ]
        else:
            reasons = [
                Reason(
                    kind="evidence_ref",
                    ref=f"device:{d.id}",
                    detail="latest observation drove the canonical vendor/model.",
                )
            ]
        # Confidence comes from the latest observation, not a hard-coded
        # heuristic. This keeps the envelope honest when the catalog
        # claims `medium` rather than `high`.
        confidence = (
            confidence_from_level(latest.confidence.value)
            if latest is not None
            else confidence_from_level("medium")
        )
    else:
        state = "imported"
        summary = (
            f"Imported but unclassified: vendor_raw={d.vendor_raw!r}, model_raw={d.model_raw!r}"
        )
        reasons = [
            Reason(
                kind="missing_input",
                ref="normalization_engine",
                detail="no rule matched; observation flagged manual_review_required",
            )
        ]
        confidence = 0.0
    env = build_envelope(
        state=state,  # type: ignore[arg-type]
        summary=summary,
        facts=facts,
        reasons=reasons,
        confidence=confidence,
    )
    return DeviceWithEnvelope(facts=facts, envelope=env)


@router.get("", response_model=DeviceList)
def list_(
    _: Principal = Depends(require(Permission.LIST_DEVICES)),
    session: Session = Depends(get_session),
    vendor_normalized: str | None = Query(default=None),
    model_normalized: str | None = Query(default=None),
    site: str | None = Query(default=None),
    region: str | None = Query(default=None),
    lifecycle_state: LifecycleState | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> DeviceList:
    rows = device_controller.list_devices(
        session=session,
        vendor_normalized=vendor_normalized,
        model_normalized=model_normalized,
        site=site,
        region=region,
        lifecycle_state=lifecycle_state,
        limit=limit,
    )
    items = [_envelope_for(r, session) for r in rows]
    return DeviceList(items=items, total_returned=len(items))


@router.get("/{device_id}", response_model=DeviceWithEnvelope)
def get_(
    device_id: uuid.UUID,
    _: Principal = Depends(require(Permission.READ_DEVICE)),
    session: Session = Depends(get_session),
) -> DeviceWithEnvelope:
    d = device_controller.get_device(session, device_id)
    if d is None:
        raise HTTPException(status_code=404, detail="device not found")
    return _envelope_for(d, session)
