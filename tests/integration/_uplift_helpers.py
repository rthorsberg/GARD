"""Shared builders for F5 uplift integration tests.

Keeps each test focused on the behaviour under test rather than the
boilerplate of seeding a device + a live FirmwareTarget + an F4
readiness verdict.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid

from sqlalchemy.orm import Session

from gard.core.tokens import issue_token
from gard.models import Device, FirmwareTarget, ReadinessEvaluation
from gard.models._enums import LifecycleState, Role


def auth_header(
    session: Session,
    *,
    roles: list[Role],
    subject: str,
) -> dict[str, str]:
    issued = issue_token(
        session=session,
        name=f"tok-{subject}",
        subject=subject,
        roles=roles,
        created_by="test",
    )
    return {"Authorization": f"Bearer {issued.jwt}"}


def make_device(
    session: Session,
    *,
    hostname: str,
    site: str = "oslo-dc1",
    region: str | None = "eu-north",
    platform_family: str = "acme-os",
    vendor: str = "acme",
    lifecycle_state: LifecycleState = LifecycleState.ready_for_uplift,
) -> Device:
    device = Device(
        hostname=hostname,
        site=site,
        region=region,
        vendor_raw=vendor,
        vendor_normalized=vendor,
        model_raw="m1",
        model_normalized="m1",
        platform_family=platform_family,
        source_system="test",
        lifecycle_state=lifecycle_state,
    )
    session.add(device)
    session.flush()
    return device


def make_live_target(
    session: Session,
    *,
    platform_family: str = "acme-os",
    target_version: str = "9.0.0",
    name: str | None = None,
    scope_selector: dict | None = None,
) -> FirmwareTarget:
    target = FirmwareTarget(
        name=name or f"target-{platform_family}-{target_version}",
        platform_family=platform_family,
        target_version=target_version,
        scope_selector=scope_selector or {"platform_family": platform_family},
        source_file_relpath=f"targets/{platform_family}.yaml",
        catalog_schema_version="1.0",
    )
    session.add(target)
    session.flush()
    return target


def make_readiness(
    session: Session,
    *,
    device: Device,
    state: str = "ready_for_uplift",
    target_version: str = "9.0.0",
    observed_version: str = "8.1.0",
    blockers: list[dict] | None = None,
) -> ReadinessEvaluation:
    row = ReadinessEvaluation(
        device_id=device.id,
        readiness_state=state,
        target_version=target_version,
        observed_version=observed_version,
        upgrade_path_exists=state == "ready_for_uplift",
        applicable_rules_count=0,
        blockers=blockers or [],
        recommended_actions=[],
        reasons=[],
        confidence=decimal.Decimal("1.00"),
        evaluated_at=dt.datetime.now(dt.UTC),
        correlation_id="test-corr",
        actor="test",
    )
    session.add(row)
    session.flush()
    return row


def future_window(
    *,
    start_offset_hours: int = 24,
    duration_hours: int = 2,
) -> tuple[str, str]:
    """Return (start_iso, end_iso) for a valid future change window."""
    start = dt.datetime.now(dt.UTC) + dt.timedelta(hours=start_offset_hours)
    end = start + dt.timedelta(hours=duration_hours)
    return start.isoformat(), end.isoformat()


def new_plan(client, headers: dict[str, str], *, name: str | None = None) -> str:
    """Create a plan via the API and return its id."""
    resp = client.post(
        "/api/v1/uplift/plans",
        json={"name": name or f"plan-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]
