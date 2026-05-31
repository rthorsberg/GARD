"""F4 readiness & prerequisites router.

Surfaces:

- ``GET  /api/v1/readiness/summary``  — estate-wide readiness counters (US1).
- ``GET  /api/v1/readiness/devices``  — paginated list of devices with
  latest readiness envelope (US1 finishing surface).
- ``GET  /api/v1/devices/{id}/readiness`` — explainable per-device
  envelope (US2). 409 on stale F3 input (R-8).
- ``POST /api/v1/readiness/evaluate`` — bounded re-evaluation trigger
  (RUN_READINESS_EVAL only).

Every read emits a ``readiness.read`` audit row. The trigger emits a
single ``readiness.evaluation_triggered`` row plus one
``readiness.evaluated`` per device that changed verdict.
"""

from __future__ import annotations

import base64
import binascii
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.api.middleware.rbac import require
from gard.api.schemas.readiness import (
    BlockerCategoryCount,
    BlockerModel,
    BlockerPredicateKind,
    EvaluateRequest,
    EvaluateResponse,
    ReadinessDeviceList,
    ReadinessDeviceRow,
    ReadinessEnvelopeModel,
    ReadinessState,
    ReasonModel,
    RecommendedActionModel,
    SummaryResponse,
)
from gard.core import readiness_evaluation_controller as ctrl
from gard.core import scope_selector as sel
from gard.core.audit import emit as audit_emit
from gard.core.logging import get_correlation_id, get_logger
from gard.core.rbac import Permission, Principal
from gard.core.settings import get_settings
from gard.db.session import get_append_only_session, get_session
from gard.models import Device, ReadinessEvaluation
from gard.models._enums import ActorType

router = APIRouter(prefix="/api/v1", tags=["readiness"])
_log = get_logger(__name__)


# ---- page token helpers (mirrors F3) -------------------------------------


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


def _envelope_from_row(row: ReadinessEvaluation) -> ReadinessEnvelopeModel:
    """Project a stored readiness row into the public envelope shape."""
    return ReadinessEnvelopeModel(
        state=row.readiness_state,  # type: ignore[arg-type]
        summary=_synth_summary(row),
        target_version=row.target_version,
        observed_version=row.observed_version,
        upgrade_path_exists=row.upgrade_path_exists,
        applicable_rules_count=row.applicable_rules_count,
        blockers=[BlockerModel(**b) for b in (row.blockers or [])],
        recommended_actions=[RecommendedActionModel(**a) for a in (row.recommended_actions or [])],
        reasons=[ReasonModel(**r) for r in (row.reasons or [])],
        compliance_evaluation_ref=(
            str(row.compliance_evaluation_ref) if row.compliance_evaluation_ref else None
        ),
        confidence=float(row.confidence),
        evaluation_id=str(row.id),
        evaluated_at=row.evaluated_at,
        correlation_id=row.correlation_id,
    )


def _synth_summary(row: ReadinessEvaluation) -> str:
    if row.readiness_state == "ready_for_uplift":
        return "device is ready for uplift"
    if row.readiness_state == "not_applicable":
        return "readiness is not applicable for this device"
    blockers = row.blockers or []
    req = sum(1 for b in blockers if b.get("severity") == "required")
    rec = sum(1 for b in blockers if b.get("severity") == "recommended")
    return f"blocked: {req} required + {rec} recommended blocker(s)"


# ---- summary endpoint ----------------------------------------------------


@router.get(
    "/readiness/summary",
    response_model=SummaryResponse,
    summary="Estate-wide readiness summary",
)
def get_summary(
    region: str | None = Query(default=None),
    site: str | None = Query(default=None),
    platform_family: str | None = Query(default=None),
    vendor_normalized: str | None = Query(default=None),
    principal: Principal = Depends(require(Permission.READ_READINESS)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> SummaryResponse:
    summary = ctrl.fetch_summary(
        session,
        region=region,
        site=site,
        platform_family=platform_family,
        vendor_normalized=vendor_normalized,
    )
    correlation_id = get_correlation_id() or "anonymous-correlation"

    audit_emit(
        session=audit_session,
        action="readiness.read",
        object_type="ReadinessSummary",
        object_id=correlation_id,
        actor=principal.subject,
        actor_type=ActorType(principal.actor_type),
        before=None,
        after={
            "filters_applied": summary.filters_applied,
            "total_outside_target": summary.total_outside_target,
            "ready_for_uplift_count": summary.ready_for_uplift_count,
            "blocked_count": summary.blocked_count,
        },
        correlation_id=correlation_id,
    )

    return SummaryResponse(
        total_outside_target=summary.total_outside_target,
        ready_for_uplift_count=summary.ready_for_uplift_count,
        blocked_count=summary.blocked_count,
        not_applicable_count=summary.not_applicable_count,
        top_blocker_categories=[
            BlockerCategoryCount(predicate_kind=k, count=c)  # type: ignore[arg-type]
            for k, c in summary.top_blocker_categories
        ],
        filters_applied=summary.filters_applied,
        as_of=summary.as_of,
        correlation_id=correlation_id,
    )


# ---- list endpoint -------------------------------------------------------


@router.get(
    "/readiness/devices",
    response_model=ReadinessDeviceList,
    summary="Paginated devices + latest readiness envelope",
)
def list_devices(
    state: ReadinessState | None = Query(default=None),
    blocker_kind: BlockerPredicateKind | None = Query(default=None),
    region: str | None = Query(default=None),
    site: str | None = Query(default=None),
    platform_family: str | None = Query(default=None),
    vendor_normalized: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    page_token: str | None = Query(default=None),
    principal: Principal = Depends(require(Permission.READ_READINESS)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> ReadinessDeviceList:
    after_id = _decode_token(page_token)
    rows = ctrl.fetch_device_list(
        session,
        state=state,
        blocker_kind=blocker_kind,
        region=region,
        site=site,
        platform_family=platform_family,
        vendor_normalized=vendor_normalized,
        limit=limit,
        after_id=after_id,
    )
    items = [
        ReadinessDeviceRow(
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
        action="readiness.read",
        object_type="ReadinessDeviceList",
        object_id=get_correlation_id() or "anonymous-correlation",
        actor=principal.subject,
        actor_type=ActorType(principal.actor_type),
        before=None,
        after={
            "filters": {
                "state": state,
                "blocker_kind": blocker_kind,
                "region": region,
                "site": site,
                "platform_family": platform_family,
                "vendor_normalized": vendor_normalized,
            },
            "returned": len(items),
        },
        correlation_id=get_correlation_id(),
    )

    return ReadinessDeviceList(
        items=items,
        total_returned=len(items),
        next_page_token=next_token,
    )


# ---- per-device endpoint -------------------------------------------------


@router.get(
    "/devices/{device_id}/readiness",
    response_model=ReadinessEnvelopeModel,
    summary="Explainable readiness envelope for one device",
)
def get_device_readiness(
    device_id: uuid.UUID,
    principal: Principal = Depends(require(Permission.READ_READINESS)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> ReadinessEnvelopeModel:
    if session.get(Device, device_id) is None:
        raise HTTPException(status_code=404, detail="device not found")

    try:
        outcome = ctrl.evaluate(
            session=session,
            audit_session=audit_session,
            device_id=device_id,
            actor=principal.subject,
            actor_type=ActorType(principal.actor_type),
        )
    except ctrl.ReadinessInputStale as stale:
        # R-8: per-device endpoint refuses to derive a verdict from a
        # stale F3 row. Caller is told exactly which refresh to trigger.
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "READINESS_INPUT_STALE",
                    "message": (
                        f"compliance_evaluation for this device is older "
                        f"than {stale.stale_threshold_days} days; refresh "
                        f"via POST /api/v1/compliance/evaluate"
                    ),
                    "details": {
                        "latest_compliance_evaluated_at": (
                            stale.latest_compliance_evaluated_at.isoformat()
                        ),
                        "stale_threshold_days": stale.stale_threshold_days,
                    },
                    "correlation_id": get_correlation_id(),
                }
            },
        ) from stale

    audit_emit(
        session=audit_session,
        action="readiness.read",
        object_type="Device",
        object_id=str(device_id),
        actor=principal.subject,
        actor_type=ActorType(principal.actor_type),
        before=None,
        after={
            "readiness_state": outcome.envelope.state,
            "blocker_count": len(outcome.envelope.blockers),
            "evaluation_id": outcome.envelope.evaluation_id,
        },
        correlation_id=get_correlation_id(),
    )

    env = outcome.envelope
    return ReadinessEnvelopeModel(
        state=env.state,
        summary=env.summary,
        target_version=env.target_version,
        observed_version=env.observed_version,
        upgrade_path_exists=env.upgrade_path_exists,
        applicable_rules_count=env.applicable_rules_count,
        blockers=[BlockerModel(**b.model_dump(mode="json")) for b in env.blockers],
        recommended_actions=[
            RecommendedActionModel(**a.model_dump(mode="json")) for a in env.recommended_actions
        ],
        reasons=[
            ReasonModel(
                kind=r.kind,
                ref_type=r.ref_type,
                ref_id=r.ref_id,
                detail=r.detail,
            )
            for r in env.reasons
        ],
        compliance_evaluation_ref=env.compliance_evaluation_ref,
        confidence=env.confidence,
        evaluation_id=env.evaluation_id,
        evaluated_at=env.evaluated_at,
        correlation_id=env.correlation_id,
    )


# ---- trigger endpoint ----------------------------------------------------


@router.post(
    "/readiness/evaluate",
    response_model=EvaluateResponse,
    summary="Trigger bounded readiness re-evaluation",
)
def evaluate_batch(
    body: EvaluateRequest,
    principal: Principal = Depends(require(Permission.RUN_READINESS_EVAL)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> EvaluateResponse:
    settings = get_settings()
    cap = settings.compliance_evaluate_max_batch
    ids: list[uuid.UUID] = []

    if body.device_ids is not None:
        ids = list(body.device_ids)
    else:
        selector = body.scope_selector or {}
        try:
            sel.validate_keys(selector)
        except sel.UnknownSelectorKey as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
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
        not_applicable_count=outcome.not_applicable_count,
        correlation_id=outcome.correlation_id,
    )
