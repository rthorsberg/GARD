"""F8 US1 — live MCP transport MVP criterion #8."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from gard.core.tokens import issue_token
from gard.models import AuditEvent
from gard.models._enums import Role
from tests.integration._mcp_helpers import mcp_call_tool
from tests.integration._mvp_isr1121_helpers import (
    PLATFORM_FAMILY,
    bootstrap_mvp_estate,
    rest_outside_target_count,
)

pytestmark = pytest.mark.integration


def _mcp_token(session) -> str:
    issued = issue_token(
        session=session,
        name="mcp-isr1121",
        subject="agent:mcp-test",
        roles=[Role.mcp_client],
        created_by="test",
    )
    session.commit()
    return issued.jwt


async def test_count_devices_outside_target_mcp_matches_rest(
    client, db_session, project_root
) -> None:
    bootstrap_mvp_estate(client, db_session, project_root)
    jwt = _mcp_token(db_session)
    mcp_out = await mcp_call_tool(
        client.app,
        jwt=jwt,
        tool_name="count_devices_outside_target",
        arguments={
            "vendor_normalized": "cisco",
            "platform_family": PLATFORM_FAMILY,
        },
    )
    rest_count = rest_outside_target_count(db_session)
    assert mcp_out["count"] == rest_count

    audit = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "mcp.tool.invoked")
        .order_by(AuditEvent.timestamp.desc())
        .limit(1)
    )
    assert audit is not None
    assert audit.result == "success"
    assert mcp_out["correlation_id"] == audit.correlation_id
