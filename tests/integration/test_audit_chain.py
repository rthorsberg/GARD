"""T053 — emit N audit events, run chain seal, verify chained SHA-256."""

from __future__ import annotations

import datetime as dt

import pytest

from gard.core.audit import emit as emit_audit
from gard.core.hashing import row_hash
from gard.models import AuditEvent
from gard.models._enums import ActorType, AuditResult
from gard.worker import seal_day

pytestmark = pytest.mark.integration


def test_chain_seal_yields_expected_hash(db_session) -> None:
    yesterday = dt.datetime.now(dt.UTC).replace(microsecond=0) - dt.timedelta(days=1)
    base = yesterday.replace(hour=12, minute=0, second=0)
    target_day = base.date()

    for i in range(5):
        emit_audit(
            session=db_session,
            action=f"test.action.{i}",
            object_type="TestObj",
            object_id=f"o-{i}",
            actor="tester",
            actor_type=ActorType.user,
            result=AuditResult.success,
            correlation_id=f"cid-{i}",
            timestamp=base + dt.timedelta(seconds=i),
        )
    db_session.commit()

    rows = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.timestamp >= base, AuditEvent.timestamp < base + dt.timedelta(days=1))
        .order_by(AuditEvent.timestamp.asc(), AuditEvent.id.asc())
        .all()
    )
    assert len(rows) == 5

    expected = ""
    for r in rows:
        expected = row_hash({"row": r.row_hash}, previous_hash=expected or None)

    result = seal_day(db_session, target_day)
    db_session.commit()

    assert result.rows_sealed == 5
    assert result.last_event_hash == expected


def test_seal_refuses_current_day(db_session) -> None:
    today = dt.datetime.now(dt.UTC).date()
    with pytest.raises(ValueError, match="refusing to seal"):
        seal_day(db_session, today)
