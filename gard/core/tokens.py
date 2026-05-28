"""Stub: real token issuance lives in Phase 2 (T032 issue_token service)."""

from __future__ import annotations


def issue_token_cli(subject: str, role: str, ttl_seconds: int | None) -> int:  # pragma: no cover
    raise NotImplementedError("gard.core.tokens.issue_token_cli is wired up in Phase 2")
