"""GARD background worker.

v1 responsibilities (per ADR-0009 / tasks.md T040):

- Daily checksum-chain sealing of `audit_events` and `lifecycle_evidence`.

Future (Phase 3 onwards):

- Consume the `import_jobs` queue (`SELECT … FOR UPDATE SKIP LOCKED`).
- Re-evaluate observations triggered by rule changes.
"""

from __future__ import annotations

import datetime as dt
import sys
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.core.hashing import row_hash
from gard.core.logging import configure_logging, get_logger
from gard.core.settings import get_settings
from gard.db.session import session_scope
from gard.models import AuditChainHead, AuditEvent, utcnow

_log = get_logger(__name__)


@dataclass(frozen=True)
class SealResult:
    day: dt.date
    rows_sealed: int
    last_event_hash: str
    is_new: bool


def seal_day(session: Session, day: dt.date) -> SealResult:
    """Seal one UTC day's audit chain.

    Idempotent: re-sealing the same day overwrites if and only if the
    computed head differs (it shouldn't, since `audit_events` is
    append-only). We refuse to seal the current UTC day — sealing while
    new rows can still arrive yields a meaningless head.
    """
    today = utcnow().date()
    if day >= today:
        raise ValueError(f"refusing to seal current/future day {day} (today is {today})")

    start = dt.datetime.combine(day, dt.time.min, tzinfo=dt.UTC)
    end = start + dt.timedelta(days=1)

    rows = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.timestamp >= start, AuditEvent.timestamp < end)
        .order_by(AuditEvent.timestamp.asc(), AuditEvent.id.asc())
    ).all()

    chain = ""
    for r in rows:
        chain = row_hash({"row": r.row_hash}, previous_hash=chain or None)

    head = session.get(AuditChainHead, day)
    if head is None:
        head = AuditChainHead(day=day, last_event_hash=chain, sealed_at=utcnow())
        session.add(head)
        is_new = True
    else:
        head.last_event_hash = chain
        head.sealed_at = utcnow()
        is_new = False
    session.flush()

    _log.info(
        "audit.chain.sealed",
        day=str(day),
        rows=len(rows),
        last_event_hash=chain,
        is_new=is_new,
    )
    return SealResult(day=day, rows_sealed=len(rows), last_event_hash=chain, is_new=is_new)


def seal_yesterday() -> SealResult:
    """Seal the day immediately before the current UTC day."""
    yesterday = utcnow().date() - dt.timedelta(days=1)
    with session_scope() as session:
        return seal_day(session, yesterday)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI
    s = get_settings()
    configure_logging(level=s.log_level, service_name=s.service_name, env=s.env)
    cmd = (argv or sys.argv[1:])[:1]
    if not cmd or cmd[0] == "seal-yesterday":
        seal_yesterday()
        return 0
    sys.stderr.write(f"unknown worker command: {cmd[0]}\n")
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
