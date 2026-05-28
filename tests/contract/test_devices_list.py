"""T060 — GET /devices: filters work; pagination cap; envelope on every item."""

from __future__ import annotations

import pytest

from gard.catalog.normalization_loader import load_catalog
from gard.core.tokens import issue_token
from gard.models._enums import Role
from tests.integration._csv_helpers import csv_body, csv_row

pytestmark = pytest.mark.contract


def _seed_with_csv(client, db_session, project_root):
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

    rows = [
        csv_row(hostname=f"r-osl-{i}", serial_number=f"FCW{i:07d}", site="oslo", region="NO")
        for i in range(3)
    ]
    rows.extend(
        csv_row(
            hostname=f"r-sto-{i}",
            serial_number=f"JNP{i:07d}",
            site="sthlm",
            region="SE",
            vendor_raw="Juniper Networks",
            model_raw="MX204",
            observed_firmware="22.4R3",
        )
        for i in range(2)
    )
    body = csv_body(rows)
    r = client.post(
        "/api/v1/imports/devices/csv",
        files={"file": ("seed.csv", body, "text/csv")},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return headers


def test_list_returns_envelope_on_each_item(client, db_session, project_root) -> None:
    headers = _seed_with_csv(client, db_session, project_root)
    r = client.get("/api/v1/devices", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total_returned"] == 5
    for item in body["items"]:
        assert "facts" in item
        assert "envelope" in item
        assert "state" in item["envelope"]
        assert "confidence" in item["envelope"]


def test_list_filter_by_vendor(client, db_session, project_root) -> None:
    headers = _seed_with_csv(client, db_session, project_root)
    r = client.get("/api/v1/devices?vendor_normalized=cisco", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total_returned"] == 3
    for item in body["items"]:
        assert item["facts"]["vendor_normalized"] == "cisco"


def test_list_filter_by_site(client, db_session, project_root) -> None:
    headers = _seed_with_csv(client, db_session, project_root)
    r = client.get("/api/v1/devices?site=sthlm", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total_returned"] == 2
    for item in body["items"]:
        assert item["facts"]["site"] == "sthlm"


def test_list_limit_caps(client, db_session, project_root) -> None:
    headers = _seed_with_csv(client, db_session, project_root)
    r = client.get("/api/v1/devices?limit=2", headers=headers)
    assert r.status_code == 200
    assert r.json()["total_returned"] == 2
