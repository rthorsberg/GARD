"""F8 US4 — disallowed MCP tools rejected with audit."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from gard.core.tokens import issue_token
from gard.models import AuditEvent
from gard.models._enums import Role
from tests.integration._mcp_helpers import McpToolCallError, mcp_call_tool
from tests.integration._mvp_isr1121_helpers import import_isr1121_fixture

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("tool_name", ["execute_sql", "run_shell"])
async def test_disallowed_tool_rejected(client, db_session, project_root, tool_name: str) -> None:
    import_isr1121_fixture(client, db_session, project_root)
    issued = issue_token(
        session=db_session,
        name="mcp-deny",
        subject="agent:bad",
        roles=[Role.mcp_client],
        created_by="test",
    )
    db_session.commit()
    with pytest.raises(McpToolCallError, match="tool not found"):
        await mcp_call_tool(client.app, jwt=issued.jwt, tool_name=tool_name, arguments={})

    db_session.expire_all()
    audit = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "mcp.disallowed_tool_attempt")
        .order_by(AuditEvent.timestamp.desc())
        .limit(1)
    )
    assert audit is not None
    assert audit.object_id == tool_name
