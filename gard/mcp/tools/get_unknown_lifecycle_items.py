"""MCP tool: get_unknown_lifecycle_items.

REST parity (close): ``GET /api/v1/compliance/devices?state=unknown``.
Adds the F2 reason kind that drove the unknown classification —
operators triage this list as the "needs manual classification" queue.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from gard.core import compliance_evaluation_controller as ctrl
from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission

TOOL_NAME = "get_unknown_lifecycle_items"
REQUIRED_PERMISSION = Permission.READ_COMPLIANCE


UnknownReasonKind = Literal[
    "missing_observation",
    "no_target_matched",
    "empty_catalog",
    "predicate_deferred",
]


class GetUnknownLifecycleItemsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=100, ge=1, le=500)


class UnknownItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: uuid.UUID
    hostname: str
    vendor_raw: str | None = None
    model_raw: str | None = None
    reason_kind: UnknownReasonKind
    reason_detail: str | None = None


class GetUnknownLifecycleItemsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[UnknownItem]
    total_returned: int = Field(ge=0)
    as_of: dt.datetime
    correlation_id: str


def _pick_reason(
    evaluation_reasons: list[dict[str, object]],
) -> tuple[UnknownReasonKind, str | None]:
    """Pick the F2 reason kind that justified the unknown classification.

    Falls back to ``missing_observation`` when no recognised kind is
    found (defensive; the controller normally always emits one).
    """
    priority: tuple[UnknownReasonKind, ...] = (
        "no_target_matched",
        "empty_catalog",
        "predicate_deferred",
        "missing_observation",
    )
    by_kind: dict[str, str | None] = {}
    for r in evaluation_reasons:
        kind = r.get("kind")
        detail = r.get("detail")
        if isinstance(kind, str):
            by_kind[kind] = detail if isinstance(detail, str) else None
    for k in priority:
        if k in by_kind:
            return k, by_kind[k]
    return "missing_observation", None


def invoke(
    *,
    session: Session,
    body: GetUnknownLifecycleItemsInput,
) -> GetUnknownLifecycleItemsOutput:
    rows = ctrl.fetch_device_list(session, state="unknown", limit=body.limit)
    items: list[UnknownItem] = []
    for d, e in rows:
        kind, detail = _pick_reason([dict(r) for r in (e.reasons or [])])
        items.append(
            UnknownItem(
                device_id=d.id,
                hostname=d.hostname,
                vendor_raw=getattr(d, "vendor_raw", None),
                model_raw=getattr(d, "model_raw", None),
                reason_kind=kind,
                reason_detail=detail,
            )
        )
    return GetUnknownLifecycleItemsOutput(
        items=items,
        total_returned=len(items),
        as_of=dt.datetime.now(dt.UTC),
        correlation_id=get_correlation_id() or "anonymous-correlation",
    )
