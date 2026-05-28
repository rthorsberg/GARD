"""Read-only lifecycle-evidence endpoint (T047)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.api.middleware.rbac import require
from gard.core.rbac import Permission, Principal
from gard.db.session import get_session
from gard.models import LifecycleEvidence

router = APIRouter(prefix="/api/v1/evidence", tags=["evidence"])


class EvidenceOut(BaseModel):
    id: uuid.UUID
    evidence_type: str
    subject_type: str
    subject_id: str
    actor: str
    system: str
    timestamp: dt.datetime
    source_checksum: str | None
    references: dict[str, Any] | None
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None


class EvidencePage(BaseModel):
    items: list[EvidenceOut]
    total_returned: int = Field(ge=0)


@router.get("", response_model=EvidencePage)
def list_evidence(
    _: Principal = Depends(require(Permission.READ_EVIDENCE)),
    session: Session = Depends(get_session),
    subject_type: str | None = Query(default=None),
    subject_id: str | None = Query(default=None),
    evidence_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> EvidencePage:
    stmt = select(LifecycleEvidence).order_by(LifecycleEvidence.timestamp.desc()).limit(limit)
    if subject_type:
        stmt = stmt.where(LifecycleEvidence.subject_type == subject_type)
    if subject_id:
        stmt = stmt.where(LifecycleEvidence.subject_id == subject_id)
    if evidence_type:
        stmt = stmt.where(LifecycleEvidence.evidence_type == evidence_type)
    rows = session.scalars(stmt).all()
    items = [
        EvidenceOut(
            id=r.id,
            evidence_type=r.evidence_type.value,
            subject_type=r.subject_type,
            subject_id=r.subject_id,
            actor=r.actor,
            system=r.system,
            timestamp=r.timestamp,
            source_checksum=r.source_checksum,
            references=r.references,
            before_state=r.before_state,
            after_state=r.after_state,
        )
        for r in rows
    ]
    return EvidencePage(items=items, total_returned=len(items))
