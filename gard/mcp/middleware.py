"""ASGI middleware for MCP Streamable HTTP auth."""

from __future__ import annotations

import json
from typing import cast

from starlette.types import ASGIApp, Receive, Scope, Send

from gard.core.logging import get_logger
from gard.core.settings import get_settings
from gard.core.tokens import InvalidTokenError, verify_token
from gard.db.session import session_scope
from gard.mcp.context import mcp_principal_scope

_log = get_logger(__name__)


def _auth_header(scope: Scope) -> str | None:
    headers = dict(scope.get("headers", []))
    raw = headers.get(b"authorization")
    if raw is None:
        return None
    text = raw.decode("latin-1")
    bearer, _, cred = text.partition(" ")
    if bearer.lower() != "bearer" or not cred:
        return None
    return cast(str, cred.strip())


class McpAuthMiddleware:
    """Validate bearer JWT before MCP session handling."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        token = _auth_header(scope)
        if not token:
            await _json_error(send, 401, "missing Authorization header")
            return

        settings = get_settings()
        try:
            with session_scope() as session:
                principal = verify_token(session=session, token=token, settings=settings)
                session.commit()
        except InvalidTokenError as exc:
            _log.info("auth.denied", reason=str(exc), surface="mcp")
            await _json_error(send, 401, f"invalid token: {exc}")
            return

        with mcp_principal_scope(principal):
            await self.app(scope, receive, send)


async def _json_error(send: Send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": body})


def wrap_mcp_app(app: ASGIApp) -> ASGIApp:
    """Correlation id (outer) + MCP auth (inner)."""
    from gard.api.middleware.correlation_id import CorrelationIdMiddleware

    return CorrelationIdMiddleware(McpAuthMiddleware(app))
