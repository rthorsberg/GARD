"""Optional CORS for split-origin dev (F11 operator portal)."""

from __future__ import annotations

from starlette.middleware.cors import CORSMiddleware

from fastapi import FastAPI

from gard.core.settings import Settings


def install_cors(app: FastAPI, settings: Settings) -> None:
    """Register CORSMiddleware when GARD_CORS_ORIGINS is non-empty."""
    raw = (settings.cors_origins or "").strip()
    if not raw:
        return
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if not origins:
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Correlation-ID", "Accept"],
    )
