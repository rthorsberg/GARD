"""F8 US3 — get_target_firmware MCP vs REST byte parity."""

from __future__ import annotations

import pytest

from gard.core.tokens import issue_token
from gard.models._enums import Role
from tests.integration._mcp_helpers import mcp_call_tool
from tests.integration._mvp_isr1121_helpers import (
    GOLDEN_HOSTNAME,
    bootstrap_mvp_estate,
    device_by_hostname,
)

pytestmark = pytest.mark.integration


def _strip_correlation(payload: dict) -> dict:
    out = dict(payload)
    out.pop("correlation_id", None)
    out.pop("as_of", None)
    return out


async def test_get_target_firmware_matches_rest(client, db_session, project_root) -> None:
    bootstrap_mvp_estate(client, db_session, project_root, with_uplift=False)
    golden = device_by_hostname(db_session, GOLDEN_HOSTNAME)
    issued = issue_token(
        session=db_session,
        name="mcp-fw",
        subject="agent:fw",
        roles=[Role.mcp_client],
        created_by="test",
    )
    db_session.commit()
    headers = {"Authorization": f"Bearer {issued.jwt}"}

    rest = client.get(
        f"/api/v1/devices/{golden.id}/firmware-compliance",
        headers=headers,
    )
    assert rest.status_code == 200, rest.text

    mcp = await mcp_call_tool(
        client.app,
        jwt=issued.jwt,
        tool_name="get_target_firmware",
        arguments={"device_id": str(golden.id)},
    )
    assert _strip_correlation(mcp) == _strip_correlation(rest.json())
