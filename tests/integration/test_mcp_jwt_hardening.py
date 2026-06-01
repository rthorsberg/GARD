"""F8 US2 — malformed/expired JWT rejected at MCP middleware (401)."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import func, select

from gard.core.tokens import issue_token
from gard.models import AuditEvent
from gard.models._enums import Role
from tests.integration._mvp_isr1121_helpers import import_isr1121_fixture

pytestmark = pytest.mark.integration


async def test_expired_jwt_returns_401(client, db_session, project_root) -> None:
    import asyncio

    import_isr1121_fixture(client, db_session, project_root)
    issued = issue_token(
        session=db_session,
        name="mcp-expired",
        subject="agent:expired",
        roles=[Role.mcp_client],
        created_by="test",
        ttl_seconds=60,
    )
    db_session.commit()

    audit_before = db_session.scalar(select(func.count()).select_from(AuditEvent)) or 0
    await asyncio.sleep(61)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=client.app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {issued.jwt}"},
    ) as http:
        resp = await http.post("/mcp/")
        assert resp.status_code == 401

    audit_after = db_session.scalar(select(func.count()).select_from(AuditEvent)) or 0
    assert audit_after == audit_before


async def test_malformed_jwt_returns_401(client, db_session, project_root) -> None:
    import_isr1121_fixture(client, db_session, project_root)
    db_session.commit()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=client.app),
        base_url="http://testserver",
        headers={"Authorization": "Bearer not-a-valid-jwt"},
    ) as http:
        resp = await http.post("/mcp/")
        assert resp.status_code == 401
