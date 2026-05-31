"""Shared bootstrap for F6 MVP vertical slice (Cisco ISR1121)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.catalog.firmware_loader import load_firmware_catalog
from gard.catalog.normalization_loader import load_catalog
from gard.core import compliance_evaluation_controller as compliance_ctrl
from gard.core.tokens import issue_token
from gard.models import AuditEvent, Device, FirmwarePackage, FirmwareTarget, LifecycleEvidence
from gard.models._enums import Role
from tests.integration._uplift_helpers import auth_header, future_window

GOLDEN_HOSTNAME = "r-osl-001"
BLOCKED_HOSTNAME = "r-osl-002"
TARGET_VERSION = "17.12.4"
PLATFORM_FAMILY = "ios"


@dataclass(frozen=True)
class MvpContext:
    drafter_headers: dict[str, str]
    approver_headers: dict[str, str]
    golden_device_id: uuid.UUID
    blocked_device_id: uuid.UUID
    import_job_id: uuid.UUID
    plan_id: str | None = None
    wave_id: str | None = None


def load_isr1121_catalogs(session: Session, project_root: Path) -> None:
    load_catalog(session, project_root / "gard-catalog" / "normalization")
    load_firmware_catalog(session, project_root / "gard-catalog" / "firmware")
    # Target package must appear built so package_drift does not mask target_drift
    # (MCP count_devices_outside_target reports target_drift counts).
    pkg = session.scalar(
        select(FirmwarePackage).where(
            FirmwarePackage.platform_family == PLATFORM_FAMILY,
            FirmwarePackage.version == TARGET_VERSION,
            FirmwarePackage.removed_at.is_(None),
        )
    )
    if pkg is not None:
        pkg.blob_present = True


def import_isr1121_fixture(
    client: TestClient,
    session: Session,
    project_root: Path,
    *,
    subject: str = "user:mvp-drafter",
) -> tuple[dict[str, str], dict]:
    load_isr1121_catalogs(session, project_root)
    issued = issue_token(
        session=session,
        name="mvp-import",
        subject=subject,
        roles=[Role.lifecycle_manager],
        created_by="test",
    )
    session.commit()
    headers = {"Authorization": f"Bearer {issued.jwt}"}

    csv_path = project_root / "deploy" / "scripts" / "fixtures" / "isr1121-devices.csv"
    body = csv_path.read_bytes()
    resp = client.post(
        "/api/v1/imports/devices/csv",
        files={"file": ("isr1121-devices.csv", body, "text/csv")},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return headers, resp.json()


def run_evaluations(client: TestClient, headers: dict[str, str]) -> None:
    comp = client.post(
        "/api/v1/compliance/evaluate",
        json={"scope_selector": {}},
        headers=headers,
    )
    assert comp.status_code == 200, comp.text
    ready = client.post(
        "/api/v1/readiness/evaluate",
        json={"scope_selector": {}},
        headers=headers,
    )
    assert ready.status_code == 200, ready.text


def device_by_hostname(session: Session, hostname: str) -> Device:
    row = session.scalar(select(Device).where(Device.hostname == hostname))
    assert row is not None, f"missing device {hostname!r}"
    return row


def bootstrap_mvp_estate(
    client: TestClient,
    session: Session,
    project_root: Path,
    *,
    with_uplift: bool = False,
) -> MvpContext:
    """Import ISR1121 fixture, evaluate, optionally draft+submit+approve wave."""
    headers, summary = import_isr1121_fixture(client, session, project_root)
    run_evaluations(client, headers)

    golden = device_by_hostname(session, GOLDEN_HOSTNAME)
    blocked = device_by_hostname(session, BLOCKED_HOSTNAME)

    drafter_headers = auth_header(
        session,
        roles=[Role.lifecycle_manager],
        subject="user:mvp-drafter",
    )
    approver_headers = auth_header(
        session,
        roles=[Role.change_approver],
        subject="user:mvp-approver",
    )
    session.commit()

    ctx = MvpContext(
        drafter_headers=drafter_headers,
        approver_headers=approver_headers,
        golden_device_id=golden.id,
        blocked_device_id=blocked.id,
        import_job_id=uuid.UUID(summary["job_id"]),
    )

    if not with_uplift:
        return ctx

    plan_resp = client.post(
        "/api/v1/uplift/plans",
        json={"name": "mvp-isr1121-plan", "description": "F6 golden path"},
        headers=drafter_headers,
    )
    assert plan_resp.status_code == 201, plan_resp.text
    plan_id = plan_resp.json()["id"]

    start, end = future_window()
    wave_resp = client.post(
        f"/api/v1/uplift/plans/{plan_id}/waves",
        json={
            "name": "mvp-isr1121-wave",
            "target_version": TARGET_VERSION,
            "target_platform_family": PLATFORM_FAMILY,
            "scope_selector": {"site_in": ["Oslo"], "platform_family": PLATFORM_FAMILY},
            "mode": "skip_ineligible",
            "change_window_start": start,
            "change_window_end": end,
        },
        headers={**drafter_headers, "Idempotency-Key": "mvp-isr1121-wave"},
    )
    assert wave_resp.status_code == 201, wave_resp.text
    wave_id = wave_resp.json()["id"]
    assert wave_resp.json()["device_count"] >= 1, "golden device must be in wave"

    submit = client.post(
        f"/api/v1/uplift/waves/{wave_id}/submit",
        headers=drafter_headers,
    )
    assert submit.status_code == 200, submit.text

    approve = client.post(
        f"/api/v1/uplift/waves/{wave_id}/approve",
        json={"citation": "CHG-MVP-ISR1121 approved by CAB for F6 vertical slice demo."},
        headers=approver_headers,
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["state"] == "approved"

    session.expire_all()
    return MvpContext(
        drafter_headers=drafter_headers,
        approver_headers=approver_headers,
        golden_device_id=golden.id,
        blocked_device_id=blocked.id,
        import_job_id=uuid.UUID(summary["job_id"]),
        plan_id=plan_id,
        wave_id=wave_id,
    )


def assert_isr1121_target_loaded(session: Session) -> FirmwareTarget:
    target = session.scalar(
        select(FirmwareTarget).where(
            FirmwareTarget.name == "cisco-ios-isr1121",
            FirmwareTarget.removed_at.is_(None),
        )
    )
    assert target is not None
    assert target.target_version == TARGET_VERSION
    return target


def audit_actions_for_device(session: Session, device_id: uuid.UUID) -> list[str]:
    rows = session.scalars(
        select(AuditEvent.action)
        .where(AuditEvent.object_id == str(device_id))
        .order_by(AuditEvent.timestamp.asc())
    ).all()
    return list(rows)


def evidence_for_import(session: Session, job_id: uuid.UUID) -> list[LifecycleEvidence]:
    return list(
        session.scalars(
            select(LifecycleEvidence).where(
                LifecycleEvidence.subject_type == "ImportJob",
                LifecycleEvidence.subject_id == str(job_id),
            )
        ).all()
    )


def rest_outside_target_count(
    session: Session,
    *,
    vendor: str = "cisco",
    platform: str = PLATFORM_FAMILY,
) -> int:
    summary = compliance_ctrl.fetch_summary(
        session,
        vendor_normalized=vendor,
        platform_family=platform,
    )
    return summary.counts_by_drift_type.get("target_drift", 0)
