"""T054 — 401 without a token, 403 with insufficient permission, audit row written."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from gard.core.tokens import issue_token
from gard.models import AuditEvent
from gard.models._enums import Role

pytestmark = pytest.mark.integration


def test_no_token_returns_401(client) -> None:
    r = client.get("/api/v1/audit")
    assert r.status_code == 401
    body = r.json()
    assert body["error"]["correlation_id"]


def test_token_without_permission_returns_403_and_audits(client, db_session) -> None:
    issued = issue_token(
        session=db_session,
        name="mcp-only",
        subject="mcp:test",
        roles=[Role.mcp_client],
        created_by="test",
    )
    db_session.commit()

    r = client.get(
        "/api/v1/audit",  # requires READ_AUDIT, mcp_client doesn't have it
        headers={"Authorization": f"Bearer {issued.jwt}"},
    )
    assert r.status_code == 403, r.text

    # auth.denied audit row exists
    rows = db_session.scalars(select(AuditEvent).where(AuditEvent.action == "auth.denied")).all()
    assert len(rows) >= 1
    assert any(r.result.value == "denied" for r in rows)
    assert any(r.actor == "mcp:test" for r in rows)


def test_token_with_permission_returns_200(client, db_session) -> None:
    issued = issue_token(
        session=db_session,
        name="viewer",
        subject="user:viewer",
        roles=[Role.viewer],
        created_by="test",
    )
    db_session.commit()
    r = client.get("/api/v1/audit", headers={"Authorization": f"Bearer {issued.jwt}"})
    assert r.status_code == 200
    assert "items" in r.json()
