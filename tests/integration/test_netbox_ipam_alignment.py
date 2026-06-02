"""F12 US5 — NetBox IPAM alignment integration tests."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from gard.core.tokens import issue_token
from gard.integrations.netbox.client import NetboxDeviceRecord
from gard.models._enums import Role
from tests.integration._csv_helpers import csv_body, csv_row

pytestmark = pytest.mark.integration

NETBOX_URL = os.environ.get("GARD_NETBOX_URL", "http://127.0.0.1:18888")


def _token(db_session, *, role: Role = Role.lifecycle_manager) -> str:
    issued = issue_token(
        session=db_session,
        name="ipam-align",
        subject="user:ipam",
        roles=[role],
        created_by="test",
    )
    db_session.commit()
    return issued.jwt


def _nb_record(*, nb_id: int = 201, name: str = "r-ipam-001") -> NetboxDeviceRecord:
    return NetboxDeviceRecord(
        id=nb_id,
        name=name,
        serial="IPAM001",
        site="oslo",
        role="edge",
        vendor_raw="Cisco",
        model_raw="ISR1121",
        tags=(),
    )


class FakeNetboxClient:
    def __init__(self, records: list[NetboxDeviceRecord]) -> None:
        self._records = records

    def list_devices(self) -> list[NetboxDeviceRecord]:
        return list(self._records)

    def get_device(self, device_id: int) -> dict:
        return {
            "id": device_id,
            "primary_ip4": {"address": "10.10.10.1/24"},
            "site": {"id": 1, "slug": "oslo"},
            "role": {"slug": "edge"},
        }

    def list_interfaces(self, *, device_id: int) -> list[dict]:
        return [
            {
                "id": 1,
                "name": "Gi0/1",
                "enabled": True,
                "mode": "access",
                "mgmt_only": False,
            }
        ]

    def list_ip_addresses(self, *, device_id: int) -> list[dict]:
        return []

    def list_vrfs(self, *, site_id: int | None = None) -> list[dict]:
        return []

    def list_vlans(self, *, site_id: int | None = None) -> list[dict]:
        return []

    def list_vlan_groups(self, *, site_id: int | None = None) -> list[dict]:
        return [{"id": 1, "slug": "oslo-access"}]

    def probe_l2vpn_available(self) -> bool:
        return False

    def list_l2vpn_services(self) -> list[dict]:
        return []


def test_sync_includes_ipam_alignment_block(client, db_session, project_root) -> None:
    from gard.catalog.normalization_loader import load_catalog

    load_catalog(db_session, project_root / "gard-catalog" / "normalization")
    db_session.commit()

    jwt = _token(db_session)
    body = csv_body([csv_row(hostname="r-ipam-001", serial_number="IPAM001", management_ip="10.10.10.99")])
    r = client.post(
        "/api/v1/imports/devices/csv",
        files={"file": ("devices.csv", body, "text/csv")},
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert r.status_code == 200, r.text

    fake = FakeNetboxClient([_nb_record()])
    with patch("gard.core.netbox_sync_controller.client_from_settings", return_value=fake):
        sync = client.post(
            "/api/v1/integrations/netbox/sync",
            headers={"Authorization": f"Bearer {jwt}"},
        )
    assert sync.status_code == 200, sync.text
    report = sync.json()["data"]["report"]
    assert "ipam_alignment" in report
    alignment = report["ipam_alignment"]
    assert alignment["phase"] in ("completed", "partial", "skipped")
    if alignment.get("run_id"):
        findings = client.get(
            "/api/v1/integrations/netbox/alignment/findings",
            params={"run_id": alignment["run_id"]},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert findings.status_code == 200


@pytest.mark.skipif(
    not os.environ.get("GARD_NETBOX_TOKEN"),
    reason="Set GARD_NETBOX_TOKEN for live NetBox integration",
)
def test_live_netbox_alignment(client, db_session) -> None:
    jwt = _token(db_session)
    sync = client.post(
        "/api/v1/integrations/netbox/sync",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    if sync.status_code == 503:
        pytest.skip("NetBox not configured")
    assert sync.status_code == 200, sync.text
    assert "ipam_alignment" in sync.json()["data"]["report"]
