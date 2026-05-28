"""T058 — GET /imports/jobs/{id} returns ImportJob shape; 404 for unknown id."""

from __future__ import annotations

import uuid

import pytest

from gard.catalog.normalization_loader import load_catalog
from gard.core.tokens import issue_token
from gard.models._enums import Role
from tests.integration._csv_helpers import csv_body, csv_row

pytestmark = pytest.mark.contract


def _seed(db_session, project_root):
    load_catalog(db_session, project_root / "gard-catalog" / "normalization")
    issued = issue_token(
        session=db_session,
        name="lc",
        subject="user:lc",
        roles=[Role.lifecycle_manager],
        created_by="test",
    )
    db_session.commit()
    return {"Authorization": f"Bearer {issued.jwt}"}


def test_get_job_shape(client, db_session, project_root) -> None:
    headers = _seed(db_session, project_root)
    body = csv_body([csv_row()])
    r = client.post(
        "/api/v1/imports/devices/csv",
        files={"file": ("a.csv", body, "text/csv")},
        headers=headers,
    )
    job_id = r.json()["job_id"]

    rj = client.get(f"/api/v1/imports/jobs/{job_id}", headers=headers)
    assert rj.status_code == 200
    job = rj.json()
    expected = {
        "id",
        "filename",
        "file_sha256",
        "file_size",
        "status",
        "actor",
        "is_override",
        "created_at",
    }
    assert expected.issubset(job.keys())
    assert job["status"] in {"pending", "processing", "completed", "failed", "cancelled"}


def test_get_job_404(client, db_session, project_root) -> None:
    headers = _seed(db_session, project_root)
    bogus = str(uuid.uuid4())
    r = client.get(f"/api/v1/imports/jobs/{bogus}", headers=headers)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "http_404"
