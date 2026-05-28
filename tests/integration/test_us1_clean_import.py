"""US1 acceptance scenario AS1 — 100-row valid CSV → all classified."""

from __future__ import annotations

from pathlib import Path

import pytest

from gard.catalog.normalization_loader import load_catalog
from gard.core.tokens import issue_token
from gard.models._enums import Role
from tests.integration._csv_helpers import csv_body, csv_row

pytestmark = pytest.mark.integration


def _seed_catalog_and_token(db_session, project_root: Path):
    load_catalog(db_session, project_root / "gard-catalog" / "normalization")
    issued = issue_token(
        session=db_session,
        name="lifecycle",
        subject="user:lc",
        roles=[Role.lifecycle_manager],
        created_by="test",
    )
    db_session.commit()
    return issued.jwt


def test_clean_import_100_rows(client, db_session, project_root) -> None:
    jwt = _seed_catalog_and_token(db_session, project_root)

    rows = []
    for i in range(100):
        rows.append(
            csv_row(
                hostname=f"r-osl-{i:03d}",
                serial_number=f"FCW100000{i:03d}",
                management_ip=f"10.20.30.{i % 254 + 1}",
            )
        )
    body = csv_body(rows)

    r = client.post(
        "/api/v1/imports/devices/csv",
        files={"file": ("devices.csv", body, "text/csv")},
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert r.status_code == 200, r.text
    summary = r.json()
    totals = summary["totals"]
    assert totals["rows_total"] == 100
    assert totals["rows_accepted"] == 100
    assert totals["rows_rejected"] == 0
    assert totals["rows_manual_review"] == 0
    assert totals["devices_created"] == 100

    # Devices listable, every item has envelope, lifecycle_state=classified.
    r2 = client.get(
        "/api/v1/devices?limit=200",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert r2.status_code == 200, r2.text
    payload = r2.json()
    assert payload["total_returned"] == 100
    for item in payload["items"]:
        assert item["facts"]["lifecycle_state"] == "classified"
        assert item["facts"]["vendor_normalized"] == "cisco"
        assert item["envelope"]["state"] == "classified"
        assert item["envelope"]["confidence"] >= 0.6
