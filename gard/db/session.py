"""SQLAlchemy engines and FastAPI session dependency.

Two engines are provided to honour ADR-0009's append-only constraint:

- :data:`engine_app` — connects as ``gard_app``: full INSERT/UPDATE/SELECT
  on regular tables, INSERT/SELECT only on append-only tables. Used by
  the request path for everything except direct audit/evidence emission.

- :data:`engine_append_only` — connects as
  ``gard_writer_append_only``: INSERT/SELECT only, used by the
  audit/evidence helpers in :mod:`gard.core.audit` and
  :mod:`gard.core.evidence` so a single SQL injection in business code
  cannot rewrite history.

In v1 dev/test the same DSN is used for both with the same DB user; the
real role split is enforced by the bootstrap migration (T014). Tests
that verify the role boundary set ``GARD_DATABASE_URL_APPEND_ONLY``
explicitly.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from gard.core.settings import Settings, get_settings


def _build_engine(url: str, settings: Settings) -> Engine:
    return create_engine(
        url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,
        future=True,
    )


@lru_cache(maxsize=1)
def get_engine_app() -> Engine:
    settings = get_settings()
    return _build_engine(settings.database_url, settings)


@lru_cache(maxsize=1)
def get_engine_append_only() -> Engine:
    settings = get_settings()
    # Optional dedicated DSN; falls back to the app DSN in dev/test.
    import os

    url = os.environ.get("GARD_DATABASE_URL_APPEND_ONLY", settings.database_url)
    return _build_engine(url, settings)


def reset_engine_caches() -> None:
    """Test helper — rebuild engines after settings or env change."""
    get_engine_app.cache_clear()
    get_engine_append_only.cache_clear()


def _maker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session, future=True)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: yields a request-scoped Session bound to ``gard_app``."""
    sm = _maker(get_engine_app())
    with sm() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def get_append_only_session() -> Iterator[Session]:
    """FastAPI dependency: yields an append-only session for audit/evidence writes."""
    sm = _maker(get_engine_append_only())
    with sm() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


@contextmanager
def session_scope() -> Iterator[Session]:
    """Non-FastAPI context manager (workers, scripts, tests)."""
    sm = _maker(get_engine_app())
    with sm() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


@contextmanager
def append_only_scope() -> Iterator[Session]:
    sm = _maker(get_engine_append_only())
    with sm() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
