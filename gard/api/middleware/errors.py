"""FastAPI exception handlers that emit the contract-stable Error envelope."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from gard.core.logging import get_correlation_id, get_logger

_log = get_logger(__name__)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    correlation_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody = Field(...)


def _render(
    *, status_code: int, code: str, message: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            details=details,
            correlation_id=get_correlation_id(),
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def install(app: FastAPI) -> None:
    """Register handlers on the FastAPI app."""

    @app.exception_handler(HTTPException)
    async def _http_exc(_: Request, exc: HTTPException) -> JSONResponse:
        return _render(
            status_code=exc.status_code,
            code=f"http_{exc.status_code}",
            message=str(exc.detail or ""),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _render(
            status_code=422,
            code="validation_error",
            message="Request validation failed",
            details={"errors": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        _log.exception("unhandled_exception", exc_type=type(exc).__name__)
        return _render(
            status_code=500,
            code="internal_error",
            message="Internal server error",
        )
