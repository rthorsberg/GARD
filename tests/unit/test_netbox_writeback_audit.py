"""Unit tests for F10 write-back audit integration in sync controller."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import select

from gard.core import netbox_sync_controller as ctrl
from gard.core.rbac import Principal
from gard.core.settings import reset_settings_cache
from gard.integrations.netbox.client import NetboxDeviceRecord
from gard.integrations.netbox.writeback_publisher import (
    WritebackEntry,
    WritebackEntryStatus,
    WritebackPhase,
    WritebackReport,
    WritebackSummary,
)
from gard.models import AuditEvent, LifecycleEvidence
from gard.models._enums import ActorType, Role


class FakeNetboxClient:
    def __init__(self, records: list[NetboxDeviceRecord]) -> None:
        self._records = records

    def list_devices(self) -> list[NetboxDeviceRecord]:
        return list(self._records)


def _record(nb_id: int = 101) -> NetboxDeviceRecord:
    return NetboxDeviceRecord(
        id=nb_id,
        name="r-osl-001",
        serial="FOC123456",
        site="oslo-dc1",
        role="edge",
        vendor_raw="Cisco",
        model_raw="ISR1121",
        tags=("edge",),
    )


def _fake_writeback_report() -> WritebackReport:
    import uuid as uuid_mod

    return WritebackReport(
        phase=WritebackPhase.completed,
        summary=WritebackSummary(updated=1),
        entries=[
            WritebackEntry(
                device_id=uuid_mod.uuid4(),
                netbox_device_id=101,
                status=WritebackEntryStatus.updated,
            )
        ],
    )


@pytest.fixture
def writeback_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_settings_cache()
    monkeypatch.setenv("GARD_NETBOX_URL", "http://127.0.0.1:18888")
    monkeypatch.setenv("GARD_NETBOX_TOKEN", "read-token")
    monkeypatch.setenv("GARD_NETBOX_WRITE_TOKEN", "write-token")
    monkeypatch.setenv("GARD_NETBOX_WRITEBACK_ENABLED", "true")
    reset_settings_cache()


def test_sync_emits_writeback_audit(db_session, writeback_settings) -> None:
    principal = Principal(
        subject="user:test",
        roles=[Role.lifecycle_manager],
        actor_type=ActorType.user,
    )
    fake = FakeNetboxClient([_record()])

    with (
        patch("gard.core.netbox_sync_controller.client_from_settings", return_value=fake),
        patch(
            "gard.core.netbox_sync_controller.run_writeback",
            return_value=_fake_writeback_report(),
        ),
    ):
        outcome = ctrl.run_sync(
            session=db_session,
            audit_session=db_session,
            principal=principal,
            writeback_confirm=True,
        )

    db_session.commit()

    assert outcome.report.writeback is not None
    actions = list(
        db_session.scalars(
            select(AuditEvent.action).where(AuditEvent.action.like("netbox.writeback.%"))
        )
    )
    assert "netbox.writeback.started" in actions
    assert "netbox.writeback.completed" in actions

    evidence = db_session.scalar(
        select(LifecycleEvidence).where(LifecycleEvidence.evidence_type == "netbox_sync")
    )
    assert evidence is not None
    assert evidence.after_state.get("writeback", {}).get("updated") == 1


def test_sync_skips_writeback_without_confirm_on_non_localhost(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    reset_settings_cache()
    monkeypatch.setenv("GARD_NETBOX_URL", "https://netbox.example.com")
    monkeypatch.setenv("GARD_NETBOX_TOKEN", "read-token")
    monkeypatch.setenv("GARD_NETBOX_WRITE_TOKEN", "write-token")
    reset_settings_cache()

    principal = Principal(
        subject="user:test",
        roles=[Role.lifecycle_manager],
        actor_type=ActorType.user,
    )
    fake = FakeNetboxClient([_record()])

    with patch("gard.core.netbox_sync_controller.client_from_settings", return_value=fake):
        outcome = ctrl.run_sync(
            session=db_session,
            audit_session=db_session,
            principal=principal,
            writeback_confirm=False,
        )

    assert outcome.report.writeback is not None
    assert outcome.report.writeback.phase == WritebackPhase.skipped
