"""Lifecycle evidence emission helper (ADR-0009)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy.orm import Session

from gard.core.hashing import row_hash
from gard.core.logging import get_logger
from gard.core.rbac import Principal
from gard.core.settings import get_settings
from gard.models import LifecycleEvidence, utcnow
from gard.models._enums import EvidenceType

_log = get_logger(__name__)


def emit(
    *,
    session: Session,
    evidence_type: EvidenceType,
    subject_type: str,
    subject_id: str,
    actor: str | None = None,
    principal: Principal | None = None,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    source_checksum: str | None = None,
    references: dict[str, Any] | None = None,
    timestamp: dt.datetime | None = None,
    system: str | None = None,
) -> LifecycleEvidence:
    """Persist a single :class:`LifecycleEvidence` row and return it.

    The caller commits the session. Evidence rows are append-only at the
    DB level — a leaked admin token can mint new rows, but it cannot
    mutate history.
    """
    resolved_actor = actor if actor is not None else (principal.subject if principal else "system")
    settings = get_settings()
    sys_ident = system if system is not None else f"{settings.service_name}@{settings.version}"
    ts = timestamp or utcnow()

    payload: dict[str, Any] = {
        "evidence_type": evidence_type.value,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "actor": resolved_actor,
        "system": sys_ident,
        "timestamp": ts,
        "before_state": before_state,
        "after_state": after_state,
        "source_checksum": source_checksum,
        "references": references,
    }
    h = row_hash(payload)

    row = LifecycleEvidence(
        evidence_type=evidence_type,
        subject_type=subject_type,
        subject_id=subject_id,
        actor=resolved_actor,
        system=sys_ident,
        timestamp=ts,
        before_state=before_state,
        after_state=after_state,
        source_checksum=source_checksum,
        references=references,
        row_hash=h,
    )
    session.add(row)
    session.flush()
    _log.info(
        "evidence.emit",
        evidence_type=evidence_type.value,
        subject_type=subject_type,
        subject_id=subject_id,
    )
    return row
