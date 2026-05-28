"""US1 AS3 — second CSV with updated firmware: new observation, no overwrite."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from gard.catalog.normalization_loader import load_catalog
from gard.core.tokens import issue_token
from gard.models import Device, DeviceObservation
from gard.models._enums import Role
from tests.integration._csv_helpers import csv_body, csv_row

pytestmark = pytest.mark.integration


def test_reimport_updates_observation_not_history(client, db_session, project_root) -> None:
    load_catalog(db_session, project_root / "gard-catalog" / "normalization")
    issued = issue_token(
        session=db_session,
        name="lc",
        subject="user:lc",
        roles=[Role.lifecycle_manager],
        created_by="test",
    )
    db_session.commit()
    headers = {"Authorization": f"Bearer {issued.jwt}"}

    first = csv_body([csv_row(observed_firmware="17.09.04a")])
    second = csv_body([csv_row(observed_firmware="17.12.01b")])

    r1 = client.post(
        "/api/v1/imports/devices/csv",
        files={"file": ("first.csv", first, "text/csv")},
        headers=headers,
    )
    assert r1.status_code == 200
    r2 = client.post(
        "/api/v1/imports/devices/csv",
        files={"file": ("second.csv", second, "text/csv")},
        headers=headers,
    )
    assert r2.status_code == 200

    devices = db_session.scalars(select(Device)).all()
    assert len(devices) == 1
    obs = db_session.scalars(
        select(DeviceObservation).order_by(DeviceObservation.created_at.asc())
    ).all()
    assert len(obs) == 2
    firmwares = [o.observed_firmware for o in obs]
    assert firmwares == ["17.09.04a", "17.12.01b"]
