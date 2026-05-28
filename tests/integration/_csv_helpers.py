"""Test helpers — generate CSV bodies that match `contracts/csv-schema.yaml`."""

from __future__ import annotations

import io
from collections.abc import Iterable

CSV_HEADER = (
    "hostname,site,serial_number,vendor_raw,model_raw,platform_family_raw,"
    "hardware_revision,management_ip,region,role,observed_firmware,"
    "observed_bootloader,observed_at\n"
)


def csv_row(
    *,
    hostname: str = "csp-edge-osl-01",
    site: str = "oslo-dc1",
    serial_number: str = "FCW2345Q9LK",
    vendor_raw: str = "Cisco Systems",
    model_raw: str = "ISR1121-8P",
    platform_family_raw: str = "ios-xe",
    hardware_revision: str = "V01",
    management_ip: str = "10.20.30.40",
    region: str = "NO",
    role: str = "edge",
    observed_firmware: str = "17.09.04a",
    observed_bootloader: str = "rom-monitor 17.07",
    observed_at: str = "2026-05-26T22:14:03Z",
) -> str:
    parts = [
        hostname,
        site,
        serial_number,
        vendor_raw,
        model_raw,
        platform_family_raw,
        hardware_revision,
        management_ip,
        region,
        role,
        observed_firmware,
        observed_bootloader,
        observed_at,
    ]
    return ",".join(parts) + "\n"


def csv_body(rows: Iterable[str]) -> bytes:
    buf = io.StringIO()
    buf.write(CSV_HEADER)
    for r in rows:
        buf.write(r)
    return buf.getvalue().encode("utf-8")
