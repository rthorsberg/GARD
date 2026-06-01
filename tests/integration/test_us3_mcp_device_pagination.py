"""F8 US3 — list_devices pagination via live MCP transport."""

from __future__ import annotations

import pytest

from gard.core.tokens import issue_token
from gard.models._enums import Role
from tests.integration._mcp_helpers import mcp_call_tool
from tests.integration._mvp_isr1121_helpers import import_isr1121_fixture

pytestmark = pytest.mark.integration


async def test_list_devices_pagination(client, db_session, project_root) -> None:
    import_isr1121_fixture(client, db_session, project_root)
    issued = issue_token(
        session=db_session,
        name="mcp-page",
        subject="agent:page",
        roles=[Role.mcp_client],
        created_by="test",
    )
    db_session.commit()

    first = await mcp_call_tool(
        client.app,
        jwt=issued.jwt,
        tool_name="list_devices",
        arguments={"vendor_normalized": "cisco", "limit": 1},
    )
    assert first["next_page_token"]
    assert len(first["items"]) == 1

    second = await mcp_call_tool(
        client.app,
        jwt=issued.jwt,
        tool_name="list_devices",
        arguments={
            "vendor_normalized": "cisco",
            "limit": 1,
            "page_token": first["next_page_token"],
        },
    )
    assert len(second["items"]) == 1
    assert first["items"][0]["facts"]["id"] != second["items"][0]["facts"]["id"]
