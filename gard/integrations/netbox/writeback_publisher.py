"""F10 NetBox lifecycle write-back publisher."""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from gard.core import compliance_evaluation_controller as compliance_ctrl
from gard.core import readiness_evaluation_controller as readiness_ctrl
from gard.core.settings import Settings, get_settings
from gard.integrations.netbox.write_client import (
    NetboxWriteClient,
    NetboxWriteError,
    NetboxWriteNotConfigured,
)
from gard.integrations.netbox.writeback_manifest import (
    WritebackManifest,
    load_writeback_manifest,
)
from gard.models import ComplianceEvaluation, Device, ReadinessEvaluation, utcnow
from gard.models._enums import LifecycleState


class WritebackEntryStatus(enum.StrEnum):
    updated = "updated"
    skipped = "skipped"
    unchanged = "unchanged"
    conflict = "conflict"
    failed = "failed"


class WritebackPhase(enum.StrEnum):
    completed = "completed"
    partial = "partial"
    failed = "failed"
    skipped = "skipped"


@dataclass
class WritebackConflict:
    field: str
    expected: str
    actual: str


@dataclass
class WritebackEntry:
    device_id: uuid.UUID
    netbox_device_id: int
    status: WritebackEntryStatus
    message: str | None = None
    conflicts: list[WritebackConflict] = field(default_factory=list)


@dataclass
class WritebackSummary:
    updated: int = 0
    skipped: int = 0
    unchanged: int = 0
    conflict: int = 0
    failed: int = 0
    skipped_not_linked: int = 0


@dataclass
class WritebackReport:
    phase: WritebackPhase
    summary: WritebackSummary
    entries: list[WritebackEntry] = field(default_factory=list)


@dataclass(frozen=True)
class DeviceLifecycleSnapshot:
    lifecycle_state: str
    compliance_summary: str
    readiness_summary: str
    target_firmware: str
    compliance_evaluated_at: str
    readiness_evaluated_at: str
    drift_outside_target: bool
    readiness_blocked: bool
    readiness_ready_for_uplift: bool


def _format_dt(value: dt.datetime | None, *, unknown: str) -> str:
    if value is None:
        return unknown
    return value.astimezone(dt.UTC).isoformat()


def _compliance_summary(row: ComplianceEvaluation | None, *, unknown: str) -> str:
    if row is None:
        return unknown
    if row.compliance_state == "compliant":
        return f"compliant on {row.observed_version!r}"
    if row.primary_drift_type:
        return f"{row.compliance_state}: {row.primary_drift_type}"
    return row.compliance_state


def _readiness_summary(row: ReadinessEvaluation | None, *, unknown: str) -> str:
    if row is None:
        return unknown
    if row.readiness_state == "ready_for_uplift":
        return "device is ready for uplift"
    if row.readiness_state == "not_applicable":
        return "readiness is not applicable for this device"
    blockers = row.blockers or []
    req = sum(1 for b in blockers if b.get("severity") == "required")
    rec = sum(1 for b in blockers if b.get("severity") == "recommended")
    return f"blocked: {req} required + {rec} recommended blocker(s)"


def build_lifecycle_snapshot(
    device: Device,
    *,
    compliance: ComplianceEvaluation | None,
    readiness: ReadinessEvaluation | None,
    unknown_sentinel: str,
) -> DeviceLifecycleSnapshot:
    return DeviceLifecycleSnapshot(
        lifecycle_state=device.lifecycle_state.value
        if isinstance(device.lifecycle_state, LifecycleState)
        else str(device.lifecycle_state),
        compliance_summary=_compliance_summary(compliance, unknown=unknown_sentinel),
        readiness_summary=_readiness_summary(readiness, unknown=unknown_sentinel),
        target_firmware=(
            compliance.target_version
            if compliance and compliance.target_version
            else unknown_sentinel
        ),
        compliance_evaluated_at=_format_dt(
            compliance.evaluated_at if compliance else None,
            unknown=unknown_sentinel,
        ),
        readiness_evaluated_at=_format_dt(
            readiness.evaluated_at if readiness else None,
            unknown=unknown_sentinel,
        ),
        drift_outside_target=bool(
            compliance is not None and compliance.compliance_state == "outside_target"
        ),
        readiness_blocked=bool(readiness is not None and readiness.readiness_state == "blocked"),
        readiness_ready_for_uplift=bool(
            readiness is not None and readiness.readiness_state == "ready_for_uplift"
        ),
    )


def _source_value(snapshot: DeviceLifecycleSnapshot, gard_source: str) -> str:
    return {
        "lifecycle_state": snapshot.lifecycle_state,
        "compliance_summary": snapshot.compliance_summary,
        "readiness_summary": snapshot.readiness_summary,
        "target_firmware": snapshot.target_firmware,
        "compliance_evaluated_at": snapshot.compliance_evaluated_at,
        "readiness_evaluated_at": snapshot.readiness_evaluated_at,
    }[gard_source]


def _tag_applies(rule_apply_when: str, snapshot: DeviceLifecycleSnapshot) -> bool:
    if rule_apply_when == "always":
        return True
    if rule_apply_when == "drift_outside_target":
        return snapshot.drift_outside_target
    if rule_apply_when == "readiness_blocked":
        return snapshot.readiness_blocked
    if rule_apply_when == "readiness_ready_for_uplift":
        return snapshot.readiness_ready_for_uplift
    return False


def _normalize_cf_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _extract_tag_slugs(tags: Any) -> list[str]:
    if not isinstance(tags, list):
        return []
    slugs: list[str] = []
    for tag in tags:
        if isinstance(tag, dict) and tag.get("slug"):
            slugs.append(str(tag["slug"]))
        elif isinstance(tag, str):
            slugs.append(tag)
    return slugs


def _build_desired_custom_fields(
    manifest: WritebackManifest,
    snapshot: DeviceLifecycleSnapshot,
) -> dict[str, str]:
    return {
        mapping.netbox_field: _source_value(snapshot, mapping.gard_source)
        for mapping in manifest.custom_fields
    }


def _build_desired_manifest_tags(
    manifest: WritebackManifest,
    snapshot: DeviceLifecycleSnapshot,
) -> set[str]:
    desired: set[str] = set()
    for rule in manifest.tags:
        if _tag_applies(rule.apply_when, snapshot):
            desired.add(rule.slug)
    return desired


def _reconcile_tags(
    *,
    current_slugs: list[str],
    manifest: WritebackManifest,
    desired_manifest_tags: set[str],
) -> list[str]:
    managed = manifest.manifest_tag_slugs
    preserved = [slug for slug in current_slugs if slug not in managed]
    merged = preserved + sorted(desired_manifest_tags)
    return merged


def write_client_from_settings(settings: Settings | None = None) -> NetboxWriteClient:
    s = settings or get_settings()
    if s.netbox_url is None:
        raise NetboxWriteNotConfigured("GARD_NETBOX_URL is not set")
    token = s.resolved_netbox_write_token()
    if not token:
        raise NetboxWriteNotConfigured("GARD_NETBOX_WRITE_TOKEN is not set")
    return NetboxWriteClient(
        base_url=str(s.netbox_url),
        token=token,
        verify_tls=s.netbox_verify_tls,
        timeout_seconds=s.netbox_timeout_seconds,
    )


def publish_device_writeback(
    *,
    client: NetboxWriteClient,
    manifest: WritebackManifest,
    device: Device,
    snapshot: DeviceLifecycleSnapshot,
) -> WritebackEntry:
    nb_id = device.netbox_device_id
    if nb_id is None:
        raise ValueError("device has no netbox_device_id")

    desired_fields = _build_desired_custom_fields(manifest, snapshot)
    desired_tags = _build_desired_manifest_tags(manifest, snapshot)

    try:
        nb_device = client.get_device(nb_id)
    except NetboxWriteError as exc:
        return WritebackEntry(
            device_id=device.id,
            netbox_device_id=nb_id,
            status=WritebackEntryStatus.failed,
            message=str(exc),
        )

    current_fields_raw = nb_device.get("custom_fields") or {}
    if not isinstance(current_fields_raw, dict):
        current_fields_raw = {}

    conflicts: list[WritebackConflict] = []
    fields_to_write: dict[str, str] = {}

    for field_name, desired in desired_fields.items():
        actual_raw = current_fields_raw.get(field_name)
        actual = _normalize_cf_value(actual_raw)
        if actual and actual != desired:
            conflicts.append(WritebackConflict(field=field_name, expected=desired, actual=actual))
            continue
        fields_to_write[field_name] = desired

    current_tag_slugs = _extract_tag_slugs(nb_device.get("tags"))
    reconciled_tags = _reconcile_tags(
        current_slugs=current_tag_slugs,
        manifest=manifest,
        desired_manifest_tags=desired_tags,
    )

    fields_match = all(
        _normalize_cf_value(current_fields_raw.get(name)) == value
        for name, value in desired_fields.items()
        if not any(c.field == name for c in conflicts)
    )
    tags_match = sorted(current_tag_slugs) == sorted(reconciled_tags)

    if conflicts:
        return WritebackEntry(
            device_id=device.id,
            netbox_device_id=nb_id,
            status=WritebackEntryStatus.conflict,
            message="custom field conflict; skipped PATCH",
            conflicts=conflicts,
        )

    if fields_match and tags_match:
        return WritebackEntry(
            device_id=device.id,
            netbox_device_id=nb_id,
            status=WritebackEntryStatus.unchanged,
            message="NetBox already matches desired lifecycle mirror",
        )

    patch_fields = fields_to_write if not fields_match else None
    patch_tags = [{"slug": slug} for slug in reconciled_tags] if not tags_match else None

    try:
        client.patch_device(nb_id, custom_fields=patch_fields, tags=patch_tags)
    except NetboxWriteError as exc:
        return WritebackEntry(
            device_id=device.id,
            netbox_device_id=nb_id,
            status=WritebackEntryStatus.failed,
            message=str(exc),
        )

    return WritebackEntry(
        device_id=device.id,
        netbox_device_id=nb_id,
        status=WritebackEntryStatus.updated,
        message="lifecycle metadata written to NetBox",
    )


def run_writeback(
    *,
    session: Session,
    devices: list[Device],
    client: NetboxWriteClient | None = None,
    manifest: WritebackManifest | None = None,
    settings: Settings | None = None,
) -> WritebackReport:
    """Write lifecycle metadata to NetBox for linked devices in the sync batch."""
    cfg = settings or get_settings()
    m = manifest or load_writeback_manifest()
    wb_client = client or write_client_from_settings(cfg)

    summary = WritebackSummary()
    entries: list[WritebackEntry] = []

    for device in devices:
        if device.netbox_device_id is None:
            summary.skipped_not_linked += 1
            continue

        compliance = compliance_ctrl.latest_evaluation_for(session, device.id)
        readiness = readiness_ctrl.latest_evaluation_for(session, device.id)
        snapshot = build_lifecycle_snapshot(
            device,
            compliance=compliance,
            readiness=readiness,
            unknown_sentinel=m.unknown_sentinel,
        )

        entry = publish_device_writeback(
            client=wb_client,
            manifest=m,
            device=device,
            snapshot=snapshot,
        )
        entries.append(entry)

        if entry.status == WritebackEntryStatus.updated:
            summary.updated += 1
            device.netbox_last_writeback_at = utcnow()
        elif entry.status == WritebackEntryStatus.unchanged:
            summary.unchanged += 1
        elif entry.status == WritebackEntryStatus.skipped:
            summary.skipped += 1
        elif entry.status == WritebackEntryStatus.conflict:
            summary.conflict += 1
        elif entry.status == WritebackEntryStatus.failed:
            summary.failed += 1

    if summary.failed and (summary.updated or summary.unchanged or summary.conflict):
        phase = WritebackPhase.partial
    elif summary.failed:
        phase = WritebackPhase.failed
    else:
        phase = WritebackPhase.completed

    session.flush()
    return WritebackReport(phase=phase, summary=summary, entries=entries)


def skipped_writeback_report(*, reason: str) -> WritebackReport:
    return WritebackReport(
        phase=WritebackPhase.skipped,
        summary=WritebackSummary(),
        entries=[],
    )
