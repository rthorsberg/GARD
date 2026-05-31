"""F5 uplift planning & waves router (T025).

Slice 5b surfaces the plan + wave lifecycle:

- ``POST /api/v1/uplift/plans``                       (DRAFT_UPLIFT_WAVE)
- ``GET  /api/v1/uplift/plans``                       (READ_UPLIFT)
- ``POST /api/v1/uplift/plans/{plan_id}/archive``     (DRAFT_UPLIFT_WAVE)
- ``POST /api/v1/uplift/plans/{plan_id}/waves``       (DRAFT_UPLIFT_WAVE, Idempotency-Key)
- ``GET  /api/v1/uplift/waves``                       (READ_UPLIFT)
- ``GET  /api/v1/uplift/waves/{wave_id}``             (READ_UPLIFT)
- ``POST /api/v1/uplift/waves/{wave_id}/submit``      (DRAFT_UPLIFT_WAVE)
- ``POST /api/v1/uplift/waves/{wave_id}/approve``     (APPROVE_UPLIFT_WAVE)
- ``POST /api/v1/uplift/waves/{wave_id}/reject``      (APPROVE_UPLIFT_WAVE)
- ``POST /api/v1/uplift/waves/{wave_id}/cancel``      (drafter OR APPROVE_UPLIFT_WAVE)

Exception endpoints land in slice 5c.

Every mutation delegates to the plan/wave controllers (which own the
audit writes); reads emit a ``uplift_*.read`` row at the edge.
"""

from __future__ import annotations

import base64
import binascii
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session

from gard.api.middleware.auth import get_principal
from gard.api.middleware.rbac import require
from gard.api.schemas.uplift import (
    ApproveRequest,
    CancelRequest,
    CreateExceptionRequest,
    CreatePlanRequest,
    CreateWaveRequest,
    ExceptionEnvelope,
    ExceptionList,
    PlanEnvelope,
    PlanList,
    RejectRequest,
    SkippedDevice,
    WaveDeviceRow,
    WaveEnvelope,
    WaveList,
)
from gard.core import uplift_exception_controller as exc_ctrl
from gard.core import uplift_plan_controller as plan_ctrl
from gard.core import uplift_state_machine as sm
from gard.core import uplift_wave_controller as wave_ctrl
from gard.core.audit import emit as audit_emit
from gard.core.logging import get_correlation_id, get_logger
from gard.core.rbac import Permission, Principal
from gard.db.session import get_append_only_session, get_session
from gard.models import Device, UpliftException, UpliftPlan, UpliftWave, UpliftWaveDevice
from gard.models._enums import ActorType

router = APIRouter(prefix="/api/v1", tags=["uplift"])
_log = get_logger(__name__)


# ---- page-token helpers (mirror F3/F4) -----------------------------------


def _encode_token(row_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(row_id.bytes).rstrip(b"=").decode("ascii")


def _decode_token(token: str | None) -> uuid.UUID | None:
    if not token:
        return None
    try:
        padded = token + "=" * (-len(token) % 4)
        return uuid.UUID(bytes=base64.urlsafe_b64decode(padded.encode("ascii")))
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="invalid page_token") from exc


def _err(
    status_code: int, code: str, message: str, details: dict[str, object] | None = None
) -> HTTPException:
    body: dict[str, object] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    body["correlation_id"] = get_correlation_id()
    return HTTPException(status_code=status_code, detail={"error": body})


# ---- projections ---------------------------------------------------------


def _plan_envelope(plan: UpliftPlan, wave_count: int) -> PlanEnvelope:
    return PlanEnvelope(
        id=str(plan.id),
        name=plan.name,
        description=plan.description,
        created_by=plan.created_by,
        created_at=plan.created_at,
        archived_at=plan.archived_at,
        archived_by=plan.archived_by,
        wave_count=wave_count,
        correlation_id=get_correlation_id() or "unknown",
    )


def _wave_envelope(
    wave: UpliftWave,
    members: list[tuple[Device, UpliftWaveDevice]],
    skipped: list[wave_ctrl.SkippedDevice] | None = None,
) -> WaveEnvelope:
    device_rows = [
        WaveDeviceRow(
            device_id=str(device.id),
            hostname=device.hostname,
            position=wd.position,
            snapshot_target_version=wd.snapshot_target_version,
            snapshot_observed_version=wd.snapshot_observed_version,
            readiness_evaluation_ref=(
                str(wd.readiness_evaluation_ref) if wd.readiness_evaluation_ref else None
            ),
        )
        for device, wd in members
    ]
    skipped_rows = [
        SkippedDevice(
            device_id=str(s.device_id),
            reason=s.reason,
            current_readiness_state=s.current_readiness_state,
        )
        for s in (skipped or [])
    ]
    return WaveEnvelope(
        id=str(wave.id),
        plan_id=str(wave.plan_id),
        name=wave.name,
        state=wave.state,  # type: ignore[arg-type]
        target_version=wave.target_version,
        target_platform_family=wave.target_platform_family,
        change_window_start=wave.change_window_start,
        change_window_end=wave.change_window_end,
        drafted_by=wave.drafted_by,
        drafted_at=wave.drafted_at,
        submitted_by=wave.submitted_by,
        submitted_at=wave.submitted_at,
        approved_by=wave.approved_by,
        approved_at=wave.approved_at,
        approval_citation=wave.approval_citation,
        rejected_by=wave.rejected_by,
        rejected_at=wave.rejected_at,
        rejection_citation=wave.rejection_citation,
        cancelled_by=wave.cancelled_by,
        cancelled_at=wave.cancelled_at,
        cancellation_reason=wave.cancellation_reason,
        invalidated_at=wave.invalidated_at,
        invalidated_reason=wave.invalidated_reason,
        device_count=len(device_rows),
        devices=device_rows,
        skipped=skipped_rows,
        correlation_id=wave.correlation_id or get_correlation_id() or "unknown",
    )


# ---- plan endpoints ------------------------------------------------------


@router.post("/uplift/plans", response_model=PlanEnvelope, status_code=201)
def create_plan(
    body: CreatePlanRequest,
    principal: Principal = Depends(require(Permission.DRAFT_UPLIFT_WAVE)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> PlanEnvelope:
    plan = plan_ctrl.create_plan(
        session=session,
        audit_session=audit_session,
        name=body.name,
        description=body.description,
        actor=principal.subject,
        actor_type=ActorType(principal.actor_type),
    )
    return _plan_envelope(plan, 0)


@router.get("/uplift/plans", response_model=PlanList)
def list_plans(
    include_archived: bool = Query(default=False),
    region: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    page_token: str | None = Query(default=None),
    principal: Principal = Depends(require(Permission.READ_UPLIFT)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> PlanList:
    after_id = _decode_token(page_token)
    page = plan_ctrl.list_plans(
        session,
        include_archived=include_archived,
        limit=limit,
        after_id=after_id,
    )
    items = [_plan_envelope(p, c) for p, c in page.plans]
    next_token = _encode_token(page.next_after_id) if page.next_after_id else None

    audit_emit(
        session=audit_session,
        action="uplift_plan.read",
        object_type="UpliftPlanList",
        object_id=get_correlation_id() or "anonymous-correlation",
        actor=principal.subject,
        actor_type=ActorType(principal.actor_type),
        after={"returned": len(items), "include_archived": include_archived},
        correlation_id=get_correlation_id(),
    )
    return PlanList(items=items, total_returned=len(items), next_page_token=next_token)


@router.post("/uplift/plans/{plan_id}/archive", response_model=PlanEnvelope)
def archive_plan(
    plan_id: uuid.UUID,
    principal: Principal = Depends(require(Permission.DRAFT_UPLIFT_WAVE)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> PlanEnvelope:
    try:
        plan = plan_ctrl.archive_plan(
            session=session,
            audit_session=audit_session,
            plan_id=plan_id,
            actor=principal.subject,
            actor_type=ActorType(principal.actor_type),
        )
    except plan_ctrl.PlanNotFound as exc:
        raise _err(404, "PLAN_NOT_FOUND", f"plan not found: {plan_id}") from exc
    return _plan_envelope(plan, plan_ctrl.count_waves(session, plan.id))


# ---- wave drafting -------------------------------------------------------


@router.post("/uplift/plans/{plan_id}/waves", response_model=WaveEnvelope)
def create_wave(
    plan_id: uuid.UUID,
    body: CreateWaveRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(require(Permission.DRAFT_UPLIFT_WAVE)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> WaveEnvelope:
    plan = plan_ctrl.get_plan(session, plan_id)
    if plan is None:
        raise _err(404, "PLAN_NOT_FOUND", f"plan not found: {plan_id}")
    if plan.archived_at is not None:
        raise _err(422, "PLAN_ARCHIVED", "cannot draft a wave inside an archived plan")

    try:
        outcome = wave_ctrl.draft_wave(
            session=session,
            audit_session=audit_session,
            plan_id=plan_id,
            name=body.name,
            target_version=body.target_version,
            target_platform_family=body.target_platform_family,
            scope_selector=body.scope_selector,
            mode=body.mode,
            change_window_start=body.change_window_start,
            change_window_end=body.change_window_end,
            idempotency_key=idempotency_key,
            actor=principal.subject,
            actor_type=ActorType(principal.actor_type),
        )
    except wave_ctrl.InvalidChangeWindow as exc:
        raise _err(422, "INVALID_CHANGE_WINDOW", exc.reason) from exc
    except wave_ctrl.TargetVersionNotLive as exc:
        raise _err(
            422,
            "TARGET_VERSION_NOT_LIVE",
            str(exc),
            {"platform_family": exc.platform_family, "target_version": exc.target_version},
        ) from exc
    except wave_ctrl.IneligibleDevicesInScope as exc:
        raise _err(
            422,
            "INELIGIBLE_DEVICES_IN_SCOPE",
            str(exc),
            {
                "skipped": [
                    {
                        "device_id": str(s.device_id),
                        "current_readiness_state": s.current_readiness_state,
                    }
                    for s in exc.skipped
                ]
            },
        ) from exc
    except wave_ctrl.EmptyWave as exc:
        raise _err(422, "EMPTY_WAVE", str(exc)) from exc
    except wave_ctrl.WaveTooLarge as exc:
        raise _err(413, "WAVE_TOO_LARGE", str(exc), {"count": exc.count, "cap": exc.cap}) from exc

    response.status_code = 200 if outcome.replayed else 201
    return _wave_envelope(outcome.wave, outcome.members, outcome.skipped)


# ---- wave reads ----------------------------------------------------------


@router.get("/uplift/waves", response_model=WaveList)
def list_waves(
    plan_id: uuid.UUID | None = Query(default=None),
    state: str | None = Query(default=None),
    target_version: str | None = Query(default=None),
    region: str | None = Query(default=None),
    site: str | None = Query(default=None),
    platform_family: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    page_token: str | None = Query(default=None),
    principal: Principal = Depends(require(Permission.READ_UPLIFT)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> WaveList:
    after_id = _decode_token(page_token)
    waves, next_after = wave_ctrl.list_waves(
        session,
        plan_id=plan_id,
        state=state,
        target_version=target_version,
        region=region,
        site=site,
        platform_family=platform_family,
        limit=limit,
        after_id=after_id,
    )
    items = [_wave_envelope(w, wave_ctrl.load_wave_members(session, w.id)) for w in waves]
    next_token = _encode_token(next_after) if next_after else None

    audit_emit(
        session=audit_session,
        action="uplift_wave.read",
        object_type="UpliftWaveList",
        object_id=get_correlation_id() or "anonymous-correlation",
        actor=principal.subject,
        actor_type=ActorType(principal.actor_type),
        after={
            "returned": len(items),
            "state": state,
            "plan_id": str(plan_id) if plan_id else None,
        },
        correlation_id=get_correlation_id(),
    )
    return WaveList(items=items, total_returned=len(items), next_page_token=next_token)


@router.get("/uplift/waves/{wave_id}", response_model=WaveEnvelope)
def get_wave(
    wave_id: uuid.UUID,
    principal: Principal = Depends(require(Permission.READ_UPLIFT)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> WaveEnvelope:
    wave = wave_ctrl.get_wave(session, wave_id)
    if wave is None:
        raise _err(404, "WAVE_NOT_FOUND", f"wave not found: {wave_id}")
    members = wave_ctrl.load_wave_members(session, wave_id)
    audit_emit(
        session=audit_session,
        action="uplift_wave.read",
        object_type="UpliftWave",
        object_id=str(wave_id),
        actor=principal.subject,
        actor_type=ActorType(principal.actor_type),
        after={"state": wave.state, "device_count": len(members)},
        correlation_id=get_correlation_id(),
    )
    return _wave_envelope(wave, members)


# ---- wave transitions ----------------------------------------------------


def _map_transition_error(exc: Exception) -> HTTPException:
    """Translate state-machine + optimistic-guard errors to HTTP."""
    if isinstance(exc, sm.SelfApprovalForbidden):
        return _err(403, "SELF_APPROVAL_FORBIDDEN", str(exc))
    if isinstance(exc, sm.TransitionForbidden | sm.ActorKindForbidden):
        return _err(409, "WAVE_TRANSITION_FORBIDDEN", str(exc))
    if isinstance(exc, wave_ctrl.WaveStateMismatch):
        return _err(
            409,
            "WAVE_STATE_MISMATCH",
            str(exc),
            {"expected": exc.expected, "actual": exc.actual},
        )
    raise exc  # pragma: no cover - unexpected


@router.post("/uplift/waves/{wave_id}/submit", response_model=WaveEnvelope)
def submit_wave(
    wave_id: uuid.UUID,
    principal: Principal = Depends(require(Permission.DRAFT_UPLIFT_WAVE)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> WaveEnvelope:
    try:
        wave = wave_ctrl.submit(
            session=session,
            audit_session=audit_session,
            wave_id=wave_id,
            actor=principal.subject,
            actor_type=ActorType(principal.actor_type),
        )
    except wave_ctrl.WaveNotFound as exc:
        raise _err(404, "WAVE_NOT_FOUND", str(exc)) from exc
    except (sm.StateMachineError, wave_ctrl.WaveStateMismatch) as exc:
        raise _map_transition_error(exc) from exc
    return _wave_envelope(wave, wave_ctrl.load_wave_members(session, wave_id))


@router.post("/uplift/waves/{wave_id}/approve", response_model=WaveEnvelope)
def approve_wave(
    wave_id: uuid.UUID,
    body: ApproveRequest,
    principal: Principal = Depends(require(Permission.APPROVE_UPLIFT_WAVE)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> WaveEnvelope:
    try:
        wave = wave_ctrl.approve(
            session=session,
            audit_session=audit_session,
            wave_id=wave_id,
            citation=body.citation,
            actor=principal.subject,
            actor_type=ActorType(principal.actor_type),
        )
    except wave_ctrl.WaveNotFound as exc:
        raise _err(404, "WAVE_NOT_FOUND", str(exc)) from exc
    except (sm.StateMachineError, wave_ctrl.WaveStateMismatch) as exc:
        raise _map_transition_error(exc) from exc
    return _wave_envelope(wave, wave_ctrl.load_wave_members(session, wave_id))


@router.post("/uplift/waves/{wave_id}/reject", response_model=WaveEnvelope)
def reject_wave(
    wave_id: uuid.UUID,
    body: RejectRequest,
    principal: Principal = Depends(require(Permission.APPROVE_UPLIFT_WAVE)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> WaveEnvelope:
    try:
        wave = wave_ctrl.reject(
            session=session,
            audit_session=audit_session,
            wave_id=wave_id,
            citation=body.citation,
            actor=principal.subject,
            actor_type=ActorType(principal.actor_type),
        )
    except wave_ctrl.WaveNotFound as exc:
        raise _err(404, "WAVE_NOT_FOUND", str(exc)) from exc
    except (sm.StateMachineError, wave_ctrl.WaveStateMismatch) as exc:
        raise _map_transition_error(exc) from exc
    return _wave_envelope(wave, wave_ctrl.load_wave_members(session, wave_id))


@router.post("/uplift/waves/{wave_id}/cancel", response_model=WaveEnvelope)
def cancel_wave(
    wave_id: uuid.UUID,
    body: CancelRequest,
    # Cancel is allowed by the drafter OR any APPROVE_UPLIFT_WAVE holder
    # (ADR-0016 / T039). Base gate is READ_UPLIFT; the drafter-or-approver
    # rule is enforced in-body so a non-drafter without approve rights 403s.
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> WaveEnvelope:
    if not principal.has(Permission.READ_UPLIFT):
        raise _err(403, "FORBIDDEN", "missing permission: uplift.read")
    wave = wave_ctrl.get_wave(session, wave_id)
    if wave is None:
        raise _err(404, "WAVE_NOT_FOUND", f"wave not found: {wave_id}")
    is_drafter = principal.subject == wave.drafted_by
    if not is_drafter and not principal.has(Permission.APPROVE_UPLIFT_WAVE):
        raise _err(
            403,
            "FORBIDDEN",
            "cancellation requires being the drafter or holding uplift.wave.approve",
        )
    try:
        wave = wave_ctrl.cancel(
            session=session,
            audit_session=audit_session,
            wave_id=wave_id,
            reason=body.reason,
            actor=principal.subject,
            actor_type=ActorType(principal.actor_type),
        )
    except (sm.StateMachineError, wave_ctrl.WaveStateMismatch) as exc:
        raise _map_transition_error(exc) from exc
    return _wave_envelope(wave, wave_ctrl.load_wave_members(session, wave_id))


# ---- exception endpoints (slice 5c) --------------------------------------


def _exception_envelope(exc: UpliftException) -> ExceptionEnvelope:
    return ExceptionEnvelope(
        id=str(exc.id),
        device_id=str(exc.device_id),
        blocker_rule_id=str(exc.blocker_rule_id) if exc.blocker_rule_id else None,
        synthetic_kind=exc.synthetic_kind,
        justification=exc.justification,
        state=exc.state,  # type: ignore[arg-type]
        filed_by=exc.filed_by,
        filed_at=exc.filed_at,
        approved_by=exc.approved_by,
        approved_at=exc.approved_at,
        rejected_by=exc.rejected_by,
        rejected_at=exc.rejected_at,
        withdrawn_by=exc.withdrawn_by,
        withdrawn_at=exc.withdrawn_at,
        expires_at=exc.expires_at,
        expired_at=exc.expired_at,
        correlation_id=exc.correlation_id or get_correlation_id() or "unknown",
    )


def _map_exception_transition_error(exc: Exception) -> HTTPException:
    if isinstance(exc, sm.SelfApprovalForbidden):
        return _err(403, "SELF_APPROVAL_FORBIDDEN", str(exc))
    if isinstance(exc, sm.TransitionForbidden | sm.ActorKindForbidden):
        return _err(409, "EXCEPTION_TRANSITION_FORBIDDEN", str(exc))
    if isinstance(exc, exc_ctrl.ExceptionStateMismatch):
        return _err(
            409,
            "EXCEPTION_STATE_MISMATCH",
            str(exc),
            {"expected": exc.expected, "actual": exc.actual},
        )
    raise exc  # pragma: no cover


@router.get("/uplift/exceptions", response_model=ExceptionList)
def list_exceptions(
    device_id: uuid.UUID | None = None,
    state: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    page_token: str | None = None,
    principal: Principal = Depends(require(Permission.READ_UPLIFT)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> ExceptionList:
    page = exc_ctrl.list_exceptions(
        session,
        device_id=device_id,
        state=state,
        limit=limit,
        after_id=_decode_token(page_token),
    )
    audit_emit(
        session=audit_session,
        action="uplift_exception.read",
        object_type="UpliftException",
        object_id="list",
        actor=principal.subject,
        actor_type=ActorType(principal.actor_type),
        before=None,
        after={"count": len(page.exceptions), "device_id": str(device_id) if device_id else None},
        correlation_id=get_correlation_id(),
    )
    items = [_exception_envelope(e) for e in page.exceptions]
    return ExceptionList(
        items=items,
        total_returned=len(items),
        next_page_token=_encode_token(page.next_after_id) if page.next_after_id else None,
    )


@router.post("/uplift/exceptions", response_model=ExceptionEnvelope, status_code=201)
def create_exception(
    body: CreateExceptionRequest,
    principal: Principal = Depends(require(Permission.MANAGE_EXCEPTION)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> ExceptionEnvelope:
    try:
        row = exc_ctrl.file_exception(
            session=session,
            audit_session=audit_session,
            device_id=body.device_id,
            blocker_rule_id=body.blocker_rule_id,
            synthetic_kind=body.synthetic_kind,
            justification=body.justification,
            expires_at=body.expires_at,
            actor=principal.subject,
            actor_type=ActorType(principal.actor_type),
        )
    except exc_ctrl.DeviceNotBlocked as err:
        raise _err(422, "DEVICE_NOT_BLOCKED", str(err)) from err
    except exc_ctrl.BlockerNotInLatestVerdict as err:
        raise _err(422, "BLOCKER_NOT_IN_LATEST_VERDICT", str(err)) from err
    except exc_ctrl.InvalidExceptionExpiry as err:
        raise _err(422, "INVALID_EXCEPTION_EXPIRY", str(err)) from err
    except exc_ctrl.ExceptionAlreadyActive as err:
        raise _err(
            409,
            "EXCEPTION_ALREADY_ACTIVE",
            str(err),
            {"existing_exception_id": str(err.existing_id)},
        ) from err
    return _exception_envelope(row)


@router.post("/uplift/exceptions/{exception_id}/approve", response_model=ExceptionEnvelope)
def approve_exception(
    exception_id: uuid.UUID,
    principal: Principal = Depends(require(Permission.APPROVE_EXCEPTION)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> ExceptionEnvelope:
    try:
        row = exc_ctrl.approve_exception(
            session=session,
            audit_session=audit_session,
            exception_id=exception_id,
            actor=principal.subject,
            actor_type=ActorType(principal.actor_type),
        )
    except exc_ctrl.ExceptionNotFound as err:
        raise _err(404, "EXCEPTION_NOT_FOUND", str(err)) from err
    except exc_ctrl.DeviceNotBlocked as err:
        raise _err(422, "DEVICE_NOT_BLOCKED", str(err)) from err
    except (sm.StateMachineError, exc_ctrl.ExceptionStateMismatch) as err:
        raise _map_exception_transition_error(err) from err
    return _exception_envelope(row)


@router.post("/uplift/exceptions/{exception_id}/reject", response_model=ExceptionEnvelope)
def reject_exception(
    exception_id: uuid.UUID,
    principal: Principal = Depends(require(Permission.APPROVE_EXCEPTION)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> ExceptionEnvelope:
    try:
        row = exc_ctrl.reject_exception(
            session=session,
            audit_session=audit_session,
            exception_id=exception_id,
            actor=principal.subject,
            actor_type=ActorType(principal.actor_type),
        )
    except exc_ctrl.ExceptionNotFound as err:
        raise _err(404, "EXCEPTION_NOT_FOUND", str(err)) from err
    except (sm.StateMachineError, exc_ctrl.ExceptionStateMismatch) as err:
        raise _map_exception_transition_error(err) from err
    return _exception_envelope(row)


@router.post("/uplift/exceptions/{exception_id}/withdraw", response_model=ExceptionEnvelope)
def withdraw_exception(
    exception_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> ExceptionEnvelope:
    exc_row = exc_ctrl.get_exception(session, exception_id)
    if exc_row is None:
        raise _err(404, "EXCEPTION_NOT_FOUND", f"exception not found: {exception_id}")
    if principal.subject != exc_row.filed_by and not principal.has(Permission.MANAGE_EXCEPTION):
        raise _err(
            403,
            "FORBIDDEN",
            "withdrawal requires being the filer or holding uplift.exception.manage",
        )
    try:
        row = exc_ctrl.withdraw_exception(
            session=session,
            audit_session=audit_session,
            exception_id=exception_id,
            actor=principal.subject,
            actor_type=ActorType(principal.actor_type),
        )
    except (sm.StateMachineError, exc_ctrl.ExceptionStateMismatch) as err:
        raise _map_exception_transition_error(err) from err
    return _exception_envelope(row)
