"""Unit tests for F10 write-back publisher."""

from __future__ import annotations

import uuid
from typing import Any

from gard.integrations.netbox.writeback_manifest import load_writeback_manifest
from gard.integrations.netbox.writeback_publisher import (
    DeviceLifecycleSnapshot,
    WritebackEntryStatus,
    _reconcile_tags,
    build_lifecycle_snapshot,
    publish_device_writeback,
)
from gard.models import Device
from gard.models._enums import LifecycleState


class FakeWriteClient:
    def __init__(self, device: dict[str, Any]) -> None:
        self._device = device
        self.patch_calls: list[dict[str, Any]] = []

    def get_device(self, device_id: int) -> dict[str, Any]:
        return dict(self._device)

    def patch_device(
        self,
        device_id: int,
        *,
        custom_fields: dict[str, Any] | None = None,
        tags: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.patch_calls.append(
            {"device_id": device_id, "custom_fields": custom_fields, "tags": tags}
        )
        if custom_fields:
            cf = self._device.setdefault("custom_fields", {})
            cf.update(custom_fields)
        if tags is not None:
            self._device["tags"] = tags
        return self._device


def _device(**kwargs: Any) -> Device:
    defaults = {
        "id": uuid.uuid4(),
        "hostname": "r-osl-001",
        "site": "oslo-dc1",
        "vendor_raw": "Cisco",
        "model_raw": "ISR1121",
        "source_system": "netbox",
        "lifecycle_state": LifecycleState.imported,
        "netbox_device_id": 101,
    }
    defaults.update(kwargs)
    return Device(**defaults)


def _snapshot(**kwargs: Any) -> DeviceLifecycleSnapshot:
    defaults = {
        "lifecycle_state": "imported",
        "compliance_summary": "outside_target: version_drift",
        "readiness_summary": "device is ready for uplift",
        "target_firmware": "17.9.4",
        "compliance_evaluated_at": "2026-06-01T12:00:00+00:00",
        "readiness_evaluated_at": "2026-06-01T12:00:00+00:00",
        "drift_outside_target": True,
        "readiness_blocked": False,
        "readiness_ready_for_uplift": True,
        "ipam_alignment_status": "unknown",
        "ipam_mismatch": False,
    }
    defaults.update(kwargs)
    return DeviceLifecycleSnapshot(**defaults)


def test_unknown_sentinel_when_no_evaluations(project_root) -> None:
    device = _device()
    snapshot = build_lifecycle_snapshot(
        device,
        compliance=None,
        readiness=None,
        unknown_sentinel="unknown",
    )
    assert snapshot.compliance_summary == "unknown"
    assert snapshot.readiness_summary == "unknown"
    assert snapshot.target_firmware == "unknown"


def test_custom_field_conflict_skips_patch(project_root) -> None:
    manifest = load_writeback_manifest(repo_root=project_root)
    client = FakeWriteClient(
        {
            "id": 101,
            "custom_fields": {"gard_lifecycle_state": "operator-edited"},
            "tags": [{"slug": "edge"}],
        }
    )
    entry = publish_device_writeback(
        client=client,
        manifest=manifest,
        device=_device(),
        snapshot=_snapshot(lifecycle_state="imported"),
    )
    assert entry.status == WritebackEntryStatus.conflict
    assert entry.conflicts
    assert client.patch_calls == []


def test_idempotent_unchanged_when_values_match(project_root) -> None:
    manifest = load_writeback_manifest(repo_root=project_root)
    snapshot = _snapshot()
    custom_fields = {
        mapping.netbox_field: {
            "lifecycle_state": snapshot.lifecycle_state,
            "compliance_summary": snapshot.compliance_summary,
            "readiness_summary": snapshot.readiness_summary,
            "target_firmware": snapshot.target_firmware,
            "compliance_evaluated_at": snapshot.compliance_evaluated_at,
            "readiness_evaluated_at": snapshot.readiness_evaluated_at,
            "ipam_alignment_status": snapshot.ipam_alignment_status,
        }[mapping.gard_source]
        for mapping in manifest.custom_fields
    }
    client = FakeWriteClient(
        {
            "id": 101,
            "custom_fields": custom_fields,
            "tags": [
                {"slug": "edge"},
                {"slug": "gard-managed"},
                {"slug": "gard-drift-outside-target"},
                {"slug": "gard-ready-for-uplift"},
            ],
        }
    )
    entry = publish_device_writeback(
        client=client,
        manifest=manifest,
        device=_device(),
        snapshot=snapshot,
    )
    assert entry.status == WritebackEntryStatus.unchanged
    assert client.patch_calls == []


def test_tag_reconcile_preserves_non_manifest_tags(project_root) -> None:
    manifest = load_writeback_manifest(repo_root=project_root)
    reconciled = _reconcile_tags(
        current_slugs=["edge", "gard-managed"],
        manifest=manifest,
        desired_manifest_tags={"gard-managed", "gard-drift-outside-target"},
    )
    assert reconciled == ["edge", "gard-drift-outside-target", "gard-managed"]


def test_removed_manifest_tag_reapplied(project_root) -> None:
    manifest = load_writeback_manifest(repo_root=project_root)
    client = FakeWriteClient(
        {
            "id": 101,
            "custom_fields": {},
            "tags": [{"slug": "edge"}],
        }
    )
    entry = publish_device_writeback(
        client=client,
        manifest=manifest,
        device=_device(),
        snapshot=_snapshot(),
    )
    assert entry.status == WritebackEntryStatus.updated
    assert client.patch_calls
    tag_slugs = [t["slug"] for t in client.patch_calls[0]["tags"]]
    assert "gard-managed" in tag_slugs
    assert "edge" in tag_slugs
