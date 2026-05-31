"""F7 US1 — NetBox sync / reconcile integration tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import select

from gard.core.tokens import issue_token
from gard.integrations.netbox.client import NetboxDeviceRecord, NetboxUnreachable
from gard.models import AuditEvent, Device, LifecycleEvidence, NetboxSyncRun
from gard.models._enums import Role
from tests.integration._csv_helpers import csv_body, csv_row

pytestmark = pytest.mark.integration


def _token(db_session, *, role: Role = Role.lifecycle_manager) -> str:
    issued = issue_token(
        session=db_session,
        name="netbox-sync",
        subject="user:netbox",
        roles=[role],
        created_by="test",
    )
    db_session.commit()
    return issued.jwt


def _import_one_device(
    client, jwt: str, *, serial: str = "FOC123456", hostname: str = "r-osl-001"
) -> None:
    body = csv_body([csv_row(hostname=hostname, serial_number=serial)])
    r = client.post(
        "/api/v1/imports/devices/csv",
        files={"file": ("devices.csv", body, "text/csv")},
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert r.status_code == 200, r.text


def _nb_record(
    *,
    nb_id: int = 101,
    name: str = "r-osl-001",
    serial: str | None = "FOC123456",
    site: str = "oslo-dc1",
    tags: tuple[str, ...] = ("edge",),
) -> NetboxDeviceRecord:
    return NetboxDeviceRecord(
        id=nb_id,
        name=name,
        serial=serial,
        site=site,
        role="edge",
        vendor_raw="Cisco",
        model_raw="ISR1121-8P",
        tags=tags,
    )


class FakeNetboxClient:
    def __init__(self, records: list[NetboxDeviceRecord]) -> None:
        self._records = records

    def list_devices(self) -> list[NetboxDeviceRecord]:
        return list(self._records)


def test_sync_matches_existing_device_by_serial(client, db_session, project_root) -> None:
    jwt = _token(db_session)
    from gard.catalog.normalization_loader import load_catalog

    load_catalog(db_session, project_root / "gard-catalog" / "normalization")
    db_session.commit()

    _import_one_device(client, jwt)

    fake = FakeNetboxClient([_nb_record()])
    with patch("gard.core.netbox_sync_controller.client_from_settings", return_value=fake):
        r = client.post(
            "/api/v1/integrations/netbox/sync",
            headers={"Authorization": f"Bearer {jwt}"},
        )

    assert r.status_code == 200, r.text
    payload = r.json()["data"]
    report = payload["report"]
    assert report["created_count"] == 0
    assert report["updated_count"] == 1
    assert report["matched_count"] == 1

    device = db_session.scalar(select(Device).where(Device.hostname == "r-osl-001"))
    assert device is not None
    assert device.netbox_device_id == 101
    assert device.tags == ["edge"]
    assert device.source_system == "netbox"


def test_sync_creates_netbox_only_device(client, db_session) -> None:
    jwt = _token(db_session)
    fake = FakeNetboxClient(
        [_nb_record(nb_id=202, name="r-ber-002", serial="FOC999888", site="ber-dc1")]
    )
    with patch("gard.core.netbox_sync_controller.client_from_settings", return_value=fake):
        r = client.post(
            "/api/v1/integrations/netbox/sync",
            headers={"Authorization": f"Bearer {jwt}"},
        )

    assert r.status_code == 200, r.text
    report = r.json()["data"]["report"]
    assert report["created_count"] == 1
    assert report["updated_count"] == 0

    device = db_session.scalar(select(Device).where(Device.serial_number == "FOC999888"))
    assert device is not None
    assert device.lifecycle_state.value == "imported"
    assert device.source_system == "netbox"


def test_sync_orphan_report_no_delete(client, db_session, project_root) -> None:
    jwt = _token(db_session)
    from gard.catalog.normalization_loader import load_catalog

    load_catalog(db_session, project_root / "gard-catalog" / "normalization")
    db_session.commit()

    _import_one_device(client, jwt, serial="FOC111111", hostname="csv-only")

    fake = FakeNetboxClient([_nb_record(nb_id=303, name="nb-only", serial="FOC222222")])
    with patch("gard.core.netbox_sync_controller.client_from_settings", return_value=fake):
        r = client.post(
            "/api/v1/integrations/netbox/sync",
            headers={"Authorization": f"Bearer {jwt}"},
        )

    assert r.status_code == 200, r.text
    report = r.json()["data"]["report"]
    assert report["orphaned_count"] == 1
    assert report["orphaned_in_gard"][0]["hostname"] == "csv-only"

    orphan = db_session.scalar(select(Device).where(Device.hostname == "csv-only"))
    assert orphan is not None


def test_sync_netbox_unreachable_rollback(client, db_session, project_root) -> None:
    jwt = _token(db_session)
    from gard.catalog.normalization_loader import load_catalog

    load_catalog(db_session, project_root / "gard-catalog" / "normalization")
    db_session.commit()

    _import_one_device(client, jwt)

    class BrokenClient:
        def list_devices(self) -> list[NetboxDeviceRecord]:
            raise NetboxUnreachable("connection refused")

    with patch(
        "gard.core.netbox_sync_controller.client_from_settings", return_value=BrokenClient()
    ):
        r = client.post(
            "/api/v1/integrations/netbox/sync",
            headers={"Authorization": f"Bearer {jwt}"},
        )

    assert r.status_code == 502, r.text
    assert r.json()["error"]["code"] == "NETBOX_UNREACHABLE"

    device = db_session.scalar(select(Device).where(Device.hostname == "r-osl-001"))
    assert device is not None
    assert device.netbox_device_id is None
    assert db_session.scalar(select(NetboxSyncRun)) is None


def test_sync_duplicate_serial_in_netbox(client, db_session) -> None:
    jwt = _token(db_session)
    fake = FakeNetboxClient(
        [
            _nb_record(nb_id=1, serial="DUP001", name="a"),
            _nb_record(nb_id=2, serial="DUP001", name="b"),
        ]
    )
    with patch("gard.core.netbox_sync_controller.client_from_settings", return_value=fake):
        r = client.post(
            "/api/v1/integrations/netbox/sync",
            headers={"Authorization": f"Bearer {jwt}"},
        )

    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "NETBOX_AMBIGUOUS_IDENTITY"
    assert db_session.scalar(select(Device)) is None


def test_sync_emits_audit_and_evidence(client, db_session) -> None:
    jwt = _token(db_session)
    fake = FakeNetboxClient([_nb_record()])
    with patch("gard.core.netbox_sync_controller.client_from_settings", return_value=fake):
        r = client.post(
            "/api/v1/integrations/netbox/sync",
            headers={"Authorization": f"Bearer {jwt}"},
        )
    assert r.status_code == 200, r.text

    actions = list(
        db_session.scalars(select(AuditEvent.action).where(AuditEvent.action.like("netbox.sync.%")))
    )
    assert "netbox.sync.started" in actions
    assert "netbox.sync.completed" in actions

    evidence = db_session.scalar(
        select(LifecycleEvidence).where(LifecycleEvidence.evidence_type == "netbox_sync")
    )
    assert evidence is not None


def test_summary_after_sync(client, db_session) -> None:
    jwt = _token(db_session)
    fake = FakeNetboxClient([_nb_record()])
    with patch("gard.core.netbox_sync_controller.client_from_settings", return_value=fake):
        client.post(
            "/api/v1/integrations/netbox/sync",
            headers={"Authorization": f"Bearer {jwt}"},
        )

    r = client.get(
        "/api/v1/integrations/netbox/summary",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["netbox_linked"] == 1
    assert data["last_sync_at"] is not None


def test_viewer_can_read_summary_not_sync(client, db_session) -> None:
    viewer_jwt = _token(db_session, role=Role.viewer)
    r = client.post(
        "/api/v1/integrations/netbox/sync",
        headers={"Authorization": f"Bearer {viewer_jwt}"},
    )
    assert r.status_code == 403

    r2 = client.get(
        "/api/v1/integrations/netbox/summary",
        headers={"Authorization": f"Bearer {viewer_jwt}"},
    )
    assert r2.status_code == 200
