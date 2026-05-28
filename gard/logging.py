"""Spec-conforming alias for :mod:`gard.core.logging` (tasks.md T006)."""

from gard.core.logging import (
    configure_logging,
    correlation_id_scope,
    get_correlation_id,
    get_logger,
    new_correlation_id,
    set_correlation_id,
)

__all__ = [
    "configure_logging",
    "correlation_id_scope",
    "get_correlation_id",
    "get_logger",
    "new_correlation_id",
    "set_correlation_id",
]
