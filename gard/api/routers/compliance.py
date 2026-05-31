"""F3 compliance & drift evaluation router.

Surfaces:

- ``GET  /api/v1/compliance/summary``  — estate-wide drift counts (US1).
- ``GET  /api/v1/compliance/devices``  — paginated list of devices with
  latest envelope (US1 + US2 finishing surface).
- ``GET  /api/v1/devices/{id}/compliance`` — explainable per-device
  envelope (US2). Distinct from F2's ``/firmware-compliance`` —
  same device, richer envelope.
- ``POST /api/v1/compliance/evaluate`` — bounded re-evaluation trigger
  (RUN_COMPLIANCE_EVAL only).

Every read emits a ``compliance.read`` audit row. The trigger emits a
single ``compliance.evaluation_triggered`` row plus one
``compliance.evaluated`` per device that changed verdict.
"""

from __future__ import annotations

import base64
import binascii
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.api.middleware.rbac import require
from gard.api.schemas.compliance import (
    ComplianceDeviceList,
    ComplianceDeviceRow,
    ComplianceEnvelopeModel,
    ComplianceState,
    DriftCounts,
    DriftType,
    EvaluateRequest,
    EvaluateResponse,
    ReasonModel,
    RecommendedActionModel,
    SummaryResponse,
)
from gard.core import compliance_evaluation_controller as ctrl
from gard.core import scope_selector as sel
from gard.core.audit import emit as audit_emit
from gard.core.logging import get_correlation_id, get_logger
from gard.core.rbac import Permission, Principal
from gard.core.settings import get_settings
from gard.db.session import get_append_only_session, get_session
from gard.models import ComplianceEvaluation, Device
from gard.models._enums import ActorType

router = APIRouter(prefix="/api/v1", tags=["compliance"])
_log = get_logger(__name__)


# ---- page token helpers --------------------------------------------------
# Opaque base64 of the evaluation-row UUID. We deliberately keep the
# token short and unsigned — listing is read-only and clients can't
# break consistency by forging one (they'd just get a 422 / empty page).


def _encode_token(eval_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(eval_id.bytes).rstrip(b"=").decode("ascii")


def _decode_token(token: str | None) -> uuid.UUID | None:
    if token is None or token == "":
        return None
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        return uuid.UUID(bytes=raw)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="invalid page_token") from exc


# ---- envelope projection -------------------------------------------------


def _envelope_from_row(row: ComplianceEvaluation) -> ComplianceEnvelopeModel:
    """Project a stored evaluation row into the public envelope shape."""
    return ComplianceEnvelopeModel(
        state=row.compliance_state,  # type: ignore[arg-type]
        summary=_synth_summary(row),
        drift_type=row.primary_drift_type,  # type: ignore[arg-type]
        secondary_drift_types=list(row.secondary_drift_types or []),  # type: ignore[arg-type]
        target_ref=str(row.target_ref) if row.target_ref else None,
        target_version=row.target_version,
        observed_version=row.observed_version,
        observation_ref=str(row.observation_ref) if row.observation_ref else None,
        facts={},  # envelope payload is reasons + actions; facts populate on live calls
        reasons=[ReasonModel(**r) for r in (row.reasons or [])],
        recommended_actions=[RecommendedActionModel(**a) for a in (row.recommended_actions or [])],
        confidence=float(row.confidence),
        evaluation_id=str(row.id),
        evaluated_at=row.evaluated_at,
        correlation_id=row.correlation_id,
    )


def _synth_summary(row: ComplianceEvaluation) -> str:
    if row.compliance_state == "compliant":
        return f"compliant on {row.observed_version!r}"
    if row.primary_drift_type:
        return f"{row.compliance_state}: {row.primary_drift_type}"
    return row.compliance_state


# ---- summary endpoint ----------------------------------------------------


@router.get(
    "/compliance/summary",
    response_model=SummaryResponse,
    summary="Estate-wide drift summary",
)
def get_summary(
    region: str | None = Query(default=None),
    site: str | None = Query(default=None),
    platform_family: str | None = Query(default=None),
    vendor_normalized: str | None = Query(default=None),
    principal: Principal = Depends(require(Permission.READ_COMPLIANCE)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> SummaryResponse:
    counts = ctrl.fetch_summary(
        session,
        region=region,
        site=site,
        platform_family=platform_family,
        vendor_normalized=vendor_normalized,
    )

    audit_emit(
        session=audit_session,
        action="compliance.read",
        object_type="ComplianceSummary",
        object_id=get_correlation_id() or "anonymous-correlation",
        actor=principal.subject,
        actor_type=ActorType(principal.actor_type),
        before=None,
        after={
            "filters_applied": counts.filters_applied,
            "total_evaluated": counts.total_evaluated,
        },
        correlation_id=get_correlation_id(),
    )

    return SummaryResponse(
        total_evaluated=counts.total_evaluated,
        compliant_count=counts.compliant_count,
        unknown_count=counts.unknown_count,
        counts_by_drift_type=DriftCounts(**counts.counts_by_drift_type),
        filters_applied=counts.filters_applied,
        as_of=counts.as_of,
    )


# ---- list endpoint -------------------------------------------------------


@router.get(
    "/compliance/devices",
    response_model=ComplianceDeviceList,
    summary="Paginated devices + latest compliance envelope",
)
def list_devices(
    drift_type: DriftType | None = Query(default=None),
    state: ComplianceState | None = Query(default=None),
    region: str | None = Query(default=None),
    site: str | None = Query(default=None),
    platform_family: str | None = Query(default=None),
    vendor_normalized: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    page_token: str | None = Query(default=None),
    principal: Principal = Depends(require(Permission.READ_COMPLIANCE)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> ComplianceDeviceList:
    after_id = _decode_token(page_token)
    rows = ctrl.fetch_device_list(
        session,
        drift_type=drift_type,
        state=state,
        region=region,
        site=site,
        platform_family=platform_family,
        vendor_normalized=vendor_normalized,
        limit=limit,
        after_id=after_id,
    )
    items = [
        ComplianceDeviceRow(
            device_id=str(d.id),
            hostname=d.hostname,
            region=d.region,
            site=d.site,
            platform_family=d.platform_family,
            envelope=_envelope_from_row(e),
        )
        for d, e in rows
    ]
    next_token: str | None = None
    if len(rows) == limit:
        next_token = _encode_token(rows[-1][1].id)

    audit_emit(
        session=audit_session,
        action="compliance.read",
        object_type="ComplianceDeviceList",
        object_id=get_correlation_id() or "anonymous-correlation",
        actor=principal.subject,
        actor_type=ActorType(principal.actor_type),
        before=None,
        after={
            "filters": {
                "drift_type": drift_type,
                "state": state,
                "region": region,
                "site": site,
                "platform_family": platform_family,
                "vendor_normalized": vendor_normalized,
            },
            "returned": len(items),
        },
        correlation_id=get_correlation_id(),
    )

    return ComplianceDeviceList(
        items=items,
        total_returned=len(items),
        next_page_token=next_token,
    )


# ---- per-device endpoint -------------------------------------------------


@router.get(
    "/devices/{device_id}/compliance",
    response_model=ComplianceEnvelopeModel,
    summary="Explainable compliance envelope for one device",
)
def get_device_compliance(
    device_id: uuid.UUID,
    principal: Principal = Depends(require(Permission.READ_COMPLIANCE)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> ComplianceEnvelopeModel:
    if session.get(Device, device_id) is None:
        raise HTTPException(status_code=404, detail="device not found")

    outcome = ctrl.evaluate(
        session=session,
        audit_session=audit_session,
        device_id=device_id,
        actor=principal.subject,
        actor_type=ActorType(principal.actor_type),
    )

    audit_emit(
        session=audit_session,
        action="compliance.read",
        object_type="Device",
        object_id=str(device_id),
        actor=principal.subject,
        actor_type=ActorType(principal.actor_type),
        before=None,
        after={
            "compliance_state": outcome.envelope.state,
            "primary_drift_type": outcome.envelope.drift_type,
            "evaluation_id": outcome.envelope.evaluation_id,
        },
        correlation_id=get_correlation_id(),
    )

    env = outcome.envelope
    return ComplianceEnvelopeModel(
        state=env.state,
        summary=env.summary,
        drift_type=env.drift_type,
        secondary_drift_types=env.secondary_drift_types,
        target_ref=env.target_ref,
        target_version=env.target_version,
        observed_version=env.observed_version,
        observation_ref=env.observation_ref,
        facts=env.facts,
        reasons=[
            ReasonModel(
                kind=r.kind,
                ref_type=r.ref_type,
                ref_id=r.ref_id,
                detail=r.detail,
            )
            for r in env.reasons
        ],
        recommended_actions=[
            RecommendedActionModel(**a.model_dump(mode="json")) for a in env.recommended_actions
        ],
        confidence=env.confidence,
        evaluation_id=env.evaluation_id,
        evaluated_at=env.evaluated_at,
        correlation_id=env.correlation_id,
    )


# ---- trigger endpoint ----------------------------------------------------


@router.post(
    "/compliance/evaluate",
    response_model=EvaluateResponse,
    summary="Trigger bounded re-evaluation",
)
def evaluate_batch(
    body: EvaluateRequest,
    principal: Principal = Depends(require(Permission.RUN_COMPLIANCE_EVAL)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> EvaluateResponse:
    settings = get_settings()
    cap = settings.compliance_evaluate_max_batch
    ids: list[uuid.UUID] = []

    # Resolve the device set ----------------------------------------------
    if body.device_ids is not None:
        ids = list(body.device_ids)
    else:
        # EvaluateRequest validator guarantees scope_selector is set here.
        selector = body.scope_selector or {}
        try:
            sel.validate_keys(selector)
        except sel.UnknownSelectorKey as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        # We resolve by streaming Device facts through the selector.
        # 5k cap is enforced after resolution so the client gets 413
        # rather than 200-with-truncation.
        device_rows = session.scalars(select(Device)).all()
        for d in device_rows:
            facts = {
                "vendor_normalized": d.vendor_normalized,
                "platform_family": d.platform_family,
                "region": d.region,
                "site": d.site,
                "role": d.role,
                "hardware_revision": d.hardware_revision,
                "lifecycle_state": d.lifecycle_state.value,
            }
            verdict = sel.evaluate(selector, facts)
            if verdict.matched:
                ids.append(d.id)
            if len(ids) > cap:
                raise HTTPException(
                    status_code=413,
                    detail={
                        "error": {
                            "code": "EVALUATION_TOO_LARGE",
                            "message": (
                                f"scope_selector resolved to more than {cap} "
                                "devices; refine the selector"
                            ),
                        }
                    },
                )

    if len(ids) > cap:
        raise HTTPException(
            status_code=413,
            detail={
                "error": {
                    "code": "EVALUATION_TOO_LARGE",
                    "message": (f"device_ids count {len(ids)} exceeds cap {cap}"),
                }
            },
        )

    outcome = ctrl.evaluate_many(
        session=session,
        audit_session=audit_session,
        device_ids=ids,
        actor=principal.subject,
        actor_type=ActorType(principal.actor_type),
    )

    return EvaluateResponse(
        requested_count=outcome.requested_count,
        evaluated_count=outcome.evaluated_count,
        unchanged_count=outcome.unchanged_count,
        correlation_id=outcome.correlation_id,
    )
