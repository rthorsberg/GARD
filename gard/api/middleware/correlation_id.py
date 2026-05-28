"""ASGI middleware that binds a per-request correlation id."""

from __future__ import annotations

from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from gard.core.logging import correlation_id_scope, new_correlation_id

CORRELATION_HEADER = b"x-correlation-id"


class CorrelationIdMiddleware:
    """Set / propagate a correlation id for every HTTP request.

    - If the inbound request carries ``X-Correlation-Id``, we honour it.
    - Otherwise we mint a new UUID4 and bind it on the contextvar.
    - The id is echoed in the response headers and is also bound for
      structured logging via :func:`gard.core.logging.correlation_id_scope`.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        incoming = headers.get(CORRELATION_HEADER)
        cid = incoming.decode("ascii") if incoming else new_correlation_id()

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                hdrs: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                hdrs.append((CORRELATION_HEADER, cid.encode("ascii")))
                new_msg: dict[str, Any] = dict(message)
                new_msg["headers"] = hdrs
                message = new_msg
            await send(message)

        with correlation_id_scope(cid):
            await self.app(scope, receive, send_with_header)


def correlation_id_factory() -> Any:  # pragma: no cover - thin alias for app factory
    return CorrelationIdMiddleware
