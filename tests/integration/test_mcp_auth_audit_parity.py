"""F8 US2 — MCP vs REST readiness summary payload and audit semantics."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from gard.core.tokens import issue_token
from gard.models import AuditEvent
from gard.models._enums import Role
from tests.integration._mcp_helpers import mcp_call_tool
from tests.integration._mvp_isr1121_helpers import PLATFORM_FAMILY, bootstrap_mvp_estate

pytestmark = pytest.mark.integration


def _summary_body(payload: dict) -> dict:
    out = dict(payload)
    out.pop("correlation_id", None)
    out.pop("as_of", None)
    return out


async def test_readiness_summary_mcp_matches_rest(client, db_session, project_root) -> None:
    bootstrap_mvp_estate(client, db_session, project_root, with_uplift=False)
    issued = issue_token(
        session=db_session,
        name="mcp-readiness",
        subject="agent:readiness",
        roles=[Role.mcp_client],
        created_by="test",
    )
    db_session.commit()
    headers = {"Authorization": f"Bearer {issued.jwt}"}
    filters = {"vendor_normalized": "cisco", "platform_family": PLATFORM_FAMILY}

    before_mcp = db_session.scalar(select(func.count()).select_from(AuditEvent)) or 0
    mcp = await mcp_call_tool(
        client.app,
        jwt=issued.jwt,
        tool_name="get_readiness_summary",
        arguments=filters,
    )
    after_mcp = db_session.scalar(select(func.count()).select_from(AuditEvent)) or 0

    rest = client.get("/api/v1/readiness/summary", params=filters, headers=headers)
    assert rest.status_code == 200, rest.text
    assert _summary_body(mcp) == _summary_body(rest.json())

    assert after_mcp == before_mcp + 1
    audit = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "mcp.tool.invoked")
        .order_by(AuditEvent.timestamp.desc())
        .limit(1)
    )
    assert audit is not None
    assert audit.result == "success"
    assert audit.object_id == "get_readiness_summary"
    assert audit.after is not None
    assert audit.after.get("records_returned", 0) >= 1
