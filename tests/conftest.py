"""Shared pytest fixtures.

Tests assume the following env vars exist (set via pytest-env, the CI
workflow, or a shell wrapper):

- ``GARD_DATABASE_URL`` — psycopg DSN for the test Postgres
- ``GARD_JWT_SECRET``  — any non-default value

The default fixture set creates a clean schema once per session and
truncates the data tables between tests. Tests that need the DB request
the ``db_session`` fixture; tests that need the FastAPI app request
``client``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from gard.core.settings import reset_settings_cache
from gard.db.session import reset_engine_caches


# Always test against a running Postgres. There is no SQLite path because
# the schema relies on JSONB, partial unique indexes, INET, and ARRAY.
def _require_dsn() -> str:
    dsn = os.environ.get("GARD_DATABASE_URL")
    if not dsn:
        pytest.skip("GARD_DATABASE_URL not set; integration tests need Postgres")
    return dsn


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def _migrated_db(project_root: Path) -> str:
    dsn = _require_dsn()
    # Run alembic upgrade head once per session.
    env = os.environ.copy()
    env["GARD_DATABASE_URL"] = dsn
    env.setdefault("GARD_JWT_SECRET", "test-secret")
    env.setdefault("GARD_REQUIRE_TLS", "false")
    res = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "gard/db/alembic.ini", "upgrade", "head"],
        cwd=str(project_root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        pytest.fail(
            "alembic upgrade head failed:\n" + res.stdout + "\n" + res.stderr,
            pytrace=False,
        )
    return dsn


@pytest.fixture(scope="session")
def engine(_migrated_db: str) -> Iterator[Engine]:
    eng = create_engine(_migrated_db, future=True)
    yield eng
    eng.dispose()


_DATA_TABLES = (
    # F5 tables — must be truncated before the tables they FK to (devices,
    # readiness_evaluations, firmware_prerequisite_rules). CASCADE on
    # TRUNCATE handles the dependency graph either way, but listing them
    # first keeps the dependency direction obvious to a reader.
    "uplift_wave_devices",
    "uplift_exceptions",
    "uplift_waves",
    "uplift_plans",
    "readiness_evaluations",
    "compliance_evaluations",
    "manual_mappings",
    "device_observations",
    "import_jobs",
    "audit_chain_heads",
    "audit_events",
    "lifecycle_evidence",
    "api_tokens",
    "normalization_rules",
    "firmware_prerequisite_rules",
    "firmware_upgrade_paths",
    "firmware_packages",
    "firmware_targets",
    "devices",
)


@pytest.fixture(autouse=True)
def _truncate_tables(engine: Engine) -> Iterator[None]:
    yield
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_DATA_TABLES)} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as session:
        yield session
        session.rollback()


@pytest.fixture(autouse=True)
def _reset_caches(_migrated_db: str) -> None:
    # Make sure each test sees fresh settings & engine caches that pick
    # up any os.environ changes the test made.
    reset_settings_cache()
    reset_engine_caches()


@pytest.fixture
def client() -> Iterator[TestClient]:
    from gard.api.app import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c
