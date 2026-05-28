"""Explainable response envelope (ADR-0005)."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field

from gard.core.logging import get_correlation_id
from gard.models import utcnow

EnvelopeState = Literal["known", "unknown", "conflicting", "stale", "classified", "imported"]
ReasonKind = Literal[
    "rule_match",
    "manual_mapping",
    "evidence_ref",
    "missing_input",
    "rule_conflict",
    "stale_observation",
    "policy_decision",
]


class Reason(BaseModel):
    kind: ReasonKind
    ref: str | None = None
    detail: str = ""


class ResponseEnvelope[T](BaseModel):
    state: EnvelopeState
    summary: str
    facts: T
    reasons: list[Reason] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    as_of: dt.datetime
    correlation_id: str | None = None


_CONFIDENCE_FROM_LEVEL: dict[str, float] = {
    "exact": 1.0,
    "high": 0.85,
    "medium": 0.6,
    "low": 0.3,
    "manual_review_required": 0.0,
}


def confidence_from_level(level: str) -> float:
    """Map the qualitative confidence enum to a numeric score (ADR-0005)."""
    return _CONFIDENCE_FROM_LEVEL.get(level, 0.0)


def build_envelope(
    *,
    state: EnvelopeState,
    summary: str,
    facts: Any,
    reasons: list[Reason] | None = None,
    recommended_actions: list[str] | None = None,
    confidence: float = 0.0,
    as_of: dt.datetime | None = None,
    correlation_id: str | None = None,
) -> ResponseEnvelope[Any]:
    """Construct a :class:`ResponseEnvelope` from positional inputs."""
    return ResponseEnvelope[Any](
        state=state,
        summary=summary,
        facts=facts,
        reasons=reasons or [],
        recommended_actions=recommended_actions or [],
        confidence=confidence,
        as_of=as_of or utcnow(),
        correlation_id=correlation_id or get_correlation_id(),
    )
