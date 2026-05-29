"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from gard.api.middleware.correlation_id import CorrelationIdMiddleware
from gard.api.middleware.errors import install as install_error_handlers
from gard.api.routers import admin_tokens, audit, evidence, health
from gard.core.logging import configure_logging
from gard.core.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or get_settings()
    s.validate_for_env()
    configure_logging(level=s.log_level, service_name=s.service_name, env=s.env)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Best-effort catalog reload on app boot. Failures are logged but
        # do not block startup (constitution: serve last-known state rather
        # than crash — ADR-0011 §8).
        from gard.catalog.normalization_loader import load_catalog
        from gard.core.firmware_catalog_controller import reload_safe as fw_reload_safe
        from gard.core.logging import get_logger
        from gard.db.session import append_only_scope, session_scope

        log = get_logger(__name__)

        # F1 normalization rules.
        try:
            with session_scope() as session:
                report = load_catalog(session, s.catalog_root)
            log.info(
                "catalog.bootstrap",
                loaded=report.loaded,
                skipped=report.skipped,
                errors=len(report.errors),
            )
        except Exception as exc:  # pragma: no cover - DB may be down at boot
            log.warning("catalog.bootstrap_failed", error=str(exc))

        # F2 firmware catalog. reload_safe swallows errors and emits a
        # structured-log warning — the API serves the last-known catalog
        # state rather than refusing to come up. See ADR-0011 §8.
        try:
            outcome = fw_reload_safe(
                session_factory=session_scope,
                audit_session_factory=append_only_scope,
                catalog_root=s.firmware_catalog_root,
            )
            if outcome.success and outcome.report is not None:
                log.info(
                    "firmware_catalog.bootstrap",
                    loaded=outcome.report.loaded,
                    removed=outcome.report.removed,
                    unchanged=outcome.report.unchanged,
                    files=len(outcome.report.file_relpaths_seen),
                    dirty=outcome.dirty,
                )
            else:
                err = outcome.error
                log.warning(
                    "firmware_catalog.bootstrap_failed",
                    file=err.file_relpath if err is not None else "?",
                    reason=err.reason if err is not None else "?",
                )
        except Exception as exc:  # pragma: no cover - DB may be down at boot
            log.warning("firmware_catalog.bootstrap_unexpected_error", error=str(exc))

        yield

    app = FastAPI(
        title="GARD",
        version=s.version,
        description="Service Lifecycle Guardrails — REST surface (F1).",
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Order matters: correlation id wraps everything so logs and error
    # bodies inherit the id even from the auth/rbac dependencies.
    app.add_middleware(CorrelationIdMiddleware)

    install_error_handlers(app)

    app.include_router(health.router)
    app.include_router(admin_tokens.router)
    app.include_router(audit.router)
    app.include_router(evidence.router)

    # Phase 3 routers (devices, imports, observations) are registered
    # via :func:`_register_phase3` below so the app skeleton stays
    # importable even before those modules exist.
    _register_phase3(app)

    _install_openapi_security(app)

    return app


def _install_openapi_security(app: FastAPI) -> None:
    """Advertise HTTP Bearer auth in the served OpenAPI document.

    The auth middleware reads ``Authorization`` via :class:`fastapi.Header`,
    which is intentional (we accept both GARD-issued service JWTs and, in a
    later feature, OIDC ID tokens via the same header). FastAPI therefore
    cannot infer a security scheme from the dependency, so we register one
    explicitly here. This is purely a schema/documentation concern — runtime
    auth enforcement is unchanged — and it gives Swagger UI the ``Authorize``
    padlock it needs for ``/healthz``-style anonymous endpoints to coexist
    with the bearer-protected ``/api/v1/...`` surface.
    """

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        components = schema.setdefault("components", {})
        components.setdefault("securitySchemes", {})["HTTPBearer"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "Paste the raw JWT (no `Bearer ` prefix). Mint one via "
                "`docker compose exec api python -m gard issue-token "
                "--subject you@example.com --role lifecycle_manager`."
            ),
        }
        schema["security"] = [{"HTTPBearer": []}]
        for path_item in schema.get("paths", {}).values():
            for method, op in path_item.items():
                if method not in {"get", "post", "put", "patch", "delete"}:
                    continue
                tags = op.get("tags") or []
                if "health" in tags:
                    op["security"] = []
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]


_PHASE3_ROUTERS: tuple[str, ...] = (
    "devices",
    "imports",
    "observations",
    "rules",
    # F2 (002-firmware-catalog):
    "firmware_compliance",
    "firmware_targets",
    "firmware_upgrade_paths",
    "firmware_prerequisites",
)


def _register_phase3(app: FastAPI) -> None:
    """Register Phase 3 / Phase 4 routers if their modules import cleanly."""
    import importlib

    for name in _PHASE3_ROUTERS:
        try:
            mod = importlib.import_module(f"gard.api.routers.{name}")
        except ImportError:
            continue
        router = getattr(mod, "router", None)
        if router is not None:
            app.include_router(router)


app = create_app()


def run_uvicorn() -> int:  # pragma: no cover - thin shim used by `gard serve`
    import uvicorn

    s = get_settings()
    uvicorn.run("gard.api.app:app", host=s.api_host, port=s.api_port, log_level=s.log_level.lower())
    return 0
