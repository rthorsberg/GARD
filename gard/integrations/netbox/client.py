"""Read-only NetBox REST client (ADR-0017)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx

from gard.core.logging import get_logger

_log = get_logger(__name__)

_ALLOWED_METHODS = frozenset({"GET"})


class NetboxNotConfigured(Exception):  # noqa: N818
    """NetBox URL or token missing from settings."""


class NetboxUnreachable(Exception):  # noqa: N818
    """NetBox HTTP call failed (network, timeout, or non-2xx)."""

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


@dataclass(frozen=True)
class NetboxDeviceRecord:
    """Normalized DCIM device row from NetBox REST."""

    id: int
    name: str
    serial: str | None
    site: str
    role: str | None
    vendor_raw: str
    model_raw: str
    tags: tuple[str, ...]


def _nested_slug_or_name(value: dict[str, Any] | None) -> str | None:
    if not value:
        return None
    slug = value.get("slug")
    if isinstance(slug, str) and slug.strip():
        return slug.strip()
    name = value.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    display = value.get("display")
    if isinstance(display, str) and display.strip():
        return display.strip()
    return None


def _parse_device(payload: dict[str, Any]) -> NetboxDeviceRecord:
    site = _nested_slug_or_name(payload.get("site"))
    if not site:
        raise ValueError(f"netbox device {payload.get('id')!r} missing site")

    device_type = payload.get("device_type") or {}
    manufacturer = device_type.get("manufacturer") or {}
    vendor = manufacturer.get("name") or "unknown"
    model = device_type.get("model") or "unknown"

    tag_slugs: list[str] = []
    for tag in payload.get("tags") or []:
        if isinstance(tag, dict):
            slug = tag.get("slug")
            if isinstance(slug, str) and slug.strip():
                tag_slugs.append(slug.strip())

    serial = payload.get("serial")
    serial_str = serial.strip() if isinstance(serial, str) and serial.strip() else None

    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"netbox device {payload.get('id')!r} missing name")

    role = _nested_slug_or_name(payload.get("role"))

    device_id = payload.get("id")
    if not isinstance(device_id, int):
        raise ValueError(f"netbox device payload missing integer id: {device_id!r}")

    return NetboxDeviceRecord(
        id=device_id,
        name=name.strip(),
        serial=serial_str,
        site=site,
        role=role,
        vendor_raw=str(vendor),
        model_raw=str(model),
        tags=tuple(sorted(set(tag_slugs))),
    )


class NetboxClient:
    """Paginated read-only wrapper around NetBox REST API v4."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        verify_tls: bool = True,
        timeout_seconds: float = 30.0,
        page_size: int = 1000,
        max_devices: int = 50_000,
    ) -> None:
        if not base_url.strip():
            raise NetboxNotConfigured("GARD_NETBOX_URL is not set")
        if not token.strip():
            raise NetboxNotConfigured("GARD_NETBOX_TOKEN is not set")
        self._base_url = base_url.rstrip("/") + "/"
        self._token = token
        self._verify_tls = verify_tls
        self._timeout = timeout_seconds
        self._page_size = min(max(page_size, 1), 1000)
        self._max_devices = max(max_devices, 1)

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None) -> Any:
        if method not in _ALLOWED_METHODS:
            raise RuntimeError(f"NetBox client is read-only; {method} is forbidden")
        url = urljoin(self._base_url, path.lstrip("/"))
        headers = {
            "Authorization": f"Token {self._token}",
            "Accept": "application/json",
        }
        try:
            with httpx.Client(timeout=self._timeout, verify=self._verify_tls) as client:
                resp = client.request(method, url, headers=headers, params=params)
        except httpx.HTTPError as exc:
            raise NetboxUnreachable(f"NetBox request failed: {exc}") from exc

        if resp.status_code >= 400:
            raise NetboxUnreachable(
                f"NetBox returned HTTP {resp.status_code} for {path}: {resp.text[:500]}"
            )
        return resp.json()

    def list_devices(self) -> list[NetboxDeviceRecord]:
        """Fetch all DCIM devices up to ``max_devices``."""
        out: list[NetboxDeviceRecord] = []
        offset = 0
        while True:
            payload = self._request(
                "GET",
                "api/dcim/devices/",
                params={"limit": self._page_size, "offset": offset},
            )
            if not isinstance(payload, dict):
                raise NetboxUnreachable("NetBox devices response is not a JSON object")
            results = payload.get("results")
            if not isinstance(results, list):
                raise NetboxUnreachable("NetBox devices response missing results[]")

            for item in results:
                if not isinstance(item, dict):
                    continue
                out.append(_parse_device(item))
                if len(out) >= self._max_devices:
                    _log.warning(
                        "netbox.list_devices.truncated",
                        max_devices=self._max_devices,
                    )
                    return out

            count = payload.get("count")
            offset += len(results)
            if not results:
                break
            if isinstance(count, int) and offset >= count:
                break
            next_url = payload.get("next")
            if next_url is None:
                break

        return out
