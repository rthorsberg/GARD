"""NetBox REST write client for F9 bootstrap (POST/PATCH only)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx

from gard.integrations.netbox.auth import netbox_authorization_header
from gard.core.logging import get_logger

_log = get_logger(__name__)


class NetboxWriteNotConfigured(Exception):  # noqa: N818
    """NetBox URL or token missing."""


class NetboxWriteError(Exception):
    """NetBox write call failed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class NetboxWriteClient:
    """Minimal POST/PATCH/GET wrapper for bootstrap provisioning."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        verify_tls: bool = True,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not base_url.strip():
            raise NetboxWriteNotConfigured("NetBox URL is not set")
        if not token.strip():
            raise NetboxWriteNotConfigured("NetBox token is not set")
        self._base_url = base_url.rstrip("/") + "/"
        self._token = token
        self._verify_tls = verify_tls
        self._timeout = timeout_seconds

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": netbox_authorization_header(self._token),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        url = urljoin(self._base_url, path.lstrip("/"))
        try:
            with httpx.Client(timeout=self._timeout, verify=self._verify_tls) as client:
                resp = client.request(
                    method,
                    url,
                    headers=self._headers(),
                    params=params,
                    json=json_body,
                )
        except httpx.HTTPError as exc:
            raise NetboxWriteError(f"NetBox request failed: {exc}") from exc

        if resp.status_code >= 400:
            raise NetboxWriteError(
                f"NetBox returned HTTP {resp.status_code} for {method} {path}: {resp.text[:500]}",
                status_code=resp.status_code,
            )
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return self.request("GET", path, params=params)

    def post(self, path: str, json_body: dict[str, Any]) -> Any:
        return self.request("POST", path, json_body=json_body)

    def patch(self, path: str, json_body: dict[str, Any]) -> Any:
        return self.request("PATCH", path, json_body=json_body)

    def list_all(self, path: str, *, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Paginate GET results until exhausted."""
        out: list[dict[str, Any]] = []
        offset = 0
        base_params = dict(params or {})
        while True:
            page_params = {**base_params, "limit": 1000, "offset": offset}
            payload = self.get(path, params=page_params)
            if not isinstance(payload, dict):
                break
            results = payload.get("results")
            if not isinstance(results, list):
                break
            for item in results:
                if isinstance(item, dict):
                    out.append(item)
            if not results:
                break
            count = payload.get("count")
            offset += len(results)
            if isinstance(count, int) and offset >= count:
                break
            if payload.get("next") is None:
                break
        return out

    def get_by_slug(self, collection_path: str, slug: str) -> dict[str, Any] | None:
        payload = self.get(collection_path, params={"slug": slug, "limit": 1})
        if not isinstance(payload, dict):
            return None
        results = payload.get("results")
        if isinstance(results, list) and results and isinstance(results[0], dict):
            return results[0]
        return None

    def get_by_name(self, collection_path: str, name: str) -> dict[str, Any] | None:
        payload = self.get(collection_path, params={"name": name, "limit": 1})
        if not isinstance(payload, dict):
            return None
        results = payload.get("results")
        if isinstance(results, list) and results and isinstance(results[0], dict):
            return results[0]
        return None

    def ensure_manufacturer(self, name: str, slug: str) -> dict[str, Any]:
        existing = self.get_by_slug("api/dcim/manufacturers/", slug)
        if existing:
            return existing
        created = self.post("api/dcim/manufacturers/", {"name": name, "slug": slug})
        if not isinstance(created, dict):
            raise NetboxWriteError(f"unexpected manufacturer create response for {slug!r}")
        _log.info("netbox.write.manufacturer.created", slug=slug)
        return created

    def count_component_templates(self, device_type_id: int) -> int:
        total = 0
        for subpath in (
            "api/dcim/interface-templates/",
            "api/dcim/power-port-templates/",
            "api/dcim/console-port-templates/",
            "api/dcim/console-server-port-templates/",
            "api/dcim/power-outlet-templates/",
            "api/dcim/front-port-templates/",
            "api/dcim/rear-port-templates/",
            "api/dcim/module-bay-templates/",
            "api/dcim/device-bay-templates/",
        ):
            items = self.list_all(subpath, params={"device_type_id": device_type_id})
            total += len(items)
        return total

    def get_device(self, device_id: int) -> dict[str, Any]:
        payload = self.get(f"api/dcim/devices/{device_id}/")
        if not isinstance(payload, dict):
            raise NetboxWriteError(f"unexpected device GET response for id={device_id}")
        return payload

    def patch_device(
        self,
        device_id: int,
        *,
        custom_fields: dict[str, Any] | None = None,
        tags: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if custom_fields is not None:
            body["custom_fields"] = custom_fields
        if tags is not None:
            body["tags"] = tags
        if not body:
            raise NetboxWriteError("patch_device requires custom_fields and/or tags")
        result = self.patch(f"api/dcim/devices/{device_id}/", body)
        if not isinstance(result, dict):
            raise NetboxWriteError(f"unexpected device PATCH response for id={device_id}")
        return result

    def ensure_custom_field(
        self,
        *,
        name: str,
        label: str,
        field_type: str,
        object_types: list[str],
        description: str | None = None,
    ) -> dict[str, Any]:
        existing = self.get_by_name("api/extras/custom-fields/", name)
        if existing:
            return existing
        body: dict[str, Any] = {
            "name": name,
            "label": label,
            "type": field_type,
            "object_types": object_types,
        }
        if description:
            body["description"] = description
        created = self.post("api/extras/custom-fields/", body)
        if not isinstance(created, dict):
            raise NetboxWriteError(f"unexpected custom field create response for {name!r}")
        _log.info("netbox.write.custom_field.created", name=name)
        return created

    def ensure_tag(self, *, slug: str, name: str | None = None) -> dict[str, Any]:
        existing = self.get_by_slug("api/extras/tags/", slug)
        if existing:
            return existing
        created = self.post(
            "api/extras/tags/",
            {"name": name or slug.replace("-", " ").title(), "slug": slug},
        )
        if not isinstance(created, dict):
            raise NetboxWriteError(f"unexpected tag create response for {slug!r}")
        _log.info("netbox.write.tag.created", slug=slug)
        return created
