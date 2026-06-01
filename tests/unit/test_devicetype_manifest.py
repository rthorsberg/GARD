"""Unit tests for device type manifest loader."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from gard.integrations.netbox.devicetype_manifest import DeviceTypeManifestError, load_manifest


def test_empty_aliases_rejected_by_schema(project_root: Path, tmp_path: Path) -> None:
    manifest_path = project_root / "gard-catalog/netbox/device-types-manifest.yaml"
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    raw["entries"][0]["model_raw_aliases"] = []
    broken = tmp_path / "empty-aliases.yaml"
    broken.write_text(yaml.dump(raw), encoding="utf-8")
    with pytest.raises(DeviceTypeManifestError, match="schema validation failed"):
        load_manifest(manifest_path=broken, repo_root=project_root)


def test_conflicting_slug_detection(project_root: Path, tmp_path: Path) -> None:
    manifest_path = project_root / "gard-catalog/netbox/device-types-manifest.yaml"
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    raw["entries"][1]["expected_slug"] = raw["entries"][0]["expected_slug"]
    broken = tmp_path / "dup-slug.yaml"
    broken.write_text(yaml.dump(raw), encoding="utf-8")
    with pytest.raises(DeviceTypeManifestError, match="duplicate expected_slug"):
        load_manifest(manifest_path=broken, repo_root=project_root)


def test_conflicting_alias_detection(project_root: Path, tmp_path: Path) -> None:
    manifest_path = project_root / "gard-catalog/netbox/device-types-manifest.yaml"
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    raw["entries"][1]["model_raw_aliases"] = list(raw["entries"][0]["model_raw_aliases"])
    broken = tmp_path / "dup-alias.yaml"
    broken.write_text(yaml.dump(raw), encoding="utf-8")
    with pytest.raises(DeviceTypeManifestError, match="alias"):
        load_manifest(manifest_path=broken, repo_root=project_root)
