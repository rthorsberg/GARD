"""T050 — append-only role enforcement on `lifecycle_evidence`."""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.contract


def _seed(db_session) -> None:
    db_session.execute(
        text(
            "INSERT INTO lifecycle_evidence "
            "(id, evidence_type, subject_type, subject_id, actor, system, "
            " timestamp, row_hash) "
            "VALUES (:id, 'import', 'ImportJob', :sid, 'tester', 'gard@test', "
            "        now(), 'h')"
        ),
        {"id": uuid.uuid4(), "sid": "j1"},
    )
    db_session.commit()


def _assert_denied(role: str, sql: str) -> None:
    eng = create_engine(os.environ["GARD_DATABASE_URL"], future=True)
    try:
        with eng.begin() as conn:
            conn.execute(text(f"SET ROLE {role}"))
            with pytest.raises(Exception) as exc_info:
                conn.execute(text(sql))
            msg = str(exc_info.value).lower()
            assert "permission" in msg or "privilege" in msg
    finally:
        eng.dispose()


def test_gard_app_cannot_update_evidence(db_session) -> None:
    _seed(db_session)
    _assert_denied("gard_app", "UPDATE lifecycle_evidence SET actor = 'attacker'")


def test_gard_app_cannot_delete_evidence(db_session) -> None:
    _seed(db_session)
    _assert_denied("gard_app", "DELETE FROM lifecycle_evidence")


def test_gard_writer_append_only_cannot_update(db_session) -> None:
    _seed(db_session)
    _assert_denied(
        "gard_writer_append_only",
        "UPDATE lifecycle_evidence SET actor = 'attacker'",
    )
