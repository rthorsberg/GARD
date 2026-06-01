"""F8 US1 — viewer token denied on MCP tool invoke."""

from __future__ import annotations

import pytest

from gard.core.tokens import issue_token
from gard.models._enums import Role
from tests.integration._mcp_helpers import McpToolCallError, mcp_call_tool
from tests.integration._mvp_isr1121_helpers import import_isr1121_fixture

pytestmark = pytest.mark.integration


async def test_viewer_denied_on_mcp_tool(client, db_session, project_root) -> None:
    import_isr1121_fixture(client, db_session, project_root)
    issued = issue_token(
        session=db_session,
        name="viewer-only",
        subject="user:viewer",
        roles=[Role.viewer],
        created_by="test",
    )
    db_session.commit()
    with pytest.raises(McpToolCallError, match=r"permission|denied|tool not found"):
        await mcp_call_tool(
            client.app,
            jwt=issued.jwt,
            tool_name="count_devices_outside_target",
            arguments={},
        )
