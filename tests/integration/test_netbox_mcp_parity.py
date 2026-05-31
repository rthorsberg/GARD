"""F7 US4 — MCP delegate parity with REST summary."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from gard.mcp.tools import get_netbox_sync_summary as mcp_summary
from tests.integration.test_netbox_sync import FakeNetboxClient, _nb_record, _token

pytestmark = pytest.mark.integration


def test_summary_parity(client, db_session) -> None:
    jwt = _token(db_session)
    fake = FakeNetboxClient([_nb_record()])
    with patch("gard.core.netbox_sync_controller.client_from_settings", return_value=fake):
        client.post(
            "/api/v1/integrations/netbox/sync",
            headers={"Authorization": f"Bearer {jwt}"},
        )

    rest = client.get(
        "/api/v1/integrations/netbox/summary",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert rest.status_code == 200, rest.text
    rest_data = rest.json()["data"]

    mcp_out = mcp_summary.invoke(
        session=db_session,
        body=mcp_summary.GetNetboxSyncSummaryInput(),
    )
    assert mcp_out.netbox_linked == rest_data["netbox_linked"]
    assert mcp_out.csv_only == rest_data["csv_only"]
    assert mcp_out.orphaned_in_gard == rest_data["orphaned_in_gard"]
    if rest_data["last_sync_at"] is None:
        assert mcp_out.last_sync_at is None
    else:
        assert mcp_out.last_sync_at is not None
