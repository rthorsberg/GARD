"""F5 US2 - submit / approve / reject / cancel (T041-T050)."""

from __future__ import annotations

import pytest

from gard.models import AuditEvent, Device
from gard.models._enums import LifecycleState, Role
from tests.integration._uplift_helpers import (
    auth_header,
    future_window,
    make_device,
    make_live_target,
    make_readiness,
    new_plan,
)

pytestmark = pytest.mark.integration


def _seed_ready(db_session, *, n: int = 1):
    make_live_target(db_session, target_version="9.0.0")
    devices = []
    for i in range(n):
        d = make_device(db_session, hostname=f"r{i}.oslo")
        make_readiness(db_session, device=d, state="ready_for_uplift")
        devices.append(d)
    return devices


def _draft_wave(client, headers, plan_id, *, name="wave-1") -> str:
    start, end = future_window()
    resp = client.post(
        f"/api/v1/uplift/plans/{plan_id}/waves",
        json={
            "name": name,
            "target_version": "9.0.0",
            "target_platform_family": "acme-os",
            "scope_selector": {"platform_family": "acme-os"},
            "change_window_start": start,
            "change_window_end": end,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _setup_submitted_wave(client, db_session, *, drafter_subject: str, drafter_role: Role):
    """Seed → plan → draft → submit. Returns (wave_id, device_ids, headers)."""
    drafter_headers = auth_header(db_session, roles=[drafter_role], subject=drafter_subject)
    devices = _seed_ready(db_session, n=2)
    db_session.commit()
    device_ids = [d.id for d in devices]

    plan_id = new_plan(client, drafter_headers)
    wave_id = _draft_wave(client, drafter_headers, plan_id)
    submitted = client.post(f"/api/v1/uplift/waves/{wave_id}/submit", headers=drafter_headers)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["state"] == "submitted"
    return wave_id, device_ids, drafter_headers


# ---- T041: happy-path approval -------------------------------------------


def test_happy_path_approval(client, db_session) -> None:
    wave_id, device_ids, _ = _setup_submitted_wave(
        client, db_session, drafter_subject="user:drafter", drafter_role=Role.lifecycle_manager
    )
    approver = auth_header(db_session, roles=[Role.change_approver], subject="user:approver")
    db_session.commit()

    # On submit devices are parked at approval_pending.
    db_session.rollback()
    for did in device_ids:
        assert db_session.get(Device, did).lifecycle_state == LifecycleState.approval_pending

    resp = client.post(
        f"/api/v1/uplift/waves/{wave_id}/approve",
        json={"citation": "change board CR-1234 approved on 2026-06-01"},
        headers=approver,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "approved"
    assert body["approved_by"] == "user:approver"
    assert "CR-1234" in body["approval_citation"]

    db_session.rollback()
    for did in device_ids:
        assert db_session.get(Device, did).lifecycle_state == LifecycleState.approved


# ---- T042: self-approval forbidden ---------------------------------------


def test_self_approval_forbidden(client, db_session) -> None:
    # Drafter holds both DRAFT + APPROVE (system_admin) so they reach the
    # SoD check rather than a missing-permission 403.
    wave_id, _ids, drafter_headers = _setup_submitted_wave(
        client, db_session, drafter_subject="user:admin", drafter_role=Role.system_admin
    )
    resp = client.post(
        f"/api/v1/uplift/waves/{wave_id}/approve",
        json={"citation": "trying to approve my own wave which is forbidden"},
        headers=drafter_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "SELF_APPROVAL_FORBIDDEN"


# ---- T043: self-rejection allowed ----------------------------------------


def test_self_rejection_allowed_with_audit_flag(client, db_session) -> None:
    wave_id, _ids, drafter_headers = _setup_submitted_wave(
        client, db_session, drafter_subject="user:admin", drafter_role=Role.system_admin
    )
    resp = client.post(
        f"/api/v1/uplift/waves/{wave_id}/reject",
        json={"citation": "drafter withdraws this wave after second thoughts"},
        headers=drafter_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "rejected"

    db_session.rollback()
    rejected = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "uplift_wave.rejected")
        .filter(AuditEvent.object_id == wave_id)
        .all()
    )
    assert len(rejected) == 1
    assert rejected[0].after["self_rejection"] is True


# ---- T044: re-approve approved wave ---------------------------------------


def test_reapprove_is_rejected(client, db_session) -> None:
    wave_id, _ids, _ = _setup_submitted_wave(
        client, db_session, drafter_subject="user:drafter", drafter_role=Role.lifecycle_manager
    )
    approver = auth_header(db_session, roles=[Role.change_approver], subject="user:approver")
    db_session.commit()

    ok = client.post(
        f"/api/v1/uplift/waves/{wave_id}/approve",
        json={"citation": "first approval is the valid one here"},
        headers=approver,
    )
    assert ok.status_code == 200

    again = client.post(
        f"/api/v1/uplift/waves/{wave_id}/approve",
        json={"citation": "second approval should be refused as terminal"},
        headers=approver,
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] in {"WAVE_STATE_MISMATCH", "WAVE_TRANSITION_FORBIDDEN"}


# ---- T045: concurrent approval (exactly one wins) ------------------------


def test_sequential_double_approval_one_wins(client, db_session) -> None:
    # TestClient is synchronous, so true concurrency is exercised by the
    # optimistic state guard: the first approve flips submitted→approved,
    # the second finds state != submitted and loses.
    wave_id, _ids, _ = _setup_submitted_wave(
        client, db_session, drafter_subject="user:drafter", drafter_role=Role.lifecycle_manager
    )
    a1 = auth_header(db_session, roles=[Role.change_approver], subject="user:approver1")
    a2 = auth_header(db_session, roles=[Role.change_approver], subject="user:approver2")
    db_session.commit()

    r1 = client.post(
        f"/api/v1/uplift/waves/{wave_id}/approve",
        json={"citation": "approver one wins the race for this wave"},
        headers=a1,
    )
    r2 = client.post(
        f"/api/v1/uplift/waves/{wave_id}/approve",
        json={"citation": "approver two loses the race for this wave"},
        headers=a2,
    )
    assert {r1.status_code, r2.status_code} == {200, 409}


# ---- T046: citation length bounds ----------------------------------------


@pytest.mark.parametrize("citation", ["too short", "x" * 2001])
def test_citation_length_bounds(client, db_session, citation) -> None:
    wave_id, _ids, _ = _setup_submitted_wave(
        client, db_session, drafter_subject="user:drafter", drafter_role=Role.lifecycle_manager
    )
    approver = auth_header(db_session, roles=[Role.change_approver], subject="user:approver")
    db_session.commit()

    resp = client.post(
        f"/api/v1/uplift/waves/{wave_id}/approve",
        json={"citation": citation},
        headers=approver,
    )
    assert resp.status_code == 422


# ---- T047: cancel authorisation ------------------------------------------


def test_cancel_by_non_drafter_without_approve_forbidden(client, db_session) -> None:
    wave_id, _ids, _ = _setup_submitted_wave(
        client, db_session, drafter_subject="user:drafter", drafter_role=Role.lifecycle_manager
    )
    # A *different* lifecycle_manager: holds DRAFT but not APPROVE, and is
    # not the drafter → must be refused.
    other = auth_header(db_session, roles=[Role.lifecycle_manager], subject="user:other-lc")
    db_session.commit()

    resp = client.post(
        f"/api/v1/uplift/waves/{wave_id}/cancel",
        json={"reason": "someone else trying to cancel"},
        headers=other,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_cancel_by_drafter_allowed(client, db_session) -> None:
    wave_id, device_ids, drafter_headers = _setup_submitted_wave(
        client, db_session, drafter_subject="user:drafter", drafter_role=Role.lifecycle_manager
    )
    resp = client.post(
        f"/api/v1/uplift/waves/{wave_id}/cancel",
        json={"reason": "drafter cancels the submitted wave"},
        headers=drafter_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "cancelled"

    # Submitted-wave cancel returns parked devices to ready_for_uplift.
    db_session.rollback()
    for did in device_ids:
        assert db_session.get(Device, did).lifecycle_state == LifecycleState.ready_for_uplift


# ---- T048: draft → approved forbidden ------------------------------------


def test_approve_draft_wave_forbidden(client, db_session) -> None:
    drafter = auth_header(db_session, roles=[Role.lifecycle_manager], subject="user:drafter")
    _seed_ready(db_session, n=1)
    db_session.commit()
    plan_id = new_plan(client, drafter)
    wave_id = _draft_wave(client, drafter, plan_id)  # NOT submitted

    approver = auth_header(db_session, roles=[Role.change_approver], subject="user:approver")
    db_session.commit()
    resp = client.post(
        f"/api/v1/uplift/waves/{wave_id}/approve",
        json={"citation": "approving a draft wave is not permitted at all"},
        headers=approver,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "WAVE_TRANSITION_FORBIDDEN"


# ---- T049: one audit row per transition ----------------------------------


def test_one_audit_row_per_transition(client, db_session) -> None:
    wave_id, _ids, _ = _setup_submitted_wave(
        client, db_session, drafter_subject="user:drafter", drafter_role=Role.lifecycle_manager
    )
    approver = auth_header(db_session, roles=[Role.change_approver], subject="user:approver")
    db_session.commit()
    client.post(
        f"/api/v1/uplift/waves/{wave_id}/approve",
        json={"citation": "approving for the audit-coverage assertion here"},
        headers=approver,
    )

    db_session.rollback()

    def _count(action: str) -> int:
        return (
            db_session.query(AuditEvent)
            .filter(AuditEvent.action == action)
            .filter(AuditEvent.object_id == wave_id)
            .count()
        )

    assert _count("uplift_wave.drafted") == 1
    assert _count("uplift_wave.submitted") == 1
    assert _count("uplift_wave.approved") == 1
