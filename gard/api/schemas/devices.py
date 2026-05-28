"""Device DTOs (T077)."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field, field_validator

from gard.core.envelope import ResponseEnvelope


class DeviceFacts(BaseModel):
    id: uuid.UUID
    serial_number: str | None = None
    hostname: str
    site: str
    region: str | None = None
    role: str | None = None
    management_ip: str | None = None
    vendor_raw: str
    vendor_normalized: str | None = None
    model_raw: str
    model_normalized: str | None = None
    platform_family: str | None = None
    hardware_revision: str | None = None
    lifecycle_state: str
    source_system: str
    created_at: dt.datetime
    updated_at: dt.datetime

    @field_validator("management_ip", mode="before")
    @classmethod
    def _coerce_ip(cls, v: object) -> object:
        # psycopg INET maps to ipaddress.IPv4Address / IPv6Address; keep
        # the model's external shape stable as a string.
        if v is None:
            return v
        return str(v)


class DeviceWithEnvelope(BaseModel):
    facts: DeviceFacts
    envelope: ResponseEnvelope[DeviceFacts]


class DeviceList(BaseModel):
    items: list[DeviceWithEnvelope]
    total_returned: int = Field(ge=0)
    next_page_token: str | None = None
