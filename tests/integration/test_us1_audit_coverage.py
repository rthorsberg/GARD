"""US1 SC-006 — every state-changing import action appears in audit_events with correct correlation_id."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from gard.catalog.normalization_loader import load_catalog
from gard.core.tokens import issue_token
from gard.models import AuditEvent
from gard.models._enums import Role
from tests.integration._csv_helpers import csv_body, csv_row

pytestmark = pytest.mark.integration


def test_audit_correlation_matches_response(client, db_session, project_root) -> None:
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
    cid = "audit-test-cid-001"
    r = client.post(
        "/api/v1/imports/devices/csv",
        files={"file": ("a.csv", body, "text/csv")},
        headers={"Authorization": f"Bearer {issued.jwt}", "X-Correlation-Id": cid},
    )
    assert r.status_code == 200
    assert r.headers.get("x-correlation-id") == cid

    rows = db_session.scalars(select(AuditEvent).where(AuditEvent.correlation_id == cid)).all()
    actions = {row.action for row in rows}
    assert "import.csv.accepted" in actions or "import.job.completed" in actions
    for row in rows:
        assert row.actor == "user:lc"
        assert row.actor_type.value == "user"
