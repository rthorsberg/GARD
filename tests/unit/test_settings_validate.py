"""Unit tests for Settings.validate_for_env()."""

from __future__ import annotations

import pytest

from gard.core.settings import Settings

pytestmark = pytest.mark.unit


def _prod_kwargs(**overrides):  # type: ignore[no-untyped-def]
    base = {
        "env": "prod",
        "jwt_secret": "long-strong-secret-x" * 2,
        "require_tls": True,
        "oidc_issuer": "https://idp.example.com/",
        "oidc_audience": "gard",
        "database_url": "postgresql+psycopg://gard_app:p@host/gard",
    }
    base.update(overrides)
    return base


def test_prod_requires_jwt_secret(monkeypatch) -> None:
    monkeypatch.setenv(
        "GARD_DATABASE_URL_APPEND_ONLY", "postgresql+psycopg://gard_writer:p@host/gard"
    )
    s = Settings(**_prod_kwargs(jwt_secret="dev-secret-change-me"))
    with pytest.raises(RuntimeError, match="GARD_JWT_SECRET"):
        s.validate_for_env()


def test_prod_requires_tls(monkeypatch) -> None:
    monkeypatch.setenv(
        "GARD_DATABASE_URL_APPEND_ONLY", "postgresql+psycopg://gard_writer:p@host/gard"
    )
    s = Settings(**_prod_kwargs(require_tls=False))
    with pytest.raises(RuntimeError, match="GARD_REQUIRE_TLS"):
        s.validate_for_env()


def test_prod_requires_oidc(monkeypatch) -> None:
    monkeypatch.setenv(
        "GARD_DATABASE_URL_APPEND_ONLY", "postgresql+psycopg://gard_writer:p@host/gard"
    )
    s = Settings(**_prod_kwargs(oidc_issuer=None))
    with pytest.raises(RuntimeError, match="OIDC"):
        s.validate_for_env()


def test_prod_requires_distinct_append_only_dsn(monkeypatch) -> None:
    same = "postgresql+psycopg://gard_app:p@host/gard"
    monkeypatch.setenv("GARD_DATABASE_URL_APPEND_ONLY", same)
    s = Settings(**_prod_kwargs(database_url=same))
    with pytest.raises(RuntimeError, match="DATABASE_URL_APPEND_ONLY"):
        s.validate_for_env()


def test_prod_requires_append_only_dsn_set(monkeypatch) -> None:
    monkeypatch.delenv("GARD_DATABASE_URL_APPEND_ONLY", raising=False)
    s = Settings(**_prod_kwargs())
    with pytest.raises(RuntimeError, match="DATABASE_URL_APPEND_ONLY"):
        s.validate_for_env()


def test_prod_passes_when_correctly_configured(monkeypatch) -> None:
    monkeypatch.setenv(
        "GARD_DATABASE_URL_APPEND_ONLY",
        "postgresql+psycopg://gard_writer:p@host/gard",
    )
    s = Settings(**_prod_kwargs())
    s.validate_for_env()  # should not raise


def test_dev_skips_all_validation() -> None:
    s = Settings(env="dev", jwt_secret="dev-secret-change-me", require_tls=False)
    s.validate_for_env()  # should not raise
