"""Structured logging configuration.

Every log record carries a `correlation_id` (a UUID7) and the
`service_name`/`env` so downstream tooling can pivot on either.

The correlation id is propagated via a contextvar; the API and MCP
middleware are responsible for setting it once per request.
"""

from __future__ import annotations

import contextvars
import logging
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import structlog

_correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "gard_correlation_id", default=None
)


def get_correlation_id() -> str | None:
    return _correlation_id_var.get()


def set_correlation_id(value: str | None) -> contextvars.Token[str | None]:
    return _correlation_id_var.set(value)


def new_correlation_id() -> str:
    """Generate a new correlation id (UUID4 — UUID7 is reserved for entity ids)."""
    return str(uuid.uuid4())


@contextmanager
def correlation_id_scope(value: str | None = None) -> Iterator[str]:
    """Bind a correlation id for the duration of the block."""
    cid = value or new_correlation_id()
    token = set_correlation_id(cid)
    try:
        yield cid
    finally:
        _correlation_id_var.reset(token)


def _add_correlation_id(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    cid = _correlation_id_var.get()
    if cid is not None:
        event_dict.setdefault("correlation_id", cid)
    return event_dict


def configure_logging(level: str = "INFO", service_name: str = "gard", env: str = "dev") -> None:
    """Configure stdlib logging + structlog.

    Idempotent: safe to call from tests.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
        force=True,
    )

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_correlation_id,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(service_name=service_name, env=env)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
