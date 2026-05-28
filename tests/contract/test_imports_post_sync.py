"""T055 — POST /imports/devices/csv (sync) returns ImportSummary shape."""

from __future__ import annotations

import pytest

from gard.catalog.normalization_loader import load_catalog
from gard.core.tokens import issue_token
from gard.models._enums import Role
from tests.integration._csv_helpers import csv_body, csv_row

pytestmark = pytest.mark.contract


def test_sync_import_summary_shape(client, db_session, project_root) -> None:
    load_catalog(db_session, project_root / "gard-catalog" / "normalization")
    issued = issue_token(
        session=db_session,
        name="lc",
        subject="user:lc",
        roles=[Role.lifecycle_manager],
        created_by="test",
    )
    db_session.commit()

    body = csv_body([csv_row()])
    r = client.post(
        "/api/v1/imports/devices/csv",
        files={"file": ("a.csv", body, "text/csv")},
        headers={"Authorization": f"Bearer {issued.jwt}"},
    )
    assert r.status_code == 200, r.text
    payload = r.json()

    expected_keys = {
        "job_id",
        "status",
        "totals",
        "correlation_id",
        "warnings",
        "csv_schema_version",
    }
    assert expected_keys.issubset(payload.keys())
    assert payload["status"] in {"completed", "failed"}

    totals = payload["totals"]
    expected_totals = {
        "rows_total",
        "rows_accepted",
        "rows_rejected",
        "rows_manual_review",
        "rows_duplicate",
        "devices_created",
        "devices_updated",
    }
    assert expected_totals.issubset(totals.keys())
    assert totals["rows_total"] == 1
    assert totals["rows_total"] == (
        totals["rows_accepted"]
        + totals["rows_rejected"]
        + totals["rows_manual_review"]
        + totals["rows_duplicate"]
    )
