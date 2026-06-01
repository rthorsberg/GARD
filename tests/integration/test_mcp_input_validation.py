"""F8 US2 — invalid MCP tool input rejected without side effects."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from gard.core.tokens import issue_token
from gard.models import AuditEvent, ComplianceEvaluation, ReadinessEvaluation
from gard.models._enums import Role
from tests.integration._mcp_helpers import McpToolCallError, mcp_call_tool
from tests.integration._mvp_isr1121_helpers import bootstrap_mvp_estate

pytestmark = pytest.mark.integration


async def test_invalid_tool_input_no_audit_or_eval_rows(client, db_session, project_root) -> None:
    bootstrap_mvp_estate(client, db_session, project_root, with_uplift=False)
    issued = issue_token(
        session=db_session,
        name="mcp-validate",
        subject="agent:validate",
        roles=[Role.mcp_client],
        created_by="test",
    )
    db_session.commit()

    audit_before = db_session.scalar(select(func.count()).select_from(AuditEvent)) or 0
    comp_before = db_session.scalar(select(func.count()).select_from(ComplianceEvaluation)) or 0
    ready_before = db_session.scalar(select(func.count()).select_from(ReadinessEvaluation)) or 0

    with pytest.raises(McpToolCallError, match=r"validation|type|required|invalid"):
        await mcp_call_tool(
            client.app,
            jwt=issued.jwt,
            tool_name="get_target_firmware",
            arguments={"device_id": "not-a-uuid"},
        )

    audit_after = db_session.scalar(select(func.count()).select_from(AuditEvent)) or 0
    comp_after = db_session.scalar(select(func.count()).select_from(ComplianceEvaluation)) or 0
    ready_after = db_session.scalar(select(func.count()).select_from(ReadinessEvaluation)) or 0

    assert audit_after == audit_before
    assert comp_after == comp_before
    assert ready_after == ready_before
