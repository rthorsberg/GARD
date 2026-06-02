"""Contract tests for F12 IPAM alignment OpenAPI shapes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from gard.api.schemas.ipam_alignment import (
    DeviceNetworkContextOut,
    IpamAlignmentFindingList,
    IpamAlignmentFindingOut,
    IpamAlignmentReportOut,
    IpamAlignmentSummaryOut,
)
from gard.api.schemas.netbox_integration import NetboxSyncReportOut


def test_sync_report_embeds_ipam_alignment() -> None:
    report = NetboxSyncReportOut(
        matched_count=1,
        created_count=0,
        updated_count=1,
        orphaned_count=0,
        ipam_alignment=IpamAlignmentReportOut(
            phase="completed",
            run_id=uuid.uuid4(),
            summary=IpamAlignmentSummaryOut(
                devices_checked=1,
                aligned_count=1,
                mismatch_count=0,
                error_count=0,
                warning_count=0,
                info_count=1,
            ),
        ),
    )
    dumped = report.model_dump(mode="json")
    assert "ipam_alignment" in dumped
    assert dumped["ipam_alignment"]["phase"] == "completed"


def test_findings_list_shape() -> None:
    now = datetime.now(tz=UTC)
    item = IpamAlignmentFindingOut(
        id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        device_id=uuid.uuid4(),
        kind="mgmt_ip_mismatch",
        severity="error",
        status="open",
        created_at=now,
    )
    lst = IpamAlignmentFindingList(items=[item], total_returned=1)
    assert lst.total_returned == 1


def test_network_context_shape() -> None:
    ctx = DeviceNetworkContextOut(
        device_id=uuid.uuid4(),
        netbox_device_id=42,
        interfaces=[{"name": "Gi0/0", "enabled": True}],
        captured_at=datetime.now(tz=UTC),
    )
    assert ctx.netbox_device_id == 42
