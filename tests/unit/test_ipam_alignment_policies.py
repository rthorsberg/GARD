"""US2/US3/US4 — IPAM alignment policy evaluation unit tests."""

from __future__ import annotations

import uuid

from gard.core.ipam_alignment_controller import (
    _evaluate_interfaces,
    _evaluate_mgmt_ip,
    _evaluate_vlan,
    _evaluate_vrf,
)
from gard.integrations.netbox.alignment_manifest import load_alignment_manifest
from gard.integrations.netbox.ipam_collector import (
    AddressRecord,
    DeviceNetworkSnapshot,
    InterfaceRecord,
    VlanRef,
    VrfRef,
)
from gard.models import Device
from gard.models._enums import AlignmentFindingKind, LifecycleState


class FakeClient:
    def list_vlan_groups(self, *, site_id: int | None = None):
        return [{"id": 1, "slug": "oslo-access"}]

    def list_vlans(self, *, site_id: int | None = None):
        return [{"id": 10, "group": {"id": 1}}]


def _device(**kwargs) -> Device:
    defaults = dict(
        id=uuid.uuid4(),
        hostname="r1",
        site="oslo",
        role="edge",
        vendor_raw="Cisco",
        model_raw="ISR",
        source_system="netbox",
        lifecycle_state=LifecycleState.imported,
        management_ip="10.0.0.1",
    )
    defaults.update(kwargs)
    return Device(**defaults)


def test_interface_missing_address(project_root) -> None:
    manifest = load_alignment_manifest(repo_root=project_root)
    device = _device()
    snap = DeviceNetworkSnapshot(
        netbox_device_id=1,
        site_slug="oslo",
        role_slug="edge",
        interfaces=[
            InterfaceRecord(
                name="Gi0/1",
                enabled=True,
                mode="access",
                mgmt_only=False,
                addresses=[],
            )
        ],
    )
    findings = _evaluate_interfaces(device, snap, manifest, {})
    kinds = {f.kind for f in findings}
    assert AlignmentFindingKind.interface_missing_address in kinds


def test_cross_device_conflict(project_root) -> None:
    manifest = load_alignment_manifest(repo_root=project_root)
    device = _device()
    snap = DeviceNetworkSnapshot(
        netbox_device_id=1,
        site_slug="oslo",
        role_slug="edge",
        interfaces=[
            InterfaceRecord(
                name="Gi0/1",
                enabled=True,
                mode="access",
                mgmt_only=False,
                addresses=[AddressRecord("10.1.1.1/24", 4, True, None)],
            )
        ],
    )
    shared = {"10.1.1.1": [(1, "Gi0/1"), (2, "Gi0/2")]}
    findings = _evaluate_interfaces(device, snap, manifest, shared)
    assert any(f.kind == AlignmentFindingKind.cross_device_address_conflict for f in findings)


def test_vrf_mismatch(project_root) -> None:
    manifest = load_alignment_manifest(repo_root=project_root)
    device = _device(site="oslo", role="edge")
    snap = DeviceNetworkSnapshot(
        netbox_device_id=1,
        site_slug="oslo",
        role_slug="edge",
        interfaces=[
            InterfaceRecord(
                name="mgmt0",
                enabled=True,
                mode=None,
                mgmt_only=True,
                vrf=VrfRef(id=1, name="default"),
                addresses=[],
            )
        ],
    )
    findings = _evaluate_vrf(device, snap, manifest)
    assert any(f.kind == AlignmentFindingKind.vrf_mismatch for f in findings)


def test_mgmt_ip_mismatch(project_root) -> None:
    manifest = load_alignment_manifest(repo_root=project_root)
    device = _device(management_ip="10.0.0.99")
    snap = DeviceNetworkSnapshot(netbox_device_id=1, primary_ip4="10.0.0.1/24")
    findings = _evaluate_mgmt_ip(device, snap, manifest)
    assert any(f.kind == AlignmentFindingKind.mgmt_ip_mismatch for f in findings)


def test_access_vlan_missing(project_root) -> None:
    manifest = load_alignment_manifest(repo_root=project_root)
    device = _device(site="oslo")
    snap = DeviceNetworkSnapshot(
        netbox_device_id=1,
        site_slug="oslo",
        site_id=1,
        interfaces=[
            InterfaceRecord(
                name="Gi0/2",
                enabled=True,
                mode="access",
                mgmt_only=False,
                addresses=[],
            )
        ],
    )
    findings = _evaluate_vlan(device, snap, manifest, FakeClient(), {})
    assert any(f.kind == AlignmentFindingKind.access_vlan_missing for f in findings)


def test_vlan_out_of_scope(project_root) -> None:
    manifest = load_alignment_manifest(repo_root=project_root)
    device = _device(site="oslo")
    snap = DeviceNetworkSnapshot(
        netbox_device_id=1,
        site_slug="oslo",
        site_id=1,
        interfaces=[
            InterfaceRecord(
                name="Gi0/3",
                enabled=True,
                mode="access",
                mgmt_only=False,
                untagged_vlan=VlanRef(id=999, vid=999, name="bad"),
                addresses=[],
            )
        ],
    )
    findings = _evaluate_vlan(device, snap, manifest, FakeClient(), {})
    assert any(f.kind == AlignmentFindingKind.vlan_out_of_scope for f in findings)
