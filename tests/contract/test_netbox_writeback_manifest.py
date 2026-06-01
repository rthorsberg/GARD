"""Contract tests for F10 write-back manifest."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from gard.integrations.netbox.writeback_manifest import (
    WritebackManifestError,
    load_writeback_manifest,
)

REQUIRED_GARD_SOURCES = frozenset(
    {
        "lifecycle_state",
        "compliance_summary",
        "readiness_summary",
        "target_firmware",
        "compliance_evaluated_at",
        "readiness_evaluated_at",
    }
)

REQUIRED_TAG_SLUGS = frozenset(
    {
        "gard-managed",
        "gard-drift-outside-target",
        "gard-readiness-blocked",
        "gard-ready-for-uplift",
    }
)


def test_manifest_schema_valid(project_root: Path) -> None:
    manifest = load_writeback_manifest(repo_root=project_root)
    assert manifest.schema_version == "1"
    assert manifest.object_type == "dcim.device"
    assert manifest.unknown_sentinel == "unknown"
    assert len(manifest.custom_fields) >= 6
    assert len(manifest.tags) >= 4


def test_unique_slugs_and_fields(project_root: Path) -> None:
    manifest = load_writeback_manifest(repo_root=project_root)
    field_names = [f.netbox_field for f in manifest.custom_fields]
    assert len(field_names) == len(set(field_names))
    slugs = [t.slug for t in manifest.tags]
    assert len(slugs) == len(set(slugs))


def test_required_gard_sources_present(project_root: Path) -> None:
    manifest = load_writeback_manifest(repo_root=project_root)
    sources = {f.gard_source for f in manifest.custom_fields}
    assert sources >= REQUIRED_GARD_SOURCES


def test_required_tag_slugs_present(project_root: Path) -> None:
    manifest = load_writeback_manifest(repo_root=project_root)
    slugs = {t.slug for t in manifest.tags}
    assert slugs >= REQUIRED_TAG_SLUGS


def test_broken_manifest_fails(project_root: Path, tmp_path: Path) -> None:
    manifest_path = project_root / "gard-catalog/netbox/write-back-manifest.yaml"
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    raw["custom_fields"][0]["gard_source"] = "not_allowed"
    broken = tmp_path / "broken-writeback-manifest.yaml"
    broken.write_text(yaml.dump(raw), encoding="utf-8")
    with pytest.raises(WritebackManifestError, match="schema validation failed"):
        load_writeback_manifest(manifest_path=broken, repo_root=project_root)
