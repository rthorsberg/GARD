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
from gard.models import (
    ComplianceEvaluation,
    Device,
    FirmwarePrerequisiteRule,
    FirmwareTarget,
    ReadinessEvaluation,
)
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


def future_expiry(*, days: int = 30) -> str:
    return (dt.datetime.now(dt.UTC) + dt.timedelta(days=days)).isoformat()


def make_prereq_rule(
    session: Session,
    *,
    name: str = "min-ram-rule",
    predicate_kind: str = "min_ram_mb",
) -> FirmwarePrerequisiteRule:
    rule = FirmwarePrerequisiteRule(
        name=name,
        applies_to={"platform_family": "acme-os"},
        predicate_kind=predicate_kind,
        predicate_args={"min_ram_mb": 8192},
        severity="required",
        source_file_relpath="prereqs/min-ram.yaml",
        catalog_schema_version="1.0",
    )
    session.add(rule)
    session.flush()
    return rule


def make_compliance(
    session: Session,
    *,
    device: Device,
    state: str = "outside_target",
    target_version: str = "9.0.0",
    observed_version: str = "8.1.0",
) -> ComplianceEvaluation:
    row = ComplianceEvaluation(
        device_id=device.id,
        compliance_state=state,
        target_version=target_version,
        observed_version=observed_version,
        primary_drift_type="target_drift" if state == "outside_target" else None,
        reasons=[],
        recommended_actions=[],
        confidence=decimal.Decimal("1.00"),
        evaluated_at=dt.datetime.now(dt.UTC),
        correlation_id="test-corr",
        actor="test",
    )
    session.add(row)
    session.flush()
    return row


def make_blocked_device(
    session: Session,
    *,
    hostname: str = "blocked.oslo",
    rule: FirmwarePrerequisiteRule | None = None,
    synthetic_kind: str | None = None,
) -> tuple[Device, uuid.UUID | None, str | None]:
    """Seed blocked device + F3/F4 rows. Returns (device, rule_id, synthetic_kind)."""
    make_live_target(session, target_version="9.0.0")
    device = make_device(
        session,
        hostname=hostname,
        lifecycle_state=LifecycleState.blocked,
    )
    make_compliance(session, device=device, state="outside_target")
    blockers: list[dict]
    rule_id: uuid.UUID | None = None
    syn: str | None = synthetic_kind
    if synthetic_kind is not None:
        blockers = [
            {
                "rule_id": None,
                "rule_name": None,
                "predicate_kind": synthetic_kind,
                "severity": "required",
                "required": {"field": "ram_mb"},
                "observed": None,
                "detail": f"synthetic blocker {synthetic_kind}",
            }
        ]
    else:
        rule = rule or make_prereq_rule(session)
        rule_id = rule.id
        blockers = [
            {
                "rule_id": str(rule.id),
                "rule_name": rule.name,
                "predicate_kind": rule.predicate_kind,
                "severity": "required",
                "required": rule.predicate_args,
                "observed": {"ram_mb": 4096},
                "detail": "insufficient RAM for uplift",
            }
        ]
    make_readiness(
        session,
        device=device,
        state="blocked",
        blockers=blockers,
    )
    return device, rule_id, syn


def file_exception_payload(
    *,
    device_id: uuid.UUID,
    blocker_rule_id: uuid.UUID | None = None,
    synthetic_kind: str | None = None,
    expires_at: str | None = None,
) -> dict:
    body: dict = {
        "device_id": str(device_id),
        "justification": "Accepted known risk for end-of-life hardware in this site.",
        "expires_at": expires_at or future_expiry(days=30),
    }
    if blocker_rule_id is not None:
        body["blocker_rule_id"] = str(blocker_rule_id)
    if synthetic_kind is not None:
        body["synthetic_kind"] = synthetic_kind
    return body


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
