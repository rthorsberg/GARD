"""US1 SC-007 — every completed import produces a lifecycle_evidence row with matching checksum."""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import select

from gard.catalog.normalization_loader import load_catalog
from gard.core.tokens import issue_token
from gard.models import LifecycleEvidence
from gard.models._enums import EvidenceType, Role
from tests.integration._csv_helpers import csv_body, csv_row

pytestmark = pytest.mark.integration


def test_evidence_emitted_on_import(client, db_session, project_root) -> None:
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
    sha = hashlib.sha256(body).hexdigest()

    r = client.post(
        "/api/v1/imports/devices/csv",
        files={"file": ("a.csv", body, "text/csv")},
        headers={"Authorization": f"Bearer {issued.jwt}"},
    )
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]

    rows = db_session.scalars(
        select(LifecycleEvidence)
        .where(LifecycleEvidence.subject_type == "ImportJob")
        .where(LifecycleEvidence.subject_id == job_id)
    ).all()
    assert len(rows) == 1
    ev = rows[0]
    assert ev.evidence_type == EvidenceType.import_event
    assert ev.source_checksum == sha
    assert ev.row_hash  # non-empty


def test_evidence_visible_via_api(client, db_session, project_root) -> None:
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
    client.post(
        "/api/v1/imports/devices/csv",
        files={"file": ("a.csv", body, "text/csv")},
        headers=headers,
    )

    r = client.get("/api/v1/evidence?subject_type=ImportJob", headers=headers)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["evidence_type"] == "import"
