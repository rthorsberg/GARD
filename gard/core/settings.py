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
        default=Path("gard-catalog/normalization"),
        description=(
            "Filesystem root containing the version-controlled normalization "
            "rule files (one rule per *.yaml). Sibling directories under "
            "gard-catalog/ (e.g. schemas/) are intentionally excluded."
        ),
    )

    # --- Limits ---------------------------------------------------------
    import_max_rows: int = 50_000
    import_max_bytes: int = 50 * 1024 * 1024  # 50 MiB
    import_concurrency: int = 4

    # --- F2: firmware catalog -------------------------------------------
    firmware_catalog_root: Path = Field(
        default=Path("gard-catalog/firmware"),
        description=(
            "Filesystem root containing the YAML firmware catalog "
            "(targets/, packages/, upgrade-paths/, prerequisites/). "
            "Source of truth per ADR-0011; the DB tables are a read-through cache."
        ),
    )
    blob_root: Path = Field(
        default=Path("/var/lib/gard/blobs"),
        description=(
            "Filesystem root for LocalFsBlobStore. Content-addressed under "
            "sha256/<first2>/<remaining62>.bin. v1 has no S3 backend."
        ),
    )
    firmware_blob_max_bytes: int = Field(
        default=5 * 1024**3,  # 5 GiB
        ge=1,
        description="Per-upload size cap for firmware blobs (FR-031).",
    )

    # --- F3: compliance & drift evaluation ------------------------------
    discovery_stale_days: int = Field(
        default=30,
        ge=1,
        description=(
            "After this many days without a fresh DeviceObservation the "
            "drift engine surfaces `discovery_drift` (kind="
            "stale_observation). 0 is rejected — would mark every device "
            "stale immediately."
        ),
    )
    evidence_stale_days: int = Field(
        default=90,
        ge=1,
        description=(
            "Compliant devices without a `re_evaluation` LifecycleEvidence "
            "row within this window surface `evidence_drift`. F3 v1 has no "
            "validation-evidence emitter so this rule is intentionally "
            "narrow — the threshold matters for F4/F6 forward."
        ),
    )
    compliance_evaluate_max_batch: int = Field(
        default=5000,
        ge=1,
        description=(
            "Hard cap on the device set resolved by POST /api/v1/compliance/"
            "evaluate. Larger requested sets are refused with 413 "
            "EVALUATION_TOO_LARGE (FR-014)."
        ),
    )

    # --- F4: readiness & prerequisites ----------------------------------
    readiness_stale_days: int = Field(
        default=30,
        ge=1,
        description=(
            "If the latest F3 ComplianceEvaluation for a device is older "
            "than this threshold, the per-device readiness endpoint "
            "refuses to derive a verdict from it (returns 409 "
            "READINESS_INPUT_STALE per R-8). The summary endpoint "
            "silently classifies such devices as not_applicable with "
            "reason=stale_compliance_input."
        ),
    )
    readiness_upgrade_weight_cap: int = Field(
        default=1000,
        ge=1,
        description=(
            "Maximum cumulative edge-weight allowed for an upgrade-path "
            "chain to count as 'reachable' for readiness purposes. "
            "Chains whose summed weight exceeds the cap are treated as "
            "missing_upgrade_path (severity=required)."
        ),
    )

    # --- F5: uplift planning & waves ------------------------------------
    uplift_wave_max_devices: int = Field(
        default=500,
        ge=1,
        description=(
            "Hard cap on the device set committed to a single wave "
            "(F5 spec FR-007). Larger drafts are refused with HTTP 413 "
            "WAVE_TOO_LARGE. Operators stage multi-thousand-device "
            "uplifts as multiple waves to keep blast radius bounded."
        ),
    )
    uplift_change_window_max_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description=(
            "Maximum duration of a wave's change_window (end - start). "
            "Caps the executor's risk surface per wave (ADR-0016 §C)."
        ),
    )
    uplift_change_window_min_minutes: int = Field(
        default=15,
        ge=1,
        description=(
            "Minimum duration of a wave's change_window. Prevents "
            "zero-length or sub-minute windows that would make audit "
            "evidence ambiguous."
        ),
    )
    uplift_idempotency_ttl_seconds: int = Field(
        default=300,
        ge=1,
        description=(
            "TTL on Idempotency-Key header reuse for wave creation "
            "(ADR-0016 §E). After this window the same key creates a "
            "fresh wave row rather than returning the original."
        ),
    )
    exception_max_lifetime_days: int = Field(
        default=180,
        ge=1,
        le=730,
        description=(
            "Maximum days between (now, expires_at) at creation time. "
            "Bounds the worst-case 'we forgot about this' liability. "
            "Six months is the operator-tested upper bound."
        ),
    )

    # --- F8: MCP transport -----------------------------------------------
    mcp_enabled: bool = Field(
        default=True,
        description="When false, the /mcp endpoint returns 404 and no MCP app is mounted.",
    )
    mcp_path: str = Field(
        default="/mcp",
        description="URL path where Streamable HTTP MCP is mounted on the API app.",
    )

    # --- F7: NetBox integration (read-only) ------------------------------
    netbox_url: HttpUrl | None = Field(
        default=None,
        description="NetBox base URL (e.g. http://127.0.0.1:18888). Optional until sync.",
    )
    netbox_token: str | None = Field(
        default=None,
        description="Read-only NetBox API token (Authorization: Token …).",
    )
    netbox_verify_tls: bool = Field(
        default=True,
        description="Verify TLS certificates when calling NetBox.",
    )
    netbox_timeout_seconds: float = Field(
        default=30.0,
        ge=1.0,
        le=300.0,
        description="HTTP timeout for NetBox REST calls.",
    )
    netbox_sync_max_devices: int = Field(
        default=50_000,
        ge=1,
        description="Hard cap on devices pulled per sync run.",
    )
    netbox_write_token: str | None = Field(
        default=None,
        description="Write-capable NetBox API token for F10 lifecycle write-back.",
    )
    netbox_writeback_enabled: bool = Field(
        default=True,
        description="When false, sync skips the post-sync write-back phase.",
    )

    def resolved_netbox_write_token(self) -> str | None:
        """Write token for F10; dev/test may fall back to read token."""
        if self.netbox_write_token:
            return self.netbox_write_token
        if self.env in ("dev", "test"):
            return self.netbox_token
        return None

    def writeback_active(self) -> bool:
        return self.netbox_writeback_enabled and bool(self.resolved_netbox_write_token())

    @staticmethod
    def is_local_netbox_url(url: str) -> bool:
        from urllib.parse import urlparse

        host = (urlparse(url).hostname or "").lower()
        return host in ("localhost", "127.0.0.1", "::1")

    def requires_writeback_confirm(self, netbox_url: str) -> bool:
        return self.env == "prod" or not self.is_local_netbox_url(netbox_url)

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
