"""F5 US1 - plans + wave drafting (T027-T034)."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from gard.models import AuditEvent, Device, UpliftWave
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


def _seed_ready_estate(db_session, *, n: int = 2, platform_family: str = "acme-os"):
    make_live_target(db_session, platform_family=platform_family, target_version="9.0.0")
    devices = []
    for i in range(n):
        d = make_device(db_session, hostname=f"r{i}.oslo", platform_family=platform_family)
        make_readiness(db_session, device=d, state="ready_for_uplift")
        devices.append(d)
    return devices


# ---- T027: happy-path draft ----------------------------------------------


def test_draft_wave_from_ready_pool(client, db_session) -> None:
    headers = auth_header(db_session, roles=[Role.lifecycle_manager], subject="user:lc")
    devices = _seed_ready_estate(db_session, n=2)
    db_session.commit()

    plan_id = new_plan(client, headers, name="q3-uplift")
    start, end = future_window()
    resp = client.post(
        f"/api/v1/uplift/plans/{plan_id}/waves",
        json={
            "name": "wave-1",
            "target_version": "9.0.0",
            "target_platform_family": "acme-os",
            "scope_selector": {"platform_family": "acme-os"},
            "change_window_start": start,
            "change_window_end": end,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["state"] == "draft"
    assert body["device_count"] == 2
    assert {d["hostname"] for d in body["devices"]} == {"r0.oslo", "r1.oslo"}
    # Positions are 1-based and contiguous.
    assert sorted(d["position"] for d in body["devices"]) == [1, 2]

    # No lifecycle transition on draft — devices remain ready_for_uplift.
    db_session.rollback()
    for d in devices:
        fresh = db_session.get(Device, d.id)
        assert fresh.lifecycle_state == LifecycleState.ready_for_uplift

    # Exactly one drafted audit row.
    drafted = db_session.query(AuditEvent).filter(AuditEvent.action == "uplift_wave.drafted").all()
    assert len(drafted) == 1
    assert drafted[0].object_id == body["id"]


# ---- T028: strict + ineligible -------------------------------------------


def test_strict_mode_rejects_ineligible(client, db_session) -> None:
    headers = auth_header(db_session, roles=[Role.lifecycle_manager], subject="user:lc")
    make_live_target(db_session, target_version="9.0.0")
    ready = make_device(db_session, hostname="ready.oslo")
    make_readiness(db_session, device=ready, state="ready_for_uplift")
    blocked = make_device(
        db_session, hostname="blocked.oslo", lifecycle_state=LifecycleState.blocked
    )
    make_readiness(db_session, device=blocked, state="blocked")
    db_session.commit()

    plan_id = new_plan(client, headers)
    start, end = future_window()
    resp = client.post(
        f"/api/v1/uplift/plans/{plan_id}/waves",
        json={
            "name": "wave-strict",
            "target_version": "9.0.0",
            "target_platform_family": "acme-os",
            "scope_selector": {"platform_family": "acme-os"},
            "mode": "strict",
            "change_window_start": start,
            "change_window_end": end,
        },
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INELIGIBLE_DEVICES_IN_SCOPE"


# ---- T029: skip_ineligible ------------------------------------------------


def test_skip_ineligible_drafts_eligible_subset(client, db_session) -> None:
    headers = auth_header(db_session, roles=[Role.lifecycle_manager], subject="user:lc")
    make_live_target(db_session, target_version="9.0.0")
    ready = make_device(db_session, hostname="ready.oslo")
    make_readiness(db_session, device=ready, state="ready_for_uplift")
    blocked = make_device(
        db_session, hostname="blocked.oslo", lifecycle_state=LifecycleState.blocked
    )
    make_readiness(db_session, device=blocked, state="blocked")
    db_session.commit()

    plan_id = new_plan(client, headers)
    start, end = future_window()
    resp = client.post(
        f"/api/v1/uplift/plans/{plan_id}/waves",
        json={
            "name": "wave-skip",
            "target_version": "9.0.0",
            "target_platform_family": "acme-os",
            "scope_selector": {"platform_family": "acme-os"},
            "mode": "skip_ineligible",
            "change_window_start": start,
            "change_window_end": end,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["device_count"] == 1
    assert body["devices"][0]["hostname"] == "ready.oslo"
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["current_readiness_state"] == "blocked"


# ---- T030: empty scope ----------------------------------------------------


def test_empty_scope_rejected(client, db_session) -> None:
    headers = auth_header(db_session, roles=[Role.lifecycle_manager], subject="user:lc")
    make_live_target(db_session, target_version="9.0.0")
    db_session.commit()

    plan_id = new_plan(client, headers)
    start, end = future_window()
    resp = client.post(
        f"/api/v1/uplift/plans/{plan_id}/waves",
        json={
            "name": "wave-empty",
            "target_version": "9.0.0",
            "target_platform_family": "acme-os",
            "scope_selector": {"platform_family": "no-such-family"},
            "change_window_start": start,
            "change_window_end": end,
        },
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "EMPTY_WAVE"


# ---- T031: idempotency ----------------------------------------------------


def test_idempotency_replay_and_ttl(client, db_session) -> None:
    headers = auth_header(db_session, roles=[Role.lifecycle_manager], subject="user:lc")
    _seed_ready_estate(db_session, n=1)
    db_session.commit()

    plan_id = new_plan(client, headers)
    start, end = future_window()
    payload = {
        "name": "wave-idem",
        "target_version": "9.0.0",
        "target_platform_family": "acme-os",
        "scope_selector": {"platform_family": "acme-os"},
        "change_window_start": start,
        "change_window_end": end,
    }
    key = str(uuid.uuid4())

    r1 = client.post(
        f"/api/v1/uplift/plans/{plan_id}/waves",
        json=payload,
        headers={**headers, "Idempotency-Key": key},
    )
    assert r1.status_code == 201, r1.text
    wave_id = r1.json()["id"]

    # Replay within TTL → 200 + same id.
    r2 = client.post(
        f"/api/v1/uplift/plans/{plan_id}/waves",
        json={**payload, "name": "wave-idem-replay"},
        headers={**headers, "Idempotency-Key": key},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["id"] == wave_id

    # No key → a brand-new wave.
    r3 = client.post(
        f"/api/v1/uplift/plans/{plan_id}/waves",
        json={**payload, "name": "wave-no-key"},
        headers=headers,
    )
    assert r3.status_code == 201
    assert r3.json()["id"] != wave_id

    # Back-date the original beyond TTL → same key now creates a new wave.
    db_session.rollback()
    wave = db_session.get(UpliftWave, uuid.UUID(wave_id))
    wave.drafted_at = dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)
    db_session.commit()

    r4 = client.post(
        f"/api/v1/uplift/plans/{plan_id}/waves",
        json={**payload, "name": "wave-post-ttl"},
        headers={**headers, "Idempotency-Key": key},
    )
    assert r4.status_code == 201, r4.text
    assert r4.json()["id"] != wave_id


# ---- T032: invalid change window -----------------------------------------


@pytest.mark.parametrize(
    ("start_off_h", "dur_h"),
    [
        (-1, 2),  # start in the past
        (24, 25),  # duration > 24h
    ],
)
def test_invalid_change_window(client, db_session, start_off_h, dur_h) -> None:
    headers = auth_header(db_session, roles=[Role.lifecycle_manager], subject="user:lc")
    _seed_ready_estate(db_session, n=1)
    db_session.commit()

    plan_id = new_plan(client, headers)
    start = dt.datetime.now(dt.UTC) + dt.timedelta(hours=start_off_h)
    end = start + dt.timedelta(hours=dur_h)
    resp = client.post(
        f"/api/v1/uplift/plans/{plan_id}/waves",
        json={
            "name": "wave-bad-window",
            "target_version": "9.0.0",
            "target_platform_family": "acme-os",
            "scope_selector": {"platform_family": "acme-os"},
            "change_window_start": start.isoformat(),
            "change_window_end": end.isoformat(),
        },
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_CHANGE_WINDOW"


def test_change_window_too_short(client, db_session) -> None:
    headers = auth_header(db_session, roles=[Role.lifecycle_manager], subject="user:lc")
    _seed_ready_estate(db_session, n=1)
    db_session.commit()

    plan_id = new_plan(client, headers)
    start = dt.datetime.now(dt.UTC) + dt.timedelta(hours=24)
    end = start + dt.timedelta(minutes=5)  # < 15min floor
    resp = client.post(
        f"/api/v1/uplift/plans/{plan_id}/waves",
        json={
            "name": "wave-short-window",
            "target_version": "9.0.0",
            "target_platform_family": "acme-os",
            "scope_selector": {"platform_family": "acme-os"},
            "change_window_start": start.isoformat(),
            "change_window_end": end.isoformat(),
        },
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_CHANGE_WINDOW"


# ---- T033: target_version not live ---------------------------------------


def test_target_version_not_live(client, db_session) -> None:
    headers = auth_header(db_session, roles=[Role.lifecycle_manager], subject="user:lc")
    # Device is ready but no live target for 9.9.9.
    d = make_device(db_session, hostname="r.oslo")
    make_readiness(db_session, device=d, state="ready_for_uplift")
    db_session.commit()

    plan_id = new_plan(client, headers)
    start, end = future_window()
    resp = client.post(
        f"/api/v1/uplift/plans/{plan_id}/waves",
        json={
            "name": "wave-no-target",
            "target_version": "9.9.9",
            "target_platform_family": "acme-os",
            "scope_selector": {"platform_family": "acme-os"},
            "change_window_start": start,
            "change_window_end": end,
        },
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "TARGET_VERSION_NOT_LIVE"


# ---- T034: plan archival --------------------------------------------------


def test_plan_archival_hides_from_default_listing(client, db_session) -> None:
    headers = auth_header(db_session, roles=[Role.lifecycle_manager], subject="user:lc")
    db_session.commit()

    plan_id = new_plan(client, headers, name="to-archive")
    arch = client.post(f"/api/v1/uplift/plans/{plan_id}/archive", headers=headers)
    assert arch.status_code == 200
    assert arch.json()["archived_at"] is not None

    default = client.get("/api/v1/uplift/plans", headers=headers)
    assert all(p["id"] != plan_id for p in default.json()["items"])

    with_arch = client.get("/api/v1/uplift/plans?include_archived=true", headers=headers)
    assert any(p["id"] == plan_id for p in with_arch.json()["items"])
