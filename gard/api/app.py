"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from gard.api.middleware.correlation_id import CorrelationIdMiddleware
from gard.api.middleware.errors import install as install_error_handlers
from gard.api.routers import admin_tokens, audit, evidence, health
from gard.core.logging import configure_logging
from gard.core.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or get_settings()
    s.validate_for_env()
    configure_logging(level=s.log_level, service_name=s.service_name, env=s.env)

    app = FastAPI(
        title="GARD",
        version=s.version,
        description="Service Lifecycle Guardrails — REST surface (F1).",
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
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

    return app


_PHASE3_ROUTERS: tuple[str, ...] = ("devices", "imports", "observations", "rules")


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
