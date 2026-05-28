"""T057 — duplicate file: 409 + override=true → 200 + audit rows."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from gard.catalog.normalization_loader import load_catalog
from gard.core.tokens import issue_token
from gard.models import AuditEvent
from gard.models._enums import Role
from tests.integration._csv_helpers import csv_body, csv_row

pytestmark = pytest.mark.contract


def test_duplicate_then_override_audit_records(client, db_session, project_root) -> None:
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

    r1 = client.post(
        "/api/v1/imports/devices/csv",
        files={"file": ("a.csv", body, "text/csv")},
        headers=headers,
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/api/v1/imports/devices/csv",
        files={"file": ("a.csv", body, "text/csv")},
        headers=headers,
    )
    assert r2.status_code == 409

    r3 = client.post(
        "/api/v1/imports/devices/csv?override=true",
        files={"file": ("a.csv", body, "text/csv")},
        headers=headers,
    )
    assert r3.status_code == 200

    actions = {a.action for a in db_session.scalars(select(AuditEvent)).all()}
    assert any("import" in a for a in actions)
