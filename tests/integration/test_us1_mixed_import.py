"""US1 AS2 — mixed CSV: some rejected, some manual_review, downloadable report."""

from __future__ import annotations

import pytest

from gard.catalog.normalization_loader import load_catalog
from gard.core.tokens import issue_token
from gard.models._enums import Role
from tests.integration._csv_helpers import csv_body, csv_row

pytestmark = pytest.mark.integration


def test_mixed_import(client, db_session, project_root) -> None:
    load_catalog(db_session, project_root / "gard-catalog" / "normalization")
    issued = issue_token(
        session=db_session,
        name="lc",
        subject="user:lc",
        roles=[Role.lifecycle_manager],
        created_by="test",
    )
    db_session.commit()

    rows = []
    # 5 valid Cisco rows
    for i in range(5):
        rows.append(csv_row(hostname=f"r-osl-{i}", serial_number=f"FCW1{i:06d}"))
    # 3 unknown vendor → manual_review
    for i in range(3):
        rows.append(
            csv_row(
                hostname=f"unknown-{i}",
                serial_number=f"UNK{i:06d}",
                vendor_raw="WeirdCorp",
                model_raw="X-9000",
                observed_firmware="ZZZ.42",
            )
        )
    # 2 invalid (missing identity)
    rows.append(
        csv_row(
            hostname="",  # required → invalid
            serial_number="",
            vendor_raw="Cisco Systems",
            model_raw="ISR1121",
            observed_firmware="17.09.04a",
        )
    )
    # 1 future observed_at
    rows.append(
        csv_row(
            hostname="future-1",
            serial_number="FUT0000001",
            observed_at="2099-01-01T00:00:00Z",
        )
    )

    body = csv_body(rows)
    r = client.post(
        "/api/v1/imports/devices/csv",
        files={"file": ("mixed.csv", body, "text/csv")},
        headers={"Authorization": f"Bearer {issued.jwt}"},
    )
    assert r.status_code == 200, r.text
    summary = r.json()
    totals = summary["totals"]
    assert totals["rows_total"] == 10
    assert totals["rows_accepted"] == 5
    assert totals["rows_manual_review"] == 3
    assert totals["rows_rejected"] == 2

    # Report endpoint returns the row errors
    job_id = summary["job_id"]
    rep = client.get(
        f"/api/v1/imports/jobs/{job_id}/report",
        headers={"Authorization": f"Bearer {issued.jwt}"},
    )
    assert rep.status_code == 200
    rep_body = rep.json()
    codes = {e["code"] for e in rep_body["row_errors"]}
    assert "ROW_OBSERVED_AT_FUTURE" in codes
    assert any(c.startswith("ROW_") for c in codes)
