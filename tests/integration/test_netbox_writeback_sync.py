"""F10 integration — post-sync write-back on NetBox sync."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import select

from gard.core.settings import reset_settings_cache
from gard.core.tokens import issue_token
from gard.integrations.netbox.client import NetboxDeviceRecord
from gard.integrations.netbox.writeback_publisher import (
    WritebackEntry,
    WritebackEntryStatus,
    WritebackPhase,
    WritebackReport,
    WritebackSummary,
)
from gard.models import Device
from gard.models._enums import Role
from tests.integration._csv_helpers import csv_body, csv_row

pytestmark = pytest.mark.integration


def _token(db_session, *, role: Role = Role.lifecycle_manager) -> str:
    issued = issue_token(
        session=db_session,
        name="netbox-writeback",
        subject="user:netbox-wb",
        roles=[role],
        created_by="test",
    )
    db_session.commit()
    return issued.jwt


def _nb_record(*, nb_id: int = 101) -> NetboxDeviceRecord:
    return NetboxDeviceRecord(
        id=nb_id,
        name="r-osl-001",
        serial="FOC123456",
        site="oslo-dc1",
        role="edge",
        vendor_raw="Cisco",
        model_raw="ISR1121-8P",
        tags=("edge",),
    )


class FakeNetboxClient:
    def __init__(self, records: list[NetboxDeviceRecord]) -> None:
        self._records = records

    def list_devices(self) -> list[NetboxDeviceRecord]:
        return list(self._records)


def _completed_writeback(updated: int = 1) -> WritebackReport:
    return WritebackReport(
        phase=WritebackPhase.completed,
        summary=WritebackSummary(updated=updated),
        entries=[
            WritebackEntry(
                device_id=uuid.uuid4(),
                netbox_device_id=101,
                status=WritebackEntryStatus.updated,
            )
        ],
    )


def test_sync_response_includes_writeback_section(
    client, db_session, project_root, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GARD_NETBOX_WRITE_TOKEN", "write-token")
    reset_settings_cache()
    jwt = _token(db_session)
    from gard.catalog.normalization_loader import load_catalog

    load_catalog(db_session, project_root / "gard-catalog" / "normalization")
    db_session.commit()

    body = csv_body([csv_row(hostname="r-osl-001", serial_number="FOC123456")])
    r = client.post(
        "/api/v1/imports/devices/csv",
        files={"file": ("devices.csv", body, "text/csv")},
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert r.status_code == 200, r.text

    fake = FakeNetboxClient([_nb_record()])
    with (
        patch("gard.core.netbox_sync_controller.client_from_settings", return_value=fake),
        patch(
            "gard.core.netbox_sync_controller.run_writeback",
            return_value=_completed_writeback(),
        ),
    ):
        r = client.post(
            "/api/v1/integrations/netbox/sync",
            headers={"Authorization": f"Bearer {jwt}"},
        )

    assert r.status_code == 200, r.text
    writeback = r.json()["data"]["report"]["writeback"]
    assert writeback is not None
    assert writeback["phase"] == "completed"
    assert writeback["summary"]["updated"] == 1


def test_second_sync_idempotent_writeback(
    client, db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GARD_NETBOX_WRITE_TOKEN", "write-token")
    reset_settings_cache()
    jwt = _token(db_session)
    fake = FakeNetboxClient([_nb_record()])
    unchanged = WritebackReport(
        phase=WritebackPhase.completed,
        summary=WritebackSummary(unchanged=1),
        entries=[],
    )

    with (
        patch("gard.core.netbox_sync_controller.client_from_settings", return_value=fake),
        patch("gard.core.netbox_sync_controller.run_writeback", return_value=unchanged),
    ):
        r = client.post(
            "/api/v1/integrations/netbox/sync",
            headers={"Authorization": f"Bearer {jwt}"},
        )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["report"]["writeback"]["summary"]["unchanged"] == 1

    device = db_session.scalar(select(Device).where(Device.hostname == "r-osl-001"))
    assert device is not None
    assert device.netbox_device_id == 101
