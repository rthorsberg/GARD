"""T061 — GET /devices/{id} returns DeviceWithEnvelope; 404 for unknown id."""

from __future__ import annotations

import uuid

import pytest

from gard.catalog.normalization_loader import load_catalog
from gard.core.tokens import issue_token
from gard.models._enums import Role
from tests.integration._csv_helpers import csv_body, csv_row

pytestmark = pytest.mark.contract


def _seed(client, db_session, project_root):
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
    body = csv_body([csv_row()])
    client.post(
        "/api/v1/imports/devices/csv",
        files={"file": ("a.csv", body, "text/csv")},
        headers=headers,
    )
    return headers


def test_get_device_404(client, db_session, project_root) -> None:
    headers = _seed(client, db_session, project_root)
    r = client.get(f"/api/v1/devices/{uuid.uuid4()}", headers=headers)
    assert r.status_code == 404


def test_get_device_envelope(client, db_session, project_root) -> None:
    headers = _seed(client, db_session, project_root)
    r_list = client.get("/api/v1/devices", headers=headers)
    device_id = r_list.json()["items"][0]["facts"]["id"]
    r = client.get(f"/api/v1/devices/{device_id}", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["facts"]["id"] == device_id
    assert "envelope" in body
    assert body["envelope"]["correlation_id"]
