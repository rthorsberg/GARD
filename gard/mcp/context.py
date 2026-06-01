"""Request-scoped MCP auth context (mirrors correlation-id pattern)."""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager

from gard.core.rbac import Principal

_principal_var: contextvars.ContextVar[Principal | None] = contextvars.ContextVar(
    "gard_mcp_principal", default=None
)


def get_mcp_principal() -> Principal | None:
    return _principal_var.get()


def set_mcp_principal(value: Principal | None) -> contextvars.Token[Principal | None]:
    return _principal_var.set(value)


@contextmanager
def mcp_principal_scope(principal: Principal) -> Iterator[Principal]:
    token = set_mcp_principal(principal)
    try:
        yield principal
    finally:
        _principal_var.reset(token)
