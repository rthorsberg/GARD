"""Regression — ImportSummary totals satisfy
`total = accepted + rejected + manual_review + duplicate`
even when in-file duplicates exist."""

from __future__ import annotations

import pytest

from gard.catalog.normalization_loader import load_catalog
from gard.core.tokens import issue_token
from gard.models._enums import Role
from tests.integration._csv_helpers import csv_body, csv_row

pytestmark = pytest.mark.integration


def test_total_equation_with_duplicates(client, db_session, project_root) -> None:
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
        csv_row(hostname="r1", serial_number="DUP000001"),  # accepted
        csv_row(hostname="r1", serial_number="DUP000001"),  # in-file duplicate
        csv_row(hostname="r2", serial_number="DUP000002"),  # accepted
        csv_row(
            hostname="weird",
            serial_number="WEIRD0001",
            vendor_raw="WeirdCorp",
            model_raw="X9",
            observed_firmware="ZZZ",
        ),  # manual_review
        csv_row(
            hostname="",
            serial_number="",
            vendor_raw="Cisco Systems",
            model_raw="ISR1121",
            observed_firmware="17.09.04a",
        ),  # rejected (missing identity)
    ]
    body = csv_body(rows)
    r = client.post(
        "/api/v1/imports/devices/csv",
        files={"file": ("dup.csv", body, "text/csv")},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    t = r.json()["totals"]
    assert t["rows_total"] == 5
    assert t["rows_accepted"] == 2
    assert t["rows_manual_review"] == 1
    assert t["rows_rejected"] == 1
    assert t["rows_duplicate"] == 1
    assert (
        t["rows_accepted"] + t["rows_rejected"] + t["rows_manual_review"] + t["rows_duplicate"]
        == t["rows_total"]
    )
