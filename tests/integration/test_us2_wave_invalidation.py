"""F5 — wave invalidation hook (T053-T056).

Drives ``uplift_wave_controller.invalidate_affected_waves`` directly.
The full catalogue-reload orchestration (F2 loader + git fixtures) is
exercised by F2's own reload tests; here we pin the invalidation
behaviour the reload hook delegates to.
"""

from __future__ import annotations

import datetime as dt

import pytest

from gard.core import uplift_wave_controller as wave_ctrl
from gard.models import (
    AuditEvent,
    Device,
    UpliftPlan,
    UpliftWave,
    UpliftWaveDevice,
)
from gard.models._enums import LifecycleState, WaveState
from tests.integration._uplift_helpers import make_device, make_live_target, make_readiness

pytestmark = pytest.mark.integration


def _make_submitted_wave(db_session, *, target_version: str = "9.0.0", state: str = "submitted"):
    """Build a wave in ``state`` with one approval_pending device member."""
    target = make_live_target(db_session, target_version=target_version)
    device = make_device(
        db_session, hostname="m0.oslo", lifecycle_state=LifecycleState.approval_pending
    )
    readiness = make_readiness(
        db_session, device=device, state="ready_for_uplift", target_version=target_version
    )
    plan = UpliftPlan(name=f"plan-{state}", created_by="user:drafter")
    db_session.add(plan)
    db_session.flush()

    now = dt.datetime.now(dt.UTC)
    start = now + dt.timedelta(hours=24)
    kwargs: dict = {
        "plan_id": plan.id,
        "name": "wave-inval",
        "target_version": target_version,
        "target_platform_family": "acme-os",
        "change_window_start": start,
        "change_window_end": start + dt.timedelta(hours=2),
        "state": state,
        "drafted_by": "user:drafter",
        "submitted_by": "user:drafter",
        "submitted_at": now,
        "correlation_id": "test-corr",
    }
    if state == "approved":
        kwargs["approved_by"] = "user:approver"
        kwargs["approved_at"] = now
        kwargs["approval_citation"] = "approved for the invalidation guard test here"
    wave = UpliftWave(**kwargs)
    db_session.add(wave)
    db_session.flush()
    db_session.add(
        UpliftWaveDevice(
            wave_id=wave.id,
            device_id=device.id,
            position=1,
            readiness_evaluation_ref=readiness.id,
            snapshot_target_version=target_version,
            snapshot_observed_version="8.1.0",
        )
    )
    db_session.commit()
    return wave, device, target


# ---- T053: F4 reverdict invalidates a submitted wave ---------------------


def test_submitted_wave_invalidated_on_affected_device(db_session) -> None:
    wave, device, _target = _make_submitted_wave(db_session)

    count = wave_ctrl.invalidate_affected_waves(
        db_session,
        db_session,
        affected_device_ids={device.id},
    )
    db_session.commit()

    assert count == 1
    db_session.rollback()
    refreshed = db_session.get(UpliftWave, wave.id)
    assert refreshed.state == WaveState.invalidated.value
    assert refreshed.invalidated_reason == "f4_reverdict"
    assert refreshed.invalidated_at is not None

    audit = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "uplift_wave.invalidated")
        .filter(AuditEvent.object_id == str(wave.id))
        .all()
    )
    assert len(audit) == 1


# ---- T054: target retirement -> reason target_retired --------------------


def test_target_retirement_reason(db_session) -> None:
    wave, device, target = _make_submitted_wave(db_session)
    # Retire the target the wave aims at.
    target.removed_at = dt.datetime.now(dt.UTC)
    db_session.commit()

    wave_ctrl.invalidate_affected_waves(db_session, db_session, affected_device_ids={device.id})
    db_session.commit()

    db_session.rollback()
    refreshed = db_session.get(UpliftWave, wave.id)
    assert refreshed.state == WaveState.invalidated.value
    assert refreshed.invalidated_reason == "target_retired"


# ---- T055: members return to ready_for_uplift ----------------------------


def test_invalidation_returns_members_to_ready(db_session) -> None:
    _wave, device, _target = _make_submitted_wave(db_session)

    wave_ctrl.invalidate_affected_waves(db_session, db_session, affected_device_ids={device.id})
    db_session.commit()

    db_session.rollback()
    fresh = db_session.get(Device, device.id)
    assert fresh.lifecycle_state == LifecycleState.ready_for_uplift


# ---- T056: only non-terminal waves are touched ---------------------------


def test_approved_wave_not_invalidated(db_session) -> None:
    wave, device, _target = _make_submitted_wave(db_session, state="approved")

    count = wave_ctrl.invalidate_affected_waves(
        db_session, db_session, affected_device_ids={device.id}
    )
    db_session.commit()

    assert count == 0
    db_session.rollback()
    refreshed = db_session.get(UpliftWave, wave.id)
    assert refreshed.state == WaveState.approved.value


def test_no_affected_devices_is_noop(db_session) -> None:
    _make_submitted_wave(db_session)
    count = wave_ctrl.invalidate_affected_waves(db_session, db_session, affected_device_ids=set())
    assert count == 0
