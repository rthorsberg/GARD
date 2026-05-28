"""Liveness / readiness endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from gard.core.settings import get_settings

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe", include_in_schema=True)
def healthz() -> dict[str, str]:
    s = get_settings()
    return {"status": "ok", "version": s.version, "service": s.service_name}
