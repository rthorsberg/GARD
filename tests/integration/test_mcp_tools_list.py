"""F8 US1 — tools/list exposes all 22 registered tools."""

from __future__ import annotations

import pytest

from gard.core.tokens import issue_token
from gard.models._enums import Role
from tests.integration._mcp_helpers import mcp_list_tools
from tests.integration._mvp_isr1121_helpers import import_isr1121_fixture

pytestmark = pytest.mark.integration


async def test_tools_list_returns_22_tools(client, db_session, project_root) -> None:
    import_isr1121_fixture(client, db_session, project_root)
    issued = issue_token(
        session=db_session,
        name="mcp-list",
        subject="agent:list",
        roles=[Role.mcp_client],
        created_by="test",
    )
    db_session.commit()
    names = await mcp_list_tools(client.app, jwt=issued.jwt)
    published = {
        n
        for n in names
        if n
        not in {
            "execute_sql",
            "run_shell",
            "read_file",
            "write_file",
            "http_request",
            "propose_firmware_target_draft",
        }
    }
    assert len(published) == 22
