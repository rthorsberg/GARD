"""F12 IPAM/DCIM alignment controller."""

from __future__ import annotations

import ipaddress
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.core import audit as audit_emit
from gard.core import evidence as evidence_emit
from gard.core.rbac import Principal
from gard.core.settings import Settings, get_settings
from gard.integrations.netbox.alignment_manifest import (
    AlignmentManifestError,
    AlignmentPolicyManifest,
    InterfacePolicy,
    load_alignment_manifest,
)
from gard.integrations.netbox.client import NetboxClient
from gard.integrations.netbox.ipam_collector import (
    DeviceNetworkSnapshot,
    InterfaceRecord,
    collect_device_snapshots,
    compile_patterns,
    detect_shared_addresses,
    interface_to_json,
    site_vlan_ids,
)
from gard.models import (
    Device,
    DeviceNetworkContext,
    IpamAlignmentFinding,
    IpamAlignmentRun,
    utcnow,
)
from gard.models._enums import (
    AlignmentFindingKind,
    AlignmentFindingSeverity,
    AlignmentFindingStatus,
    AuditResult,
    EvidenceType,
    IpamAlignmentRunStatus,
)

DEFAULT_SEVERITIES: dict[AlignmentFindingKind, AlignmentFindingSeverity] = {
    AlignmentFindingKind.mgmt_ip_match: AlignmentFindingSeverity.info,
    AlignmentFindingKind.mgmt_ip_mismatch: AlignmentFindingSeverity.error,
    AlignmentFindingKind.mgmt_ip_missing_in_netbox: AlignmentFindingSeverity.error,
    AlignmentFindingKind.mgmt_ip_missing_in_gard: AlignmentFindingSeverity.warning,
    AlignmentFindingKind.mgmt_ip_ambiguous: AlignmentFindingSeverity.error,
    AlignmentFindingKind.mgmt_ip_fallback_used: AlignmentFindingSeverity.info,
    AlignmentFindingKind.interface_ip_bound: AlignmentFindingSeverity.info,
    AlignmentFindingKind.interface_missing_address: AlignmentFindingSeverity.error,
    AlignmentFindingKind.prefix_vrf_scope_mismatch: AlignmentFindingSeverity.error,
    AlignmentFindingKind.cross_device_address_conflict: AlignmentFindingSeverity.error,
    AlignmentFindingKind.shared_address: AlignmentFindingSeverity.info,
    AlignmentFindingKind.vrf_mismatch: AlignmentFindingSeverity.error,
    AlignmentFindingKind.vrf_orphaned_in_site: AlignmentFindingSeverity.info,
    AlignmentFindingKind.access_vlan_missing: AlignmentFindingSeverity.error,
    AlignmentFindingKind.vlan_out_of_scope: AlignmentFindingSeverity.error,
    AlignmentFindingKind.vlan_aligned: AlignmentFindingSeverity.info,
    AlignmentFindingKind.overlay_rt_aligned: AlignmentFindingSeverity.info,
    AlignmentFindingKind.rt_missing_on_interface: AlignmentFindingSeverity.error,
    AlignmentFindingKind.rt_import_missing: AlignmentFindingSeverity.error,
    AlignmentFindingKind.rt_export_missing: AlignmentFindingSeverity.error,
    AlignmentFindingKind.l2vpn_module_unavailable: AlignmentFindingSeverity.info,
}


@dataclass(frozen=True)
class MgmtIpResolution:
    ip: str | None
    method: str | None
    ambiguous: bool = False
    fallback_used: bool = False
    candidates: tuple[str, ...] = ()


@dataclass
class FindingDraft:
    kind: AlignmentFindingKind
    device_id: uuid.UUID
    status: AlignmentFindingStatus = AlignmentFindingStatus.open
    interface_name: str | None = None
    netbox_observed: dict[str, Any] | None = None
    gard_observed: dict[str, Any] | None = None
    remediation_hint: str | None = None


@dataclass
class IpamAlignmentSummary:
    devices_checked: int = 0
    aligned_count: int = 0
    mismatch_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    findings_by_kind: dict[str, int] = field(default_factory=dict)
    l2vpn_available: bool = False


@dataclass
class IpamAlignmentEntry:
    device_id: uuid.UUID
    netbox_device_id: int
    overall_status: str
    finding_count: int
    top_kinds: list[str] = field(default_factory=list)


@dataclass
class IpamAlignmentReport:
    phase: IpamAlignmentRunStatus
    run_id: uuid.UUID | None
    summary: IpamAlignmentSummary
    entries: list[IpamAlignmentEntry] = field(default_factory=list)


def _host_only(address: str) -> str:
    try:
        return str(ipaddress.ip_interface(address).ip)
    except ValueError:
        return address.split("/")[0]


def _gard_mgmt_ip(device: Device) -> str | None:
    if device.management_ip is None:
        return None
    return _host_only(str(device.management_ip))


def _iface_addresses(iface: InterfaceRecord, *, prefer_ipv4: bool) -> list[str]:
    addrs = [_host_only(a.address) for a in iface.addresses]
    if not addrs:
        return []
    if prefer_ipv4:
        v4 = [a for a, raw in zip(addrs, iface.addresses, strict=True) if raw.family == 4]
        if v4:
            return v4
    return addrs


def resolve_mgmt_ip(
    snapshot: DeviceNetworkSnapshot,
    manifest: AlignmentPolicyManifest,
) -> MgmtIpResolution:
    """Resolve canonical NetBox management IP per research R-2."""
    prefer_ipv4 = manifest.mgmt_ip.prefer_ipv4
    patterns = compile_patterns(manifest.mgmt_ip.interface_name_patterns)
    candidates: list[tuple[int, str, str]] = []

    def add(priority: int, method: str, ip: str | None) -> None:
        if ip:
            candidates.append((priority, method, _host_only(ip)))

    if prefer_ipv4 and snapshot.primary_ip4:
        add(1, "primary_ip4", snapshot.primary_ip4)
    elif snapshot.primary_ip6:
        add(1, "primary_ip6", snapshot.primary_ip6)
    if not prefer_ipv4 and snapshot.primary_ip6:
        add(1, "primary_ip6", snapshot.primary_ip6)
    if snapshot.oob_ip:
        add(2, "oob_ip", snapshot.oob_ip)

    for iface in snapshot.interfaces:
        if not iface.enabled:
            continue
        ips = _iface_addresses(iface, prefer_ipv4=prefer_ipv4)
        if iface.mgmt_only and ips:
            for ip in ips:
                add(3, "mgmt_interface", ip)
        if ips and any(p.search(iface.name) for p in patterns):
            for ip in ips:
                add(4, "name_pattern", ip)

    if not candidates:
        for iface in snapshot.interfaces:
            if not iface.enabled:
                continue
            ips = _iface_addresses(iface, prefer_ipv4=prefer_ipv4)
            for ip in ips:
                add(5, "fallback", ip)

    if not candidates:
        return MgmtIpResolution(ip=None, method=None)

    min_priority = min(c[0] for c in candidates)
    top = [c for c in candidates if c[0] == min_priority]
    unique_ips = {c[2] for c in top}
    if len(unique_ips) > 1:
        return MgmtIpResolution(
            ip=None,
            method=top[0][1],
            ambiguous=True,
            candidates=tuple(sorted(unique_ips)),
        )
    method = top[0][1]
    ip = top[0][2]
    return MgmtIpResolution(
        ip=ip,
        method=method,
        fallback_used=(method == "fallback"),
        candidates=(ip,),
    )


def _severity_for(
    kind: AlignmentFindingKind,
    manifest: AlignmentPolicyManifest,
) -> AlignmentFindingSeverity:
    override = manifest.severity_overrides.get(kind.value)
    if override:
        return AlignmentFindingSeverity(override)
    return DEFAULT_SEVERITIES[kind]


def _policy_matches(policy: InterfacePolicy, *, site: str | None, role: str | None, name: str) -> bool:
    if policy.site != "*" and policy.site != site:
        return False
    if policy.role != "*" and policy.role != role:
        return False
    try:
        return bool(re.search(policy.interface_pattern, name))
    except re.error:
        return False


def _evaluate_mgmt_ip(
    device: Device,
    snapshot: DeviceNetworkSnapshot,
    manifest: AlignmentPolicyManifest,
) -> list[FindingDraft]:
    resolution = resolve_mgmt_ip(snapshot, manifest)
    gard_ip = _gard_mgmt_ip(device)
    findings: list[FindingDraft] = []

    if resolution.ambiguous:
        findings.append(
            FindingDraft(
                kind=AlignmentFindingKind.mgmt_ip_ambiguous,
                device_id=device.id,
                netbox_observed={"candidates": list(resolution.candidates)},
                gard_observed={"management_ip": gard_ip},
                remediation_hint="Resolve duplicate management IP candidates in NetBox",
            )
        )
        return findings

    netbox_ip = resolution.ip
    if resolution.fallback_used and netbox_ip:
        findings.append(
            FindingDraft(
                kind=AlignmentFindingKind.mgmt_ip_fallback_used,
                device_id=device.id,
                status=AlignmentFindingStatus.passed,
                netbox_observed={"resolved_mgmt_ip": netbox_ip, "method": resolution.method},
            )
        )

    if netbox_ip and gard_ip:
        if netbox_ip == gard_ip:
            findings.append(
                FindingDraft(
                    kind=AlignmentFindingKind.mgmt_ip_match,
                    device_id=device.id,
                    status=AlignmentFindingStatus.passed,
                    netbox_observed={"resolved_mgmt_ip": netbox_ip},
                    gard_observed={"management_ip": gard_ip},
                )
            )
        else:
            findings.append(
                FindingDraft(
                    kind=AlignmentFindingKind.mgmt_ip_mismatch,
                    device_id=device.id,
                    netbox_observed={"resolved_mgmt_ip": netbox_ip, "method": resolution.method},
                    gard_observed={"management_ip": gard_ip},
                    remediation_hint="Align GARD management_ip with NetBox or update NetBox primary/mgmt assignment",
                )
            )
    elif gard_ip and not netbox_ip:
        findings.append(
            FindingDraft(
                kind=AlignmentFindingKind.mgmt_ip_missing_in_netbox,
                device_id=device.id,
                gard_observed={"management_ip": gard_ip},
            )
        )
    elif netbox_ip and not gard_ip:
        findings.append(
            FindingDraft(
                kind=AlignmentFindingKind.mgmt_ip_missing_in_gard,
                device_id=device.id,
                netbox_observed={"resolved_mgmt_ip": netbox_ip, "method": resolution.method},
            )
        )
    elif manifest.mgmt_ip.require_assignment:
        findings.append(
            FindingDraft(
                kind=AlignmentFindingKind.mgmt_ip_missing_in_netbox,
                device_id=device.id,
            )
        )
    return findings


def _evaluate_interfaces(
    device: Device,
    snapshot: DeviceNetworkSnapshot,
    manifest: AlignmentPolicyManifest,
    shared_hosts: dict[str, list[tuple[int, str]]],
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    site = snapshot.site_slug or device.site
    role = snapshot.role_slug or device.role

    for iface in snapshot.interfaces:
        if not iface.enabled:
            continue
        for policy in manifest.interface_policies:
            if not _policy_matches(policy, site=site, role=role, name=iface.name):
                continue
            if policy.require_ip:
                if iface.addresses:
                    findings.append(
                        FindingDraft(
                            kind=AlignmentFindingKind.interface_ip_bound,
                            device_id=device.id,
                            status=AlignmentFindingStatus.passed,
                            interface_name=iface.name,
                            netbox_observed={"addresses": [a.address for a in iface.addresses]},
                        )
                    )
                else:
                    findings.append(
                        FindingDraft(
                            kind=AlignmentFindingKind.interface_missing_address,
                            device_id=device.id,
                            interface_name=iface.name,
                            remediation_hint=f"Assign IP to {iface.name} per policy {policy.id}",
                        )
                    )
            for addr in iface.addresses:
                host = _host_only(addr.address)
                refs = shared_hosts.get(host, [])
                cross_device = [r for r in refs if r[0] != snapshot.netbox_device_id]
                if cross_device:
                    findings.append(
                        FindingDraft(
                            kind=AlignmentFindingKind.cross_device_address_conflict,
                            device_id=device.id,
                            interface_name=iface.name,
                            netbox_observed={"address": addr.address, "also_on": cross_device},
                        )
                    )
                elif len(refs) > 1:
                    findings.append(
                        FindingDraft(
                            kind=AlignmentFindingKind.shared_address,
                            device_id=device.id,
                            status=AlignmentFindingStatus.passed,
                            interface_name=iface.name,
                            netbox_observed={"address": addr.address},
                        )
                    )
                if iface.vrf and addr.vrf and iface.vrf.name != addr.vrf:
                    findings.append(
                        FindingDraft(
                            kind=AlignmentFindingKind.prefix_vrf_scope_mismatch,
                            device_id=device.id,
                            interface_name=iface.name,
                            netbox_observed={"interface_vrf": iface.vrf.name, "address_vrf": addr.vrf},
                        )
                    )
    return findings


def _evaluate_vrf(
    device: Device,
    snapshot: DeviceNetworkSnapshot,
    manifest: AlignmentPolicyManifest,
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    site = snapshot.site_slug or device.site
    role = snapshot.role_slug or device.role
    for exp in manifest.vrf_expectations:
        if exp.site != site:
            continue
        if exp.role != "*" and exp.role != role:
            continue
        pattern = re.compile(exp.interface_pattern)
        for iface in snapshot.interfaces:
            if not iface.enabled or not pattern.search(iface.name):
                continue
            actual = iface.vrf.name if iface.vrf else None
            if actual == exp.expected_vrf:
                continue
            findings.append(
                FindingDraft(
                    kind=AlignmentFindingKind.vrf_mismatch,
                    device_id=device.id,
                    interface_name=iface.name,
                    netbox_observed={"vrf": actual},
                    gard_observed={"expected_vrf": exp.expected_vrf, "policy_id": exp.id},
                )
            )
    return findings


def _evaluate_vlan(
    device: Device,
    snapshot: DeviceNetworkSnapshot,
    manifest: AlignmentPolicyManifest,
    client: NetboxClient,
    vlan_scope_cache: dict[tuple[int, str], set[int]],
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    site = snapshot.site_slug or device.site
    for exp in manifest.vlan_expectations:
        if exp.site != site:
            continue
        access_pattern = (
            re.compile(exp.access_interface_pattern)
            if exp.access_interface_pattern
            else None
        )
        scope_key = (snapshot.site_id or 0, exp.vlan_group_slug)
        if scope_key not in vlan_scope_cache and snapshot.site_id is not None:
            vlan_scope_cache[scope_key] = site_vlan_ids(
                client,
                site_id=snapshot.site_id,
                group_slug=exp.vlan_group_slug,
            )
        allowed = vlan_scope_cache.get(scope_key, set())

        for iface in snapshot.interfaces:
            if not iface.enabled:
                continue
            if access_pattern and iface.mode == "access":
                if not access_pattern.search(iface.name):
                    continue
                if iface.untagged_vlan is None:
                    findings.append(
                        FindingDraft(
                            kind=AlignmentFindingKind.access_vlan_missing,
                            device_id=device.id,
                            interface_name=iface.name,
                        )
                    )
                elif allowed and iface.untagged_vlan.id not in allowed:
                    findings.append(
                        FindingDraft(
                            kind=AlignmentFindingKind.vlan_out_of_scope,
                            device_id=device.id,
                            interface_name=iface.name,
                            netbox_observed={"vlan_id": iface.untagged_vlan.id},
                        )
                    )
                else:
                    findings.append(
                        FindingDraft(
                            kind=AlignmentFindingKind.vlan_aligned,
                            device_id=device.id,
                            status=AlignmentFindingStatus.passed,
                            interface_name=iface.name,
                        )
                    )
    return findings


def skipped_alignment_report(*, reason: str) -> IpamAlignmentReport:
    return IpamAlignmentReport(
        phase=IpamAlignmentRunStatus.skipped,
        run_id=None,
        summary=IpamAlignmentSummary(),
        entries=[],
    )


def manifest_from_settings(settings: Settings | None = None) -> AlignmentPolicyManifest:
    s = settings or get_settings()
    if s.netbox_alignment_manifest_path:
        return load_alignment_manifest(manifest_path=Path(s.netbox_alignment_manifest_path))
    return load_alignment_manifest()


def run_alignment(
    *,
    session: Session,
    audit_session: Session,
    sync_run_id: uuid.UUID,
    devices: list[Device],
    client: NetboxClient,
    principal: Principal,
    correlation_id: str,
    manifest: AlignmentPolicyManifest | None = None,
    settings: Settings | None = None,
) -> IpamAlignmentReport:
    """Run IPAM alignment for NetBox-linked devices after reconcile."""
    s = settings or get_settings()
    actor = principal.subject or "system"
    started = utcnow()

    audit_emit.emit(
        session=audit_session,
        action="netbox.ipam_alignment.started",
        object_type="IpamAlignmentRun",
        object_id="pending",
        principal=principal,
        correlation_id=correlation_id,
        after={"sync_run_id": str(sync_run_id), "device_count": len(devices)},
    )

    linked = [d for d in devices if d.netbox_device_id is not None]
    if not linked:
        run = IpamAlignmentRun(
            id=uuid.uuid4(),
            netbox_sync_run_id=sync_run_id,
            status=IpamAlignmentRunStatus.skipped,
            started_at=started,
            completed_at=utcnow(),
            correlation_id=correlation_id,
            actor=actor,
        )
        session.add(run)
        session.flush()
        audit_emit.emit(
            session=audit_session,
            action="netbox.ipam_alignment.completed",
            object_type="IpamAlignmentRun",
            object_id=str(run.id),
            principal=principal,
            correlation_id=correlation_id,
            after={"status": "skipped", "reason": "no_linked_devices"},
        )
        return IpamAlignmentReport(
            phase=IpamAlignmentRunStatus.skipped,
            run_id=run.id,
            summary=IpamAlignmentSummary(),
        )

    try:
        policy = manifest or manifest_from_settings(s)
    except AlignmentManifestError as exc:
        run = IpamAlignmentRun(
            id=uuid.uuid4(),
            netbox_sync_run_id=sync_run_id,
            status=IpamAlignmentRunStatus.failed,
            started_at=started,
            completed_at=utcnow(),
            correlation_id=correlation_id,
            actor=actor,
        )
        session.add(run)
        session.flush()
        audit_emit.emit(
            session=audit_session,
            action="netbox.ipam_alignment.failed",
            object_type="IpamAlignmentRun",
            object_id=str(run.id),
            principal=principal,
            result=AuditResult.failure,
            correlation_id=correlation_id,
            after={"error": str(exc)},
        )
        return IpamAlignmentReport(
            phase=IpamAlignmentRunStatus.failed,
            run_id=run.id,
            summary=IpamAlignmentSummary(),
        )

    run = IpamAlignmentRun(
        id=uuid.uuid4(),
        netbox_sync_run_id=sync_run_id,
        status=IpamAlignmentRunStatus.partial,
        started_at=started,
        correlation_id=correlation_id,
        actor=actor,
    )
    session.add(run)
    session.flush()

    nb_ids = [d.netbox_device_id for d in linked if d.netbox_device_id is not None]
    snapshots = collect_device_snapshots(
        client,
        nb_ids,
        concurrency=s.netbox_ipam_prefetch_concurrency,
    )
    shared_hosts = detect_shared_addresses(snapshots)
    l2vpn_available = client.probe_l2vpn_available()
    run.l2vpn_available = l2vpn_available

    all_drafts: list[FindingDraft] = []
    vlan_scope_cache: dict[tuple[int, str], set[int]] = {}
    device_findings: dict[uuid.UUID, list[FindingDraft]] = {}

    if not l2vpn_available:
        all_drafts.append(
            FindingDraft(
                kind=AlignmentFindingKind.l2vpn_module_unavailable,
                device_id=linked[0].id,
                status=AlignmentFindingStatus.passed,
                netbox_observed={"l2vpn_available": False},
            )
        )

    for device in linked:
        nb_id = device.netbox_device_id
        if nb_id is None:
            continue
        snapshot = snapshots.get(nb_id)
        if snapshot is None:
            continue
        drafts: list[FindingDraft] = []
        resolution = resolve_mgmt_ip(snapshot, policy)
        drafts.extend(_evaluate_mgmt_ip(device, snapshot, policy))
        drafts.extend(_evaluate_interfaces(device, snapshot, policy, shared_hosts))
        drafts.extend(_evaluate_vrf(device, snapshot, policy))
        drafts.extend(_evaluate_vlan(device, snapshot, policy, client, vlan_scope_cache))
        device_findings[device.id] = drafts
        all_drafts.extend(drafts)

        ctx = DeviceNetworkContext(
            id=uuid.uuid4(),
            run_id=run.id,
            device_id=device.id,
            netbox_device_id=nb_id,
            primary_ip4=snapshot.primary_ip4,
            primary_ip6=snapshot.primary_ip6,
            resolved_mgmt_ip=resolution.ip,
            mgmt_resolution_method=resolution.method,
            interfaces=[interface_to_json(i) for i in snapshot.interfaces],
            overlay_bindings=[],
            captured_at=utcnow(),
        )
        session.add(ctx)

        open_kinds = [d.kind for d in drafts if d.status == AlignmentFindingStatus.open]
        device.netbox_last_alignment_at = utcnow()
        if any(
            _severity_for(d.kind, policy) == AlignmentFindingSeverity.error
            for d in drafts
            if d.status == AlignmentFindingStatus.open
        ) or open_kinds:
            device.netbox_alignment_status = "mismatch"
        elif drafts:
            device.netbox_alignment_status = "aligned"
        else:
            device.netbox_alignment_status = "unknown"

    summary = IpamAlignmentSummary(devices_checked=len(linked), l2vpn_available=l2vpn_available)
    entries: list[IpamAlignmentEntry] = []

    for draft in all_drafts:
        severity = _severity_for(draft.kind, policy)
        if draft.status == AlignmentFindingStatus.open:
            if severity == AlignmentFindingSeverity.error:
                summary.error_count += 1
            elif severity == AlignmentFindingSeverity.warning:
                summary.warning_count += 1
            else:
                summary.info_count += 1
        summary.findings_by_kind[draft.kind.value] = (
            summary.findings_by_kind.get(draft.kind.value, 0) + 1
        )
        finding = IpamAlignmentFinding(
            id=uuid.uuid4(),
            run_id=run.id,
            device_id=draft.device_id,
            kind=draft.kind,
            severity=severity,
            status=draft.status,
            netbox_observed=draft.netbox_observed,
            gard_observed=draft.gard_observed,
            remediation_hint=draft.remediation_hint,
            interface_name=draft.interface_name,
        )
        session.add(finding)

    for device in linked:
        drafts = device_findings.get(device.id, [])
        open_count = sum(1 for d in drafts if d.status == AlignmentFindingStatus.open)
        error_open = any(
            d.status == AlignmentFindingStatus.open
            and _severity_for(d.kind, policy) == AlignmentFindingSeverity.error
            for d in drafts
        )
        if error_open or open_count:
            summary.mismatch_count += 1
            overall = "mismatch"
        elif drafts:
            summary.aligned_count += 1
            overall = "aligned"
        else:
            overall = "unknown"
        kinds = [d.kind.value for d in drafts if d.status == AlignmentFindingStatus.open][:3]
        entries.append(
            IpamAlignmentEntry(
                device_id=device.id,
                netbox_device_id=device.netbox_device_id or 0,
                overall_status=overall,
                finding_count=len(drafts),
                top_kinds=kinds,
            )
        )

    run.devices_checked = len(linked)
    run.findings_error_count = summary.error_count
    run.findings_warning_count = summary.warning_count
    run.findings_info_count = summary.info_count
    run.completed_at = utcnow()
    run.status = (
        IpamAlignmentRunStatus.partial
        if summary.error_count
        else IpamAlignmentRunStatus.completed
    )

    audit_emit.emit(
        session=audit_session,
        action="netbox.ipam_alignment.completed",
        object_type="IpamAlignmentRun",
        object_id=str(run.id),
        principal=principal,
        correlation_id=correlation_id,
        after={
            "devices_checked": summary.devices_checked,
            "error_count": summary.error_count,
            "warning_count": summary.warning_count,
        },
    )
    evidence_emit.emit(
        session=audit_session,
        evidence_type=EvidenceType.netbox_ipam_alignment,
        subject_type="IpamAlignmentRun",
        subject_id=str(run.id),
        principal=principal,
        after_state={
            "sync_run_id": str(sync_run_id),
            "devices_checked": summary.devices_checked,
            "error_count": summary.error_count,
            "warning_count": summary.warning_count,
            "info_count": summary.info_count,
        },
        references={"correlation_id": correlation_id},
    )
    session.flush()

    return IpamAlignmentReport(
        phase=run.status,
        run_id=run.id,
        summary=summary,
        entries=entries[:100],
    )


def get_latest_network_context(
    session: Session,
    device_id: uuid.UUID,
) -> DeviceNetworkContext | None:
    return session.scalar(
        select(DeviceNetworkContext)
        .where(DeviceNetworkContext.device_id == device_id)
        .order_by(DeviceNetworkContext.captured_at.desc())
        .limit(1)
    )


def list_findings(
    session: Session,
    *,
    run_id: uuid.UUID | None = None,
    device_id: uuid.UUID | None = None,
    severity: AlignmentFindingSeverity | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[IpamAlignmentFinding], int]:
    stmt = select(IpamAlignmentFinding)
    if run_id is not None:
        stmt = stmt.where(IpamAlignmentFinding.run_id == run_id)
    if device_id is not None:
        stmt = stmt.where(IpamAlignmentFinding.device_id == device_id)
    if severity is not None:
        stmt = stmt.where(IpamAlignmentFinding.severity == severity)
    stmt = stmt.order_by(IpamAlignmentFinding.created_at.desc()).offset(offset).limit(limit)
    rows = list(session.scalars(stmt))
    return rows, len(rows)
