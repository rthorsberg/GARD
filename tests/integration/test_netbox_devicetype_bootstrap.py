"""Integration tests for F9 NetBox device type bootstrap."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from gard.core.tokens import issue_token
from gard.integrations.netbox.client import NetboxDeviceRecord
from gard.integrations.netbox.devicetype_importer import EntryStatus, import_entry, run_bootstrap
from gard.integrations.netbox.devicetype_manifest import load_manifest
from gard.models._enums import Role
from tests.integration._csv_helpers import csv_body, csv_row

pytestmark = pytest.mark.integration


class FakeWriteClient:
    """In-memory NetBox write stub for bootstrap tests."""

    def __init__(self) -> None:
        self.manufacturers: dict[str, dict[str, Any]] = {}
        self.device_types: dict[str, dict[str, Any]] = {}
        self.templates: dict[str, list[dict[str, Any]]] = {
            "api/dcim/interface-templates/": [],
            "api/dcim/power-port-templates/": [],
            "api/dcim/console-port-templates/": [],
            "api/dcim/console-server-port-templates/": [],
            "api/dcim/power-outlet-templates/": [],
            "api/dcim/front-port-templates/": [],
            "api/dcim/rear-port-templates/": [],
            "api/dcim/module-bay-templates/": [],
            "api/dcim/device-bay-templates/": [],
        }
        self._next_id = 1

    def get_by_slug(self, collection_path: str, slug: str) -> dict[str, Any] | None:
        if collection_path == "api/dcim/manufacturers/":
            return self.manufacturers.get(slug)
        if collection_path == "api/dcim/device-types/":
            return self.device_types.get(slug)
        return None

    def ensure_manufacturer(self, name: str, slug: str) -> dict[str, Any]:
        existing = self.manufacturers.get(slug)
        if existing:
            return existing
        row = {"id": self._next_id, "name": name, "slug": slug}
        self._next_id += 1
        self.manufacturers[slug] = row
        return row

    def post(self, path: str, json_body: dict[str, Any]) -> dict[str, Any]:
        if path == "api/dcim/device-types/":
            slug = str(json_body["slug"])
            row = {"id": self._next_id, **json_body}
            self._next_id += 1
            self.device_types[slug] = row
            return row
        if path in self.templates:
            row = {"id": self._next_id, **json_body}
            self._next_id += 1
            self.templates[path].append(row)
            return row
        raise AssertionError(f"unexpected post path: {path}")

    def list_all(self, path: str, *, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        dt_id = (params or {}).get("device_type_id")
        if path in self.templates and dt_id is not None:
            return [t for t in self.templates[path] if t.get("device_type") == dt_id]
        return []

    def count_component_templates(self, device_type_id: int) -> int:
        total = 0
        for path in self.templates:
            total += len(self.list_all(path, params={"device_type_id": device_type_id}))
        return total


def test_bootstrap_isr1121_imports_interfaces(project_root: Path) -> None:
    manifest = load_manifest(repo_root=project_root)
    isr = next(e for e in manifest.entries if e.id == "cisco-isr1121-8p")
    client = FakeWriteClient()

    result = import_entry(client, manifest, isr)
    assert result.status == EntryStatus.CREATED
    assert result.netbox_device_type_id is not None

    dt = client.device_types[isr.expected_slug]
    assert dt["model"] == "ISR 1121-8P"

    ifaces = client.templates["api/dcim/interface-templates/"]
    assert len(ifaces) >= 10
    power = client.templates["api/dcim/power-port-templates/"]
    assert len(power) >= 1


def test_second_bootstrap_run_all_skipped(project_root: Path) -> None:
    manifest = load_manifest(repo_root=project_root)
    client = FakeWriteClient()
    first = run_bootstrap(client, manifest, netbox_url="http://127.0.0.1:18888")
    assert first.summary.created == len(manifest.entries)

    second = run_bootstrap(client, manifest, netbox_url="http://127.0.0.1:18888")
    assert second.summary.skipped == len(manifest.entries)
    assert second.summary.created == 0
    assert second.summary.conflict == 0


def test_f7_sync_matches_isr1121_serials_after_bootstrap(client, db_session, project_root) -> None:
    """Bootstrap community model strings align with F7 serial matching on seeded fixtures."""
    from gard.catalog.normalization_loader import load_catalog

    issued = issue_token(
        session=db_session,
        name="netbox-bootstrap-sync",
        subject="user:netbox",
        roles=[Role.lifecycle_manager],
        created_by="test",
    )
    db_session.commit()
    jwt = issued.jwt
    load_catalog(db_session, project_root / "gard-catalog" / "normalization")
    db_session.commit()

    for serial, hostname in (("FOC123456", "r-osl-001"), ("FOC123457", "r-osl-002")):
        body = csv_body([csv_row(hostname=hostname, serial_number=serial)])
        r = client.post(
            "/api/v1/imports/devices/csv",
            files={"file": ("devices.csv", body, "text/csv")},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert r.status_code == 200, r.text

    manifest = load_manifest(repo_root=project_root)
    isr = next(e for e in manifest.entries if e.id == "cisco-isr1121-8p")
    yaml_data = yaml.safe_load(manifest.library_file(isr).read_text(encoding="utf-8"))
    community_model = str(yaml_data["model"])

    fake_devices = [
        NetboxDeviceRecord(
            id=201,
            name="r-osl-001",
            serial="FOC123456",
            site="oslo-dc1",
            role="edge",
            vendor_raw="Cisco",
            model_raw=community_model,
            tags=("edge",),
        ),
        NetboxDeviceRecord(
            id=202,
            name="r-osl-002",
            serial="FOC123457",
            site="oslo-dc1",
            role="edge",
            vendor_raw="Cisco",
            model_raw=community_model,
            tags=("edge",),
        ),
    ]

    class FakeReadClient:
        def list_devices(self) -> list[NetboxDeviceRecord]:
            return fake_devices

    with patch(
        "gard.core.netbox_sync_controller.client_from_settings", return_value=FakeReadClient()
    ):
        r = client.post(
            "/api/v1/integrations/netbox/sync",
            headers={"Authorization": f"Bearer {jwt}"},
        )
    assert r.status_code == 200, r.text
    report = r.json()["data"]["report"]
    assert report["matched_count"] >= 2
