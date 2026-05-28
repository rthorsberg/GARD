"""Application settings loaded from environment variables.

All settings are immutable at runtime — re-read by re-instantiating
:class:`Settings`. Tests should construct ad-hoc instances; the rest of
the codebase uses :func:`get_settings` (lru-cached).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 30 days; default per spec FR-025. Operators may shorten via env.
DEFAULT_API_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30

# Sentinel used to detect "operator forgot to set GARD_JWT_SECRET". Kept
# as a module constant so static analyzers don't flag it as a hard-coded
# password.
_DEV_JWT_SECRET = "dev-secret-change-me"  # noqa: S105


class Settings(BaseSettings):
    """Process-wide configuration.

    Read from `GARD_*` env vars; in dev/test, also from `.env` if present.
    """

    model_config = SettingsConfigDict(
        env_prefix="GARD_",
        env_file=(".env",),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Runtime --------------------------------------------------------
    env: Literal["dev", "test", "staging", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    service_name: str = "gard"
    version: str = "0.1.0"

    # --- HTTP -----------------------------------------------------------
    api_host: str = "0.0.0.0"  # noqa: S104  bound by reverse proxy / TLS terminator
    api_port: int = 8000
    # If `True`, the app refuses to start when the request scheme is `http`
    # (configurable for local dev). Production deployments MUST set this
    # `True`. Tests/dev compose may set `False`.
    require_tls: bool = True

    # --- Database -------------------------------------------------------
    database_url: str = Field(
        default="postgresql+psycopg://gard:gard@localhost:5432/gard",
        description="SQLAlchemy URL for the application Postgres.",
    )
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # --- Auth -----------------------------------------------------------
    oidc_issuer: HttpUrl | None = None
    oidc_audience: str | None = None
    jwt_secret: str = Field(
        default=_DEV_JWT_SECRET,
        description="HS256 signing secret for service-issued API tokens.",
    )
    jwt_algorithm: Literal["HS256", "RS256"] = "HS256"
    api_token_ttl_seconds: int = Field(
        default=DEFAULT_API_TOKEN_TTL_SECONDS,
        ge=60,
        le=60 * 60 * 24 * 365,
        description="Default TTL applied to newly minted API tokens (FR-025).",
    )

    # --- Catalog --------------------------------------------------------
    catalog_root: Path = Field(
        default=Path("gard-catalog"),
        description="Filesystem root of the version-controlled normalization catalog.",
    )

    # --- Limits ---------------------------------------------------------
    import_max_rows: int = 50_000
    import_max_bytes: int = 50 * 1024 * 1024  # 50 MiB
    import_concurrency: int = 4

    @field_validator("jwt_secret")
    @classmethod
    def _reject_weak_prod_secret(cls, v: str, info) -> str:  # type: ignore[no-untyped-def]
        # We can't see env from here cleanly; the gate is in `validate_for_env`.
        return v

    def validate_for_env(self) -> None:
        """Raise if the settings combination is unsafe for the chosen env.

        Called once at app startup. Tests bypass by using env="dev" or "test".
        """
        if self.env == "prod":
            import os

            if self.jwt_secret == _DEV_JWT_SECRET:
                raise RuntimeError("GARD_JWT_SECRET must be set in production")
            if not self.require_tls:
                raise RuntimeError("GARD_REQUIRE_TLS must be true in production (FR-024)")
            if self.oidc_issuer is None or self.oidc_audience is None:
                raise RuntimeError(
                    "GARD_OIDC_ISSUER and GARD_OIDC_AUDIENCE are required in production"
                )
            # ADR-0009: append-only audit/evidence writes MUST go through a
            # dedicated DB role with INSERT/SELECT only. In prod we refuse
            # to start when the two DSNs collapse onto the same user.
            ao_dsn = os.environ.get("GARD_DATABASE_URL_APPEND_ONLY")
            if not ao_dsn or ao_dsn == self.database_url:
                raise RuntimeError(
                    "GARD_DATABASE_URL_APPEND_ONLY must be set to a distinct "
                    "DSN connecting as gard_writer_append_only in production "
                    "(ADR-0009)"
                )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return process-wide settings (cached)."""
    return Settings()


def reset_settings_cache() -> None:
    """Test helper: clear the cached :func:`get_settings` value."""
    get_settings.cache_clear()
