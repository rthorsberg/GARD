"""Device identity resolution (T072 / research.md D9).

Canonical identity for an imported row is:

1. ``serial_number`` (case-insensitive, trimmed) when present.
2. ``(hostname, site)`` (case-insensitive, trimmed) fallback.
3. Reject when both are absent — handled upstream by
   :func:`gard.api.schemas.csv_row.row_invariants`.
"""

from __future__ import annotations

from dataclasses import dataclass

from gard.api.schemas.csv_row import CsvRow


@dataclass(frozen=True)
class DeviceIdentity:
    """Effective identity coordinates used for upsert + dedup."""

    serial_lower: str | None
    hostname_lower: str | None
    site_lower: str | None

    @property
    def kind(self) -> str:
        return "serial" if self.serial_lower else "hostname_site"

    @property
    def key(self) -> str:
        """Stable text key used for in-file dedup."""
        if self.serial_lower:
            return f"serial:{self.serial_lower}"
        return f"hs:{self.hostname_lower}|{self.site_lower}"


def from_csv(row: CsvRow) -> DeviceIdentity:
    serial = (row.serial_number or "").strip().lower() or None
    if serial:
        # When serial is present, hostname/site are NOT part of identity
        # (they may legitimately differ across observations of the same
        # box, e.g., during a rename).
        return DeviceIdentity(serial_lower=serial, hostname_lower=None, site_lower=None)
    return DeviceIdentity(
        serial_lower=None,
        hostname_lower=row.hostname.strip().lower(),
        site_lower=row.site.strip().lower(),
    )
