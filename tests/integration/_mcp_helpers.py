"""Helpers for live MCP transport integration tests."""

from __future__ import annotations

from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from starlette.types import ASGIApp


class McpToolCallError(RuntimeError):
    """Raised when the MCP server rejects a tool invocation."""


async def mcp_call_tool(
    app: ASGIApp,
    *,
    jwt: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> Any:
    """Initialize an MCP session and call one tool."""
    pending_error: McpToolCallError | None = None
    payload: Any = None

    async with (
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {jwt}"},
        ) as http,
        streamable_http_client(
            "http://testserver/mcp/",
            http_client=http,
        ) as (read, write, _get_session_id),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool(tool_name, arguments or {})
        if result.isError:
            pending_error = McpToolCallError(str(result.content))
        elif result.structuredContent is not None:
            payload = result.structuredContent
        else:
            payload = result.content

    if pending_error is not None:
        raise pending_error
    return payload


async def mcp_list_tools(app: ASGIApp, *, jwt: str) -> list[str]:
    async with (
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {jwt}"},
        ) as http,
        streamable_http_client(
            "http://testserver/mcp/",
            http_client=http,
        ) as (read, write, _get_session_id),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        tools = await session.list_tools()
        return [t.name for t in tools.tools]
