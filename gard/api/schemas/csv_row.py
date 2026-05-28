"""CSV row Pydantic models matching `contracts/csv-schema.yaml` (T070)."""

from __future__ import annotations

import datetime as dt
import ipaddress
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

CSV_SCHEMA_VERSION = "1.0.0"


def _strip_or_none(v: str | None) -> str | None:
    if v is None:
        return None
    s = v.strip()
    return s if s else None


class CsvRow(BaseModel):
    """One device-inventory CSV row, post column parsing.

    Pydantic enforces required-not-null fields; row-level invariants
    (identity_present, vendor_or_model_present, observed_at_not_far_future)
    are checked separately by :func:`row_invariants` so the failure can
    be mapped to a stable error code.
    """

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    hostname: str = Field(min_length=1)
    site: str = Field(min_length=1)
    serial_number: str | None = None

    vendor_raw: str = Field(min_length=1)
    model_raw: str = Field(min_length=1)
    platform_family_raw: str | None = None
    hardware_revision: str | None = None

    management_ip: str | None = None
    region: str | None = None
    role: str | None = None

    observed_firmware: str | None = None
    observed_bootloader: str | None = None
    observed_at: dt.datetime | None = None

    @field_validator(
        "serial_number",
        "platform_family_raw",
        "hardware_revision",
        "region",
        "role",
        "observed_firmware",
        "observed_bootloader",
        "management_ip",
        mode="before",
    )
    @classmethod
    def _empty_to_none(cls, v: Any) -> Any:
        if isinstance(v, str):
            return _strip_or_none(v)
        return v


CSV_ERROR_CODES: dict[str, str] = {
    "ROW_ENCODING": "Row failed UTF-8 decoding.",
    "ROW_BAD_COLUMNS": "Row column count does not match the header.",
    "ROW_MISSING_IDENTITY": "Row has neither serial_number nor (hostname, site).",
    "ROW_MISSING_VENDOR_AND_MODEL": "Row has empty vendor_raw and model_raw.",
    "ROW_OBSERVED_AT_FUTURE": "observed_at is more than 5 minutes in the future.",
    "ROW_BAD_IPADDRESS": "management_ip is not a valid IPv4/IPv6 address.",
    "ROW_BAD_DATETIME": "observed_at is not a valid RFC 3339 timestamp.",
    "ROW_DUPLICATE_IN_FILE": (
        "Row collides with an earlier row on identity; later row wins for canonical "
        "Device, all rows recorded as observations."
    ),
    "ROW_VALIDATION": "Row failed Pydantic validation.",
    "ROW_MISSING_HEADER": "Required header column missing.",
}


REQUIRED_COLUMNS = (
    "hostname",
    "site",
    "serial_number",
    "vendor_raw",
    "model_raw",
    "observed_firmware",
)


def row_invariants(row: CsvRow) -> list[tuple[str, str]]:
    """Apply row-level invariants from the CSV schema. Return error tuples (code, msg)."""
    errs: list[tuple[str, str]] = []
    if not row.serial_number and not (row.hostname and row.site):
        errs.append(("ROW_MISSING_IDENTITY", "missing serial_number and hostname+site"))
    if not (row.vendor_raw or row.model_raw):
        errs.append(("ROW_MISSING_VENDOR_AND_MODEL", "vendor_raw and model_raw both empty"))
    if row.observed_at is not None:
        now = dt.datetime.now(dt.UTC)
        # observed_at may be naive after parsing; normalize:
        oa = row.observed_at
        if oa.tzinfo is None:
            oa = oa.replace(tzinfo=dt.UTC)
        if oa > now + dt.timedelta(minutes=5):
            errs.append(("ROW_OBSERVED_AT_FUTURE", f"observed_at={oa.isoformat()} > now+5min"))
    if row.management_ip is not None:
        try:
            ipaddress.ip_address(row.management_ip)
        except ValueError:
            errs.append(("ROW_BAD_IPADDRESS", f"invalid IP: {row.management_ip}"))
    return errs
