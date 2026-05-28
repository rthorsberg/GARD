"""T049 — append-only role enforcement on `audit_events` (ADR-0009)."""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.contract


def _gard_app_dsn() -> str:
    """A DSN connected as ``gard_app``.

    The test owner provisions ``gard_app`` and grants membership to the
    test superuser so a ``SET ROLE`` succeeds without changing the
    connection user. ``CREATE ROLE`` is idempotent in our migration
    (0001) so the role definitely exists.
    """
    base = os.environ["GARD_DATABASE_URL"]
    return base


def test_gard_app_cannot_update_audit_events(db_session) -> None:
    # Insert an audit row using the superuser, then SET ROLE gard_app and
    # try to mutate it.
    db_session.execute(
        text(
            "INSERT INTO audit_events "
            "(id, timestamp, actor, actor_type, action, object_type, object_id, "
            " result, correlation_id, row_hash) "
            "VALUES (:id, now(), 'tester', 'user', 'test.action', "
            "        'TestObject', :oid, 'success', :cid, 'h')"
        ),
        {
            "id": uuid.uuid4(),
            "oid": "obj-1",
            "cid": "cid-1",
        },
    )
    db_session.commit()

    eng = create_engine(_gard_app_dsn(), future=True)
    try:
        with eng.begin() as conn:
            conn.execute(text("SET ROLE gard_app"))
            with pytest.raises(Exception) as exc_info:
                conn.execute(text("UPDATE audit_events SET actor = 'attacker'"))
            msg = str(exc_info.value).lower()
            assert "permission" in msg or "privilege" in msg
    finally:
        eng.dispose()


def test_gard_app_cannot_delete_audit_events(db_session) -> None:
    db_session.execute(
        text(
            "INSERT INTO audit_events "
            "(id, timestamp, actor, actor_type, action, object_type, object_id, "
            " result, correlation_id, row_hash) "
            "VALUES (:id, now(), 'tester', 'user', 'test.action', "
            "        'TestObject', :oid, 'success', :cid, 'h')"
        ),
        {
            "id": uuid.uuid4(),
            "oid": "obj-1",
            "cid": "cid-1",
        },
    )
    db_session.commit()

    eng = create_engine(_gard_app_dsn(), future=True)
    try:
        with eng.begin() as conn:
            conn.execute(text("SET ROLE gard_app"))
            with pytest.raises(Exception) as exc_info:
                conn.execute(text("DELETE FROM audit_events"))
            msg = str(exc_info.value).lower()
            assert "permission" in msg or "privilege" in msg
    finally:
        eng.dispose()
