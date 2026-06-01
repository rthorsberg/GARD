"""F8 US5 — MCP disabled via settings."""

from __future__ import annotations

from fastapi.testclient import TestClient

from gard.core.settings import reset_settings_cache


def test_mcp_disabled_returns_404(monkeypatch) -> None:
    monkeypatch.setenv("GARD_MCP_ENABLED", "false")
    reset_settings_cache()
    from gard.api.app import create_app

    app = create_app()
    with TestClient(app) as c:
        resp = c.post("/mcp")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "MCP disabled"
    reset_settings_cache()
