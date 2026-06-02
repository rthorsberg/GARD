"""F12 IPAM alignment REST DTOs."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


class IpamAlignmentSummaryOut(BaseModel):
    devices_checked: int = Field(ge=0)
    aligned_count: int = Field(ge=0)
    mismatch_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    info_count: int = Field(ge=0)
    findings_by_kind: dict[str, int] = Field(default_factory=dict)
    l2vpn_available: bool = False


class IpamAlignmentEntryOut(BaseModel):
    device_id: uuid.UUID
    netbox_device_id: int
    overall_status: Literal["aligned", "mismatch", "unknown"]
    finding_count: int = Field(ge=0)
    top_kinds: list[str] = Field(default_factory=list, max_length=3)


class IpamAlignmentReportOut(BaseModel):
    phase: Literal["completed", "partial", "failed", "skipped"]
    run_id: uuid.UUID | None = None
    summary: IpamAlignmentSummaryOut
    entries: list[IpamAlignmentEntryOut] = Field(default_factory=list, max_length=100)


class IpamAlignmentFindingOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    device_id: uuid.UUID
    kind: str
    severity: Literal["error", "warning", "info"]
    status: Literal["open", "pass"]
    interface_name: str | None = None
    netbox_observed: dict[str, Any] | None = None
    gard_observed: dict[str, Any] | None = None
    remediation_hint: str | None = None
    created_at: dt.datetime


class IpamAlignmentFindingList(BaseModel):
    items: list[IpamAlignmentFindingOut]
    total_returned: int
    next_page_token: str | None = None


class DeviceNetworkContextOut(BaseModel):
    device_id: uuid.UUID
    netbox_device_id: int
    resolved_mgmt_ip: str | None = None
    mgmt_resolution_method: str | None = None
    primary_ip4: str | None = None
    primary_ip6: str | None = None
    interfaces: list[dict[str, Any]]
    overlay_bindings: list[dict[str, Any]] = Field(default_factory=list)
    captured_at: dt.datetime
