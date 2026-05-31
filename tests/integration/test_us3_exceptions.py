"""F5 US3 — exceptions lifecycle (T065-T072)."""

from __future__ import annotations

import datetime as dt
import time
import uuid

import pytest

from gard.models import AuditEvent, Device
from gard.models._enums import LifecycleState, Role
from tests.integration._uplift_helpers import (
    auth_header,
    file_exception_payload,
    future_expiry,
    make_blocked_device,
)

pytestmark = pytest.mark.integration

JUSTIFICATION = "Accepted known risk for end-of-life hardware in this site."


def test_happy_path_exception_approval_and_f4_carveout(client, db_session) -> None:
    device, rule_id, _ = make_blocked_device(db_session)
    filer = auth_header(db_session, roles=[Role.lifecycle_manager], subject="user:filer")
    approver = auth_header(db_session, roles=[Role.change_approver], subject="user:approver")
    db_session.commit()

    filed = client.post(
        "/api/v1/uplift/exceptions",
        json=file_exception_payload(device_id=device.id, blocker_rule_id=rule_id),
        headers=filer,
    )
    assert filed.status_code == 201, filed.text
    exc_id = filed.json()["id"]
    assert filed.json()["state"] == "pending_review"
    assert db_session.get(Device, device.id).lifecycle_state == LifecycleState.blocked

    approved = client.post(
        f"/api/v1/uplift/exceptions/{exc_id}/approve",
        headers=approver,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["state"] == "approved"
    db_session.expire_all()
    assert db_session.get(Device, device.id).lifecycle_state == LifecycleState.exception_approved

    readiness = client.get(f"/api/v1/devices/{device.id}/readiness", headers=approver)
    assert readiness.status_code == 200, readiness.text
    body = readiness.json()
    assert body["state"] == "not_applicable"
    assert body["reasons"][0]["kind"] == "active_exception"
    assert body["reasons"][0]["ref_id"] == exc_id


def test_exception_expiry_returns_device_to_blocked(client, db_session) -> None:
    device, rule_id, _ = make_blocked_device(db_session, hostname="expire.oslo")
    filer = auth_header(db_session, roles=[Role.lifecycle_manager], subject="user:filer")
    approver = auth_header(db_session, roles=[Role.change_approver], subject="user:approver")
    db_session.commit()

    expires = (dt.datetime.now(dt.UTC) + dt.timedelta(seconds=1)).isoformat()
    filed = client.post(
        "/api/v1/uplift/exceptions",
        json=file_exception_payload(
            device_id=device.id,
            blocker_rule_id=rule_id,
            expires_at=expires,
        ),
        headers=filer,
    )
    assert filed.status_code == 201, filed.text
    exc_id = filed.json()["id"]
    assert (
        client.post(f"/api/v1/uplift/exceptions/{exc_id}/approve", headers=approver).status_code
        == 200
    )

    time.sleep(1.2)
    readiness = client.get(f"/api/v1/devices/{device.id}/readiness", headers=approver)
    assert readiness.status_code == 200, readiness.text
    assert readiness.json()["state"] == "blocked"
    db_session.expire_all()
    assert db_session.get(Device, device.id).lifecycle_state == LifecycleState.blocked

    expired_audit = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "uplift_exception.expired")
        .filter(AuditEvent.object_id == exc_id)
        .one_or_none()
    )
    assert expired_audit is not None


def test_exception_already_active_conflict(client, db_session) -> None:
    device, rule_id, _ = make_blocked_device(db_session, hostname="dup.oslo")
    filer = auth_header(db_session, roles=[Role.lifecycle_manager], subject="user:filer")
    db_session.commit()

    first = client.post(
        "/api/v1/uplift/exceptions",
        json=file_exception_payload(device_id=device.id, blocker_rule_id=rule_id),
        headers=filer,
    )
    assert first.status_code == 201

    second = client.post(
        "/api/v1/uplift/exceptions",
        json=file_exception_payload(device_id=device.id, blocker_rule_id=rule_id),
        headers=filer,
    )
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "EXCEPTION_ALREADY_ACTIVE"
    assert second.json()["error"]["details"]["existing_exception_id"] == first.json()["id"]


@pytest.mark.parametrize(
    "justification",
    [
        "too short",
        "x" * 2001,
    ],
)
def test_justification_length_bounds(client, db_session, justification: str) -> None:
    device, rule_id, _ = make_blocked_device(
        db_session, hostname=f"just-{uuid.uuid4().hex[:6]}.oslo"
    )
    headers = auth_header(db_session, roles=[Role.lifecycle_manager], subject="user:filer")
    db_session.commit()

    resp = client.post(
        "/api/v1/uplift/exceptions",
        json={
            "device_id": str(device.id),
            "blocker_rule_id": str(rule_id),
            "justification": justification,
            "expires_at": future_expiry(),
        },
        headers=headers,
    )
    assert resp.status_code == 422


def test_self_approval_forbidden(client, db_session) -> None:
    device, rule_id, _ = make_blocked_device(db_session, hostname="sod.oslo")
    # Filer must hold APPROVE_EXCEPTION so RBAC passes and SoD is enforced in-controller.
    filer = auth_header(
        db_session,
        roles=[Role.lifecycle_manager, Role.change_approver],
        subject="user:same",
    )
    db_session.commit()

    exc_id = client.post(
        "/api/v1/uplift/exceptions",
        json=file_exception_payload(device_id=device.id, blocker_rule_id=rule_id),
        headers=filer,
    ).json()["id"]

    resp = client.post(f"/api/v1/uplift/exceptions/{exc_id}/approve", headers=filer)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "SELF_APPROVAL_FORBIDDEN"


def test_withdraw_by_filer_from_pending(client, db_session) -> None:
    device, rule_id, _ = make_blocked_device(db_session, hostname="withdraw.oslo")
    filer = auth_header(db_session, roles=[Role.lifecycle_manager], subject="user:filer")
    db_session.commit()

    exc_id = client.post(
        "/api/v1/uplift/exceptions",
        json=file_exception_payload(device_id=device.id, blocker_rule_id=rule_id),
        headers=filer,
    ).json()["id"]

    resp = client.post(f"/api/v1/uplift/exceptions/{exc_id}/withdraw", headers=filer)
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "withdrawn"


def test_synthetic_blocker_exception(client, db_session) -> None:
    device, _, syn = make_blocked_device(
        db_session,
        hostname="synthetic.oslo",
        synthetic_kind="missing_upgrade_path",
    )
    filer = auth_header(db_session, roles=[Role.lifecycle_manager], subject="user:filer")
    db_session.commit()

    resp = client.post(
        "/api/v1/uplift/exceptions",
        json=file_exception_payload(device_id=device.id, synthetic_kind=syn),
        headers=filer,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["synthetic_kind"] == syn
    assert resp.json()["blocker_rule_id"] is None


def test_f4_audit_chain_after_exception_carveout(client, db_session) -> None:
    device, rule_id, _ = make_blocked_device(db_session, hostname="audit.oslo")
    filer = auth_header(db_session, roles=[Role.lifecycle_manager], subject="user:filer")
    approver = auth_header(db_session, roles=[Role.change_approver], subject="user:approver")
    db_session.commit()

    before = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "readiness.evaluated")
        .filter(AuditEvent.object_id == str(device.id))
        .count()
    )

    exc_id = client.post(
        "/api/v1/uplift/exceptions",
        json=file_exception_payload(device_id=device.id, blocker_rule_id=rule_id),
        headers=filer,
    ).json()["id"]
    client.post(f"/api/v1/uplift/exceptions/{exc_id}/approve", headers=approver)
    client.get(f"/api/v1/devices/{device.id}/readiness", headers=approver)

    after = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "readiness.evaluated")
        .filter(AuditEvent.object_id == str(device.id))
        .count()
    )
    assert after == before + 1
