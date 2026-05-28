"""DTOs for the admin token endpoints (T045)."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field

from gard.models._enums import Role


class IssueTokenRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    subject: str = Field(min_length=1, max_length=256)
    roles: list[Role] = Field(min_length=1)
    ttl_seconds: int | None = Field(default=None, ge=60, le=60 * 60 * 24 * 365)


class IssueTokenResponse(BaseModel):
    token_id: uuid.UUID
    jwt: str
    expires_at: dt.datetime
    name: str
    subject: str
    roles: list[Role]


class TokenSummary(BaseModel):
    id: uuid.UUID
    name: str
    subject: str
    roles: list[str]
    issued_at: dt.datetime
    expires_at: dt.datetime
    revoked_at: dt.datetime | None = None
