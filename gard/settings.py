"""Spec-conforming alias for :mod:`gard.core.settings`.

The implementation lives in :mod:`gard.core.settings`; this module is the
public import path documented in `tasks.md` T005. Re-exporting (rather
than moving) keeps ``gard.core.*`` cohesive while honouring the spec.
"""

from gard.core.settings import (
    DEFAULT_API_TOKEN_TTL_SECONDS,
    Settings,
    get_settings,
    reset_settings_cache,
)

__all__ = [
    "DEFAULT_API_TOKEN_TTL_SECONDS",
    "Settings",
    "get_settings",
    "reset_settings_cache",
]
