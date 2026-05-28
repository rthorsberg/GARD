"""Regression — Device envelope confidence reflects the latest observation,
not a hard-coded heuristic, and reasons reference the matching rule id."""

from __future__ import annotations

import pytest

from gard.catalog.normalization_loader import load_catalog
from gard.core.tokens import issue_token
from gard.models._enums import Role
from tests.integration._csv_helpers import csv_body, csv_row

pytestmark = pytest.mark.integration


def test_envelope_confidence_from_observation(client, db_session, project_root) -> None:
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
    client.post(
        "/api/v1/imports/devices/csv",
        files={"file": ("a.csv", body, "text/csv")},
        headers=headers,
    )

    r = client.get("/api/v1/devices", headers=headers)
    assert r.status_code == 200
    item = r.json()["items"][0]

    # The seed cisco-ios rule has confidence: high → 0.85.
    assert item["envelope"]["confidence"] == pytest.approx(0.85)

    # The reasons list cites the rule id (cisco-ios), not a generic label.
    reasons = item["envelope"]["reasons"]
    assert reasons, "envelope must carry reasons"
    assert any(r["kind"] == "rule_match" for r in reasons)
    assert any("cisco-ios" in (r.get("ref") or "") for r in reasons)
