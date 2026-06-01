"""F8 US4 — list tools respect pagination bounds at max limit."""

from __future__ import annotations

import pytest

from gard.core.tokens import issue_token
from gard.models._enums import Role
from tests.integration._mcp_helpers import mcp_call_tool
from tests.integration._mvp_isr1121_helpers import import_isr1121_fixture

pytestmark = pytest.mark.integration


async def test_firmware_packages_pagination_at_small_limit(
    client, db_session, project_root
) -> None:
    import_isr1121_fixture(client, db_session, project_root)
    issued = issue_token(
        session=db_session,
        name="mcp-bounds",
        subject="agent:bounds",
        roles=[Role.mcp_client],
        created_by="test",
    )
    db_session.commit()

    page = await mcp_call_tool(
        client.app,
        jwt=issued.jwt,
        tool_name="list_firmware_packages",
        arguments={"limit": 1},
    )
    assert page["total_returned"] == 1
    assert page["next_page_token"]

    follow = await mcp_call_tool(
        client.app,
        jwt=issued.jwt,
        tool_name="list_firmware_packages",
        arguments={"limit": 1, "page_token": page["next_page_token"]},
    )
    assert follow["total_returned"] == 1
    assert page["items"][0]["id"] != follow["items"][0]["id"]

    max_page = await mcp_call_tool(
        client.app,
        jwt=issued.jwt,
        tool_name="list_firmware_packages",
        arguments={"limit": 500},
    )
    assert max_page["total_returned"] <= 500
