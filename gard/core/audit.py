"""Audit emission helper (ADR-0009).

Every state-changing action and every authorization denial calls
:func:`emit`. The helper writes through the append-only role
(see :func:`gard.db.session.append_only_scope`) so a SQL injection in
business code cannot rewrite history.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy.orm import Session

from gard.core.hashing import row_hash
from gard.core.logging import get_correlation_id, get_logger
from gard.core.rbac import Principal
from gard.models import AuditEvent, utcnow
from gard.models._enums import ActorType, AuditResult

_log = get_logger(__name__)


def emit(
    *,
    session: Session,
    action: str,
    object_type: str,
    object_id: str,
    result: AuditResult = AuditResult.success,
    principal: Principal | None = None,
    actor: str | None = None,
    actor_type: ActorType | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    source_ip: str | None = None,
    correlation_id: str | None = None,
    timestamp: dt.datetime | None = None,
) -> AuditEvent:
    """Persist a single :class:`AuditEvent` and return it.

    Caller is responsible for committing the session. The function
    accepts an explicit ``session`` because audit rows are written from
    multiple call sites (request handlers, the worker, the auth
    middleware) and we want each caller to own its transaction
    boundary.
    """
    if principal is None and (actor is None or actor_type is None):
        raise ValueError("audit.emit requires either principal= or actor+actor_type=")
    resolved_actor = actor if actor is not None else (principal.subject if principal else "system")
    resolved_actor_type: ActorType
    if actor_type is not None:
        resolved_actor_type = actor_type
    elif principal is not None:
        # principal.actor_type is a string; coerce.
        resolved_actor_type = ActorType(principal.actor_type)
    else:
        resolved_actor_type = ActorType.system

    cid = correlation_id or get_correlation_id() or ""
    ts = timestamp or utcnow()

    payload: dict[str, Any] = {
        "timestamp": ts,
        "actor": resolved_actor,
        "actor_type": resolved_actor_type.value,
        "action": action,
        "object_type": object_type,
        "object_id": object_id,
        "before": before,
        "after": after,
        "result": result.value,
        "correlation_id": cid,
        "source_ip": source_ip,
    }
    h = row_hash(payload)

    event = AuditEvent(
        timestamp=ts,
        actor=resolved_actor,
        actor_type=resolved_actor_type,
        action=action,
        object_type=object_type,
        object_id=object_id,
        before=before,
        after=after,
        result=result,
        correlation_id=cid,
        source_ip=source_ip,
        row_hash=h,
    )
    session.add(event)
    session.flush()  # surface FK/check errors immediately
    _log.info(
        "audit.emit",
        action=action,
        object_type=object_type,
        object_id=object_id,
        result=result.value,
    )
    return event
