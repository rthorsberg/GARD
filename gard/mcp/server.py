"""GARD MCP Streamable HTTP server (F8)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import anyio
import mcp.types as types
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.server import StreamableHTTPASGIApp
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.types import ASGIApp

from gard.core.settings import Settings, get_settings
from gard.mcp.handler import (
    DISALLOWED_TOOLS,
    McpHandlerError,
    McpPermissionDenied,
    McpToolNotFound,
    McpValidationFailed,
    invoke_tool,
)
from gard.mcp.middleware import wrap_mcp_app
from gard.mcp.registry import TOOL_REGISTRY


def _tool_description(name: str) -> str:
    if name in DISALLOWED_TOOLS:
        return "Disallowed — rejected per Constitution VI"
    return f"GARD curated lifecycle tool: {name}"


def _build_lowlevel_server() -> Server:
    server = Server("gard-mcp")

    @server.list_tools()  # type: ignore[no-untyped-call]
    async def handle_list_tools() -> list[types.Tool]:
        tools: list[types.Tool] = []
        for entry in TOOL_REGISTRY.values():
            tools.append(
                types.Tool(
                    name=entry.name,
                    description=_tool_description(entry.name),
                    inputSchema=entry.input_model.model_json_schema(),
                )
            )
        for denied in sorted(DISALLOWED_TOOLS):
            tools.append(
                types.Tool(
                    name=denied,
                    description=_tool_description(denied),
                    inputSchema={"type": "object", "additionalProperties": False},
                )
            )
        return tools

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            try:
                return invoke_tool(name, arguments or {})
            except McpToolNotFound as exc:
                raise ToolError(str(exc)) from exc
            except McpPermissionDenied as exc:
                raise ToolError(str(exc)) from exc
            except McpValidationFailed as exc:
                raise ToolError(str(exc)) from exc
            except McpHandlerError as exc:
                raise ToolError(str(exc)) from exc

        return await anyio.to_thread.run_sync(_run)

    return server


def create_session_manager() -> StreamableHTTPSessionManager:
    """One session manager per FastAPI app instance (not process-global)."""
    return StreamableHTTPSessionManager(
        app=_build_lowlevel_server(),
        json_response=True,
        stateless=True,
    )


@asynccontextmanager
async def mcp_runtime(session_manager: StreamableHTTPSessionManager) -> AsyncIterator[None]:
    """Start the Streamable HTTP session manager task group."""
    async with session_manager.run():
        yield


def create_mcp_asgi_app(session_manager: StreamableHTTPSessionManager) -> ASGIApp:
    """Return the authenticated MCP ASGI app (for mounting under FastAPI)."""
    handler = StreamableHTTPASGIApp(session_manager)
    return wrap_mcp_app(handler)


def run_mcp(settings: Settings | None = None) -> int:  # pragma: no cover
    """CLI entry: run API + MCP via uvicorn (shared ``create_app``)."""
    import uvicorn

    s = settings or get_settings()
    uvicorn.run(
        "gard.api.app:app",
        host=s.api_host,
        port=s.api_port,
        log_level=s.log_level.lower(),
    )
    return 0
