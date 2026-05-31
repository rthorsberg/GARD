"""F7 US2 — tagged_with readiness after NetBox tag sync."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import select

from gard.catalog.firmware_loader import load_firmware_catalog
from gard.catalog.normalization_loader import load_catalog
from gard.integrations.netbox.client import NetboxDeviceRecord
from gard.models import Device, FirmwarePrerequisiteRule
from tests.integration._mvp_isr1121_helpers import run_evaluations
from tests.integration.test_netbox_sync import FakeNetboxClient, _token

pytestmark = pytest.mark.integration

TAG_TEST_SITE = "nb-tag-test-site"


def _edge_prereq(session) -> None:
    session.add(
        FirmwarePrerequisiteRule(
            name="nb-tag-test-edge-required",
            applies_to={"site_in": [TAG_TEST_SITE], "platform_family": "ios"},
            predicate_kind="tagged_with",
            predicate_args={"tags": ["edge"]},
            severity="required",
            evaluable=True,
            source_file_relpath="prerequisites/test-edge-tag.yaml",
            catalog_schema_version="1.0.0",
        )
    )
    session.flush()


def _import_tag_test_device(client, jwt: str) -> None:
    header = (
        "hostname,site,serial_number,vendor_raw,model_raw,platform_family_raw,"
        "hardware_revision,management_ip,region,role,observed_firmware,"
        "observed_bootloader,observed_at,ram_mb,disk_mb,licenses\n"
    )
    row = (
        f"nb-tag-001,{TAG_TEST_SITE},NBEDGE001,Cisco Systems,ISR1121-8P,ios-xe,"
        "V02,10.20.30.40,NO,edge,16.9.5,rom-monitor 17.07,"
        "2026-05-26T22:14:03Z,2048,4096,\n"
    )
    body = (header + row).encode("utf-8")
    r = client.post(
        "/api/v1/imports/devices/csv",
        files={"file": ("nb-tag.csv", body, "text/csv")},
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert r.status_code == 200, r.text


def _readiness_for_device(client, jwt: str, device_id) -> dict:
    r = client.get(
        f"/api/v1/devices/{device_id}/readiness",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_tagged_with_passes_after_netbox_sync(client, db_session, project_root) -> None:
    jwt = _token(db_session)
    load_catalog(db_session, project_root / "gard-catalog" / "normalization")
    load_firmware_catalog(db_session, project_root / "gard-catalog" / "firmware")
    _edge_prereq(db_session)
    db_session.commit()

    _import_tag_test_device(client, jwt)
    run_evaluations(client, {"Authorization": f"Bearer {jwt}"})

    device = db_session.scalar(select(Device).where(Device.hostname == "nb-tag-001"))
    assert device is not None
    assert device.tags is None

    before = _readiness_for_device(client, jwt, device.id)
    assert before["state"] == "ready_for_uplift"
    blocker_kinds = {b["predicate_kind"] for b in before["blockers"]}
    assert "tagged_with" in blocker_kinds
    assert all(b["severity"] == "recommended" for b in before["blockers"] if b["predicate_kind"] == "tagged_with")

    fake = FakeNetboxClient(
        [
            NetboxDeviceRecord(
                id=501,
                name="nb-tag-001",
                serial="NBEDGE001",
                site=TAG_TEST_SITE,
                role="edge",
                vendor_raw="Cisco",
                model_raw="ISR1121-8P",
                tags=("edge",),
            )
        ]
    )
    with patch("gard.core.netbox_sync_controller.client_from_settings", return_value=fake):
        sync = client.post(
            "/api/v1/integrations/netbox/sync",
            headers={"Authorization": f"Bearer {jwt}"},
        )
    assert sync.status_code == 200, sync.text
    db_session.expire_all()
    device = db_session.get(Device, device.id)
    assert device.tags == ["edge"]

    after = _readiness_for_device(client, jwt, device.id)
    assert after["state"] == "ready_for_uplift"
    assert "tagged_with" not in {b["predicate_kind"] for b in after["blockers"]}
    assert not any(r.get("kind") == "predicate_deferred" for r in after.get("reasons", []))


def test_tagged_with_blocks_when_tag_removed_on_resync(client, db_session, project_root) -> None:
    jwt = _token(db_session)
    load_catalog(db_session, project_root / "gard-catalog" / "normalization")
    load_firmware_catalog(db_session, project_root / "gard-catalog" / "firmware")
    _edge_prereq(db_session)
    db_session.commit()

    _import_tag_test_device(client, jwt)
    run_evaluations(client, {"Authorization": f"Bearer {jwt}"})

    device = db_session.scalar(select(Device).where(Device.hostname == "nb-tag-001"))
    assert device is not None

    record = NetboxDeviceRecord(
        id=501,
        name="nb-tag-001",
        serial="NBEDGE001",
        site=TAG_TEST_SITE,
        role="edge",
        vendor_raw="Cisco",
        model_raw="ISR1121-8P",
        tags=("edge",),
    )
    with patch("gard.core.netbox_sync_controller.client_from_settings", return_value=FakeNetboxClient([record])):
        assert client.post("/api/v1/integrations/netbox/sync", headers={"Authorization": f"Bearer {jwt}"}).status_code == 200

    db_session.expire_all()
    assert db_session.get(Device, device.id).tags == ["edge"]
    assert _readiness_for_device(client, jwt, device.id)["state"] == "ready_for_uplift"

    record_no_tag = NetboxDeviceRecord(
        id=501,
        name="nb-tag-001",
        serial="NBEDGE001",
        site=TAG_TEST_SITE,
        role="edge",
        vendor_raw="Cisco",
        model_raw="ISR1121-8P",
        tags=(),
    )
    with patch("gard.core.netbox_sync_controller.client_from_settings", return_value=FakeNetboxClient([record_no_tag])):
        assert client.post("/api/v1/integrations/netbox/sync", headers={"Authorization": f"Bearer {jwt}"}).status_code == 200

    db_session.expire_all()
    assert db_session.get(Device, device.id).tags == []

    blocked = _readiness_for_device(client, jwt, device.id)
    assert blocked["state"] == "blocked"
    tagged = [b for b in blocked["blockers"] if b["predicate_kind"] == "tagged_with"]
    assert tagged
    assert tagged[0]["severity"] == "required"
