"""US1 — management IP resolution unit tests."""

from __future__ import annotations

from gard.core.ipam_alignment_controller import resolve_mgmt_ip
from gard.integrations.netbox.alignment_manifest import load_alignment_manifest
from gard.integrations.netbox.ipam_collector import (
    AddressRecord,
    DeviceNetworkSnapshot,
    InterfaceRecord,
)


def _manifest(project_root):
    return load_alignment_manifest(repo_root=project_root)


def _snapshot(**kwargs) -> DeviceNetworkSnapshot:
    return DeviceNetworkSnapshot(netbox_device_id=1, **kwargs)


def test_primary_ip4_match(project_root) -> None:
    manifest = _manifest(project_root)
    snap = _snapshot(primary_ip4="10.0.0.1/24")
    res = resolve_mgmt_ip(snap, manifest)
    assert res.ip == "10.0.0.1"
    assert res.method == "primary_ip4"
    assert not res.ambiguous


def test_mismatch_candidates_ambiguous(project_root) -> None:
    manifest = _manifest(project_root)
    snap = _snapshot(
        primary_ip4="10.0.0.1/24",
        primary_ip6="2001:db8::1/128",
        interfaces=[
            InterfaceRecord(
                name="mgmt0",
                enabled=True,
                mode=None,
                mgmt_only=True,
                addresses=[AddressRecord("10.0.0.2/24", 4, True, None)],
            )
        ],
    )
    res = resolve_mgmt_ip(snap, manifest)
    assert res.ambiguous or res.ip in {"10.0.0.1", "10.0.0.2"}


def test_mgmt_interface_resolution(project_root) -> None:
    manifest = _manifest(project_root)
    snap = _snapshot(
        interfaces=[
            InterfaceRecord(
                name="mgmt0",
                enabled=True,
                mode=None,
                mgmt_only=True,
                addresses=[AddressRecord("192.168.1.10/24", 4, True, None)],
            )
        ],
    )
    res = resolve_mgmt_ip(snap, manifest)
    assert res.ip == "192.168.1.10"
    assert res.method == "mgmt_interface"


def test_fallback_used(project_root) -> None:
    manifest = _manifest(project_root)
    snap = _snapshot(
        interfaces=[
            InterfaceRecord(
                name="Gi0/0",
                enabled=True,
                mode="access",
                mgmt_only=False,
                addresses=[AddressRecord("172.16.0.5/24", 4, False, None)],
            )
        ],
    )
    res = resolve_mgmt_ip(snap, manifest)
    assert res.ip == "172.16.0.5"
    assert res.fallback_used


def test_name_pattern_resolution(project_root) -> None:
    manifest = _manifest(project_root)
    snap = _snapshot(
        interfaces=[
            InterfaceRecord(
                name="Loopback0",
                enabled=True,
                mode=None,
                mgmt_only=False,
                addresses=[AddressRecord("10.255.0.1/32", 4, True, None)],
            )
        ],
    )
    res = resolve_mgmt_ip(snap, manifest)
    assert res.ip == "10.255.0.1"
    assert res.method == "name_pattern"
