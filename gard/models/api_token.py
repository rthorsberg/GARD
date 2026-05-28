"""`api_tokens` — service / MCP-client JWT registry."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import ARRAY, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from gard.models import Base, utcnow, uuid7_default


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7_default)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    roles: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)

    issued_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    # FR-025: never null. Default applied at the service layer from settings.
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[str] = mapped_column(String, nullable=False)
