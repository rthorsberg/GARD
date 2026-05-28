"""US1 edge case — identical-hash re-upload: 409 + override=true → 200, is_override recorded."""

from __future__ import annotations

import pytest

from gard.catalog.normalization_loader import load_catalog
from gard.core.tokens import issue_token
from gard.models._enums import Role
from tests.integration._csv_helpers import csv_body, csv_row

pytestmark = pytest.mark.integration


def test_duplicate_file_then_override(client, db_session, project_root) -> None:
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
    headers = {"Authorization": f"Bearer {issued.jwt}"}

    r1 = client.post(
        "/api/v1/imports/devices/csv",
        files={"file": ("dup.csv", body, "text/csv")},
        headers=headers,
    )
    assert r1.status_code == 200, r1.text

    r2 = client.post(
        "/api/v1/imports/devices/csv",
        files={"file": ("dup.csv", body, "text/csv")},
        headers=headers,
    )
    assert r2.status_code == 409

    r3 = client.post(
        "/api/v1/imports/devices/csv?override=true",
        files={"file": ("dup.csv", body, "text/csv")},
        headers=headers,
    )
    assert r3.status_code == 200, r3.text

    job_id = r3.json()["job_id"]
    rj = client.get(f"/api/v1/imports/jobs/{job_id}", headers=headers)
    assert rj.status_code == 200
    assert rj.json()["is_override"] is True
