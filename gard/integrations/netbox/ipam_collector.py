"""F12 NetBox IPAM/DCIM data collector."""

from __future__ import annotations

import ipaddress
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from gard.integrations.netbox.client import NetboxClient


@dataclass(frozen=True)
class AddressRecord:
    address: str
    family: int
    primary: bool
    vrf: str | None


@dataclass(frozen=True)
class VlanRef:
    id: int
    vid: int
    name: str
    group_slug: str | None = None


@dataclass(frozen=True)
class VrfRef:
    id: int
    name: str
    rd: str | None = None


@dataclass
class InterfaceRecord:
    name: str
    enabled: bool
    mode: str | None
    mgmt_only: bool
    vrf: VrfRef | None = None
    untagged_vlan: VlanRef | None = None
    tagged_vlans: list[VlanRef] = field(default_factory=list)
    addresses: list[AddressRecord] = field(default_factory=list)


@dataclass
class DeviceNetworkSnapshot:
    netbox_device_id: int
    primary_ip4: str | None = None
    primary_ip6: str | None = None
    oob_ip: str | None = None
    site_slug: str | None = None
    site_id: int | None = None
    role_slug: str | None = None
    interfaces: list[InterfaceRecord] = field(default_factory=list)


def _nested_slug(value: dict[str, Any] | None) -> str | None:
    if not value:
        return None
    for key in ("slug", "name"):
        raw = value.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _ip_address(value: dict[str, Any] | None) -> str | None:
    if not value:
        return None
    addr = value.get("address")
    if isinstance(addr, str) and addr.strip():
        return addr.strip()
    return None


def _host_only(address: str) -> str:
    try:
        return str(ipaddress.ip_interface(address).ip)
    except ValueError:
        return address.split("/")[0]


def _parse_vlan(raw: dict[str, Any] | None) -> VlanRef | None:
    if not raw:
        return None
    vid = raw.get("vid")
    vlan_id = raw.get("id")
    name = raw.get("name")
    if not isinstance(vid, int) or not isinstance(vlan_id, int):
        return None
    group = raw.get("group") or {}
    return VlanRef(
        id=vlan_id,
        vid=vid,
        name=str(name) if name else str(vid),
        group_slug=_nested_slug(group if isinstance(group, dict) else None),
    )


def _parse_vrf(raw: dict[str, Any] | None) -> VrfRef | None:
    if not raw:
        return None
    vrf_id = raw.get("id")
    name = raw.get("name")
    if not isinstance(vrf_id, int):
        return None
    rd = raw.get("rd")
    return VrfRef(id=vrf_id, name=str(name) if name else "unknown", rd=str(rd) if rd else None)


def _normalize_interface(
    raw: dict[str, Any],
    addresses_by_iface: dict[int, list[AddressRecord]],
) -> InterfaceRecord:
    iface_id = raw.get("id")
    name = raw.get("name")
    addr_list = addresses_by_iface.get(iface_id, []) if isinstance(iface_id, int) else []
    tagged = [_parse_vlan(v) for v in (raw.get("tagged_vlans") or []) if isinstance(v, dict)]
    return InterfaceRecord(
        name=str(name) if name else "unknown",
        enabled=bool(raw.get("enabled", True)),
        mode=str(raw.get("mode")) if raw.get("mode") else None,
        mgmt_only=bool(raw.get("mgmt_only", False)),
        vrf=_parse_vrf(raw.get("vrf") if isinstance(raw.get("vrf"), dict) else None),
        untagged_vlan=_parse_vlan(
            raw.get("untagged_vlan") if isinstance(raw.get("untagged_vlan"), dict) else None
        ),
        tagged_vlans=[v for v in tagged if v is not None],
        addresses=addr_list,
    )


def _build_address_map(ip_rows: list[dict[str, Any]]) -> dict[int, list[AddressRecord]]:
    by_iface: dict[int, list[AddressRecord]] = {}
    for row in ip_rows:
        assigned = row.get("assigned_object")
        if not isinstance(assigned, dict):
            continue
        iface_id = assigned.get("id")
        addr = row.get("address")
        if not isinstance(iface_id, int) or not isinstance(addr, str):
            continue
        family = 6 if ":" in addr else 4
        vrf = row.get("vrf")
        vrf_name = _nested_slug(vrf if isinstance(vrf, dict) else None)
        rec = AddressRecord(
            address=addr,
            family=family,
            primary=bool(row.get("primary_for_parent", False)),
            vrf=vrf_name,
        )
        by_iface.setdefault(iface_id, []).append(rec)
    return by_iface


def collect_device_snapshot(client: NetboxClient, netbox_device_id: int) -> DeviceNetworkSnapshot:
    """Fetch interfaces and IP addresses for one NetBox device."""
    detail = client.get_device(netbox_device_id)
    site = detail.get("site") if isinstance(detail.get("site"), dict) else None
    role = detail.get("role") if isinstance(detail.get("role"), dict) else None
    iface_rows = client.list_interfaces(device_id=netbox_device_id)
    ip_rows = client.list_ip_addresses(device_id=netbox_device_id)
    addr_map = _build_address_map(ip_rows)
    interfaces = [_normalize_interface(row, addr_map) for row in iface_rows]
    return DeviceNetworkSnapshot(
        netbox_device_id=netbox_device_id,
        primary_ip4=_ip_address(
            detail.get("primary_ip4") if isinstance(detail.get("primary_ip4"), dict) else None
        ),
        primary_ip6=_ip_address(
            detail.get("primary_ip6") if isinstance(detail.get("primary_ip6"), dict) else None
        ),
        oob_ip=_ip_address(
            detail.get("oob_ip") if isinstance(detail.get("oob_ip"), dict) else None
        ),
        site_slug=_nested_slug(site),
        site_id=site.get("id")
        if isinstance(site, dict) and isinstance(site.get("id"), int)
        else None,
        role_slug=_nested_slug(role),
        interfaces=interfaces,
    )


def collect_device_snapshots(
    client: NetboxClient,
    netbox_device_ids: list[int],
    *,
    concurrency: int = 8,
) -> dict[int, DeviceNetworkSnapshot]:
    """Batch-fetch network snapshots keyed by NetBox device id."""
    if not netbox_device_ids:
        return {}
    out: dict[int, DeviceNetworkSnapshot] = {}
    workers = min(max(concurrency, 1), len(netbox_device_ids))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(collect_device_snapshot, client, nb_id): nb_id
            for nb_id in netbox_device_ids
        }
        for fut in as_completed(futures):
            nb_id = futures[fut]
            out[nb_id] = fut.result()
    return out


def interface_to_json(iface: InterfaceRecord) -> dict[str, Any]:
    return {
        "name": iface.name,
        "enabled": iface.enabled,
        "mode": iface.mode,
        "mgmt_only": iface.mgmt_only,
        "vrf": (
            {"id": iface.vrf.id, "name": iface.vrf.name, "rd": iface.vrf.rd} if iface.vrf else None
        ),
        "untagged_vlan": (
            {
                "id": iface.untagged_vlan.id,
                "vid": iface.untagged_vlan.vid,
                "name": iface.untagged_vlan.name,
            }
            if iface.untagged_vlan
            else None
        ),
        "tagged_vlans": [{"id": v.id, "vid": v.vid, "name": v.name} for v in iface.tagged_vlans],
        "addresses": [
            {
                "address": a.address,
                "family": a.family,
                "primary": a.primary,
                "vrf": a.vrf,
            }
            for a in iface.addresses
        ],
    }


def compile_patterns(patterns: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p) for p in patterns)


def detect_shared_addresses(
    snapshots: dict[int, DeviceNetworkSnapshot],
) -> dict[str, list[tuple[int, str]]]:
    """Map host IP -> [(netbox_device_id, interface_name), ...]."""
    hosts: dict[str, list[tuple[int, str]]] = {}
    for nb_id, snap in snapshots.items():
        for iface in snap.interfaces:
            for addr in iface.addresses:
                host = _host_only(addr.address)
                hosts.setdefault(host, []).append((nb_id, iface.name))
    return {h: refs for h, refs in hosts.items() if len(refs) > 1}


def site_vlan_ids(
    client: NetboxClient,
    *,
    site_id: int,
    group_slug: str,
) -> set[int]:
    groups = client.list_vlan_groups(site_id=site_id)
    group_id: int | None = None
    for g in groups:
        if _nested_slug(g) == group_slug:
            gid = g.get("id")
            if isinstance(gid, int):
                group_id = gid
                break
    if group_id is None:
        return set()
    vlans = client.list_vlans(site_id=site_id)
    return {
        v["id"]
        for v in vlans
        if isinstance(v.get("id"), int)
        and isinstance(v.get("group"), dict)
        and v["group"].get("id") == group_id
    }
