"""Import community device type YAML into NetBox (F9 bootstrap)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from gard.core.logging import get_logger
from gard.integrations.netbox.devicetype_manifest import DeviceTypeManifest, ManifestEntry
from gard.integrations.netbox.write_client import NetboxWriteClient, NetboxWriteError

_log = get_logger(__name__)

# Community YAML list keys → NetBox template collection paths.
_COMPONENT_SPECS: tuple[tuple[str, str, str], ...] = (
    ("interfaces", "api/dcim/interface-templates/", "interface"),
    ("power-ports", "api/dcim/power-port-templates/", "power-port"),
    ("console-ports", "api/dcim/console-port-templates/", "console-port"),
    ("console-server-ports", "api/dcim/console-server-port-templates/", "console-server-port"),
    ("power-outlets", "api/dcim/power-outlet-templates/", "power-outlet"),
    ("front-ports", "api/dcim/front-port-templates/", "front-port"),
    ("rear-ports", "api/dcim/rear-port-templates/", "rear-port"),
    ("module-bays", "api/dcim/module-bay-templates/", "module-bay"),
    ("device-bays", "api/dcim/device-bay-templates/", "device-bay"),
)


class EntryStatus(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    SKIPPED = "skipped"
    CONFLICT = "conflict"
    FAILED = "failed"


@dataclass
class EntryResult:
    id: str
    status: EntryStatus
    netbox_device_type_id: int | None = None
    message: str = ""


@dataclass
class BootstrapSummary:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    conflict: int = 0
    failed: int = 0

    def bump(self, status: EntryStatus) -> None:
        if status == EntryStatus.CREATED:
            self.created += 1
        elif status == EntryStatus.UPDATED:
            self.updated += 1
        elif status == EntryStatus.SKIPPED:
            self.skipped += 1
        elif status == EntryStatus.CONFLICT:
            self.conflict += 1
        elif status == EntryStatus.FAILED:
            self.failed += 1


@dataclass
class BootstrapReport:
    upstream_pin: str
    netbox_url: str
    entries: list[EntryResult] = field(default_factory=list)
    summary: BootstrapSummary = field(default_factory=BootstrapSummary)


def _slugify_manufacturer(name: str) -> str:
    return name.strip().lower().replace(" ", "-")


def _load_community_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"device type YAML root must be a mapping: {path}")
    return data


def _expected_component_count(yaml_data: dict[str, Any]) -> int:
    total = 0
    for key, _, _ in _COMPONENT_SPECS:
        items = yaml_data.get(key)
        if isinstance(items, list):
            total += len(items)
    return total


def _device_type_payload(
    yaml_data: dict[str, Any],
    *,
    manufacturer_id: int,
    expected_slug: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "manufacturer": manufacturer_id,
        "model": str(yaml_data["model"]),
        "slug": expected_slug,
    }
    if "u_height" in yaml_data:
        payload["u_height"] = yaml_data["u_height"]
    if "is_full_depth" in yaml_data:
        payload["is_full_depth"] = yaml_data["is_full_depth"]
    if yaml_data.get("part_number"):
        payload["part_number"] = str(yaml_data["part_number"])
    if "weight" in yaml_data:
        payload["weight"] = yaml_data["weight"]
    if "weight_unit" in yaml_data:
        payload["weight_unit"] = yaml_data["weight_unit"]
    if yaml_data.get("comments"):
        payload["comments"] = str(yaml_data["comments"])
    return payload


def _template_payload(
    device_type_id: int,
    component: dict[str, Any],
    *,
    kind: str,
) -> dict[str, Any]:
    name = component.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{kind} template missing name")
    payload: dict[str, Any] = {"device_type": device_type_id, "name": name.strip()}
    if component.get("type"):
        payload["type"] = component["type"]
    if component.get("label"):
        payload["label"] = component["label"]
    if kind == "interface" and "mgmt_only" in component:
        payload["mgmt_only"] = bool(component["mgmt_only"])
    if kind == "power-port":
        if "maximum_draw" in component:
            payload["maximum_draw"] = component["maximum_draw"]
        if "allocated_draw" in component:
            payload["allocated_draw"] = component["allocated_draw"]
    return payload


def _create_components(
    client: NetboxWriteClient,
    *,
    device_type_id: int,
    yaml_data: dict[str, Any],
) -> int:
    created = 0
    for yaml_key, api_path, kind in _COMPONENT_SPECS:
        items = yaml_data.get(yaml_key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            body = _template_payload(device_type_id, item, kind=kind)
            client.post(api_path, body)
            created += 1
    return created


def import_entry(
    client: NetboxWriteClient,
    manifest: DeviceTypeManifest,
    entry: ManifestEntry,
    *,
    force: bool = False,
) -> EntryResult:
    """Import one manifest entry into NetBox."""
    yaml_path = manifest.library_file(entry)
    try:
        yaml_data = _load_community_yaml(yaml_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return EntryResult(
            id=entry.id,
            status=EntryStatus.FAILED,
            message=f"failed to load YAML: {exc}",
        )

    manufacturer_name = str(yaml_data.get("manufacturer") or entry.vendor_normalized)
    mfg_slug = _slugify_manufacturer(manufacturer_name)
    expected_components = _expected_component_count(yaml_data)

    try:
        manufacturer = client.ensure_manufacturer(manufacturer_name, mfg_slug)
        mfg_id = manufacturer.get("id")
        if not isinstance(mfg_id, int):
            raise NetboxWriteError(f"manufacturer {mfg_slug!r} missing id")

        existing = client.get_by_slug("api/dcim/device-types/", entry.expected_slug)
        if existing:
            dt_id = existing.get("id")
            if not isinstance(dt_id, int):
                raise NetboxWriteError(f"device type {entry.expected_slug!r} missing id")
            existing_count = client.count_component_templates(dt_id)
            if existing_count == expected_components and expected_components > 0:
                return EntryResult(
                    id=entry.id,
                    status=EntryStatus.SKIPPED,
                    netbox_device_type_id=dt_id,
                    message="device type and components already present",
                )
            if existing_count != expected_components and not force:
                return EntryResult(
                    id=entry.id,
                    status=EntryStatus.CONFLICT,
                    netbox_device_type_id=dt_id,
                    message=(
                        f"existing type has {existing_count} templates, "
                        f"expected {expected_components}; use --force to recreate components"
                    ),
                )
            if force and existing_count != expected_components:
                _create_components(client, device_type_id=dt_id, yaml_data=yaml_data)
                return EntryResult(
                    id=entry.id,
                    status=EntryStatus.UPDATED,
                    netbox_device_type_id=dt_id,
                    message="components added under existing device type (--force)",
                )
            if existing_count == 0 and expected_components > 0:
                _create_components(client, device_type_id=dt_id, yaml_data=yaml_data)
                return EntryResult(
                    id=entry.id,
                    status=EntryStatus.UPDATED,
                    netbox_device_type_id=dt_id,
                    message="components added to existing device type",
                )
            return EntryResult(
                id=entry.id,
                status=EntryStatus.SKIPPED,
                netbox_device_type_id=dt_id,
                message="device type already exists",
            )

        body = _device_type_payload(
            yaml_data,
            manufacturer_id=mfg_id,
            expected_slug=entry.expected_slug,
        )
        created_dt = client.post("api/dcim/device-types/", body)
        if not isinstance(created_dt, dict):
            raise NetboxWriteError(f"unexpected device type create response for {entry.id!r}")
        dt_id = created_dt.get("id")
        if not isinstance(dt_id, int):
            raise NetboxWriteError(f"created device type missing id for {entry.id!r}")

        comp_created = _create_components(client, device_type_id=dt_id, yaml_data=yaml_data)
        _log.info(
            "devicetype_importer.created",
            entry_id=entry.id,
            slug=entry.expected_slug,
            components=comp_created,
        )
        return EntryResult(
            id=entry.id,
            status=EntryStatus.CREATED,
            netbox_device_type_id=dt_id,
            message=f"created device type with {comp_created} component templates",
        )
    except NetboxWriteError as exc:
        return EntryResult(
            id=entry.id,
            status=EntryStatus.FAILED,
            message=str(exc),
        )


def run_bootstrap(
    client: NetboxWriteClient,
    manifest: DeviceTypeManifest,
    *,
    netbox_url: str,
    force: bool = False,
) -> BootstrapReport:
    """Import all manifest entries."""
    report = BootstrapReport(upstream_pin=manifest.upstream_pin, netbox_url=netbox_url)
    for entry in manifest.entries:
        result = import_entry(client, manifest, entry, force=force)
        report.entries.append(result)
        report.summary.bump(result.status)
    return report
