"""Contract tests for F9 device type manifest."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
import yaml

from gard.integrations.netbox.devicetype_manifest import (
    DeviceTypeManifestError,
    load_manifest,
)


def test_manifest_schema_and_library_paths_exist(project_root: Path) -> None:
    manifest = load_manifest(repo_root=project_root)
    assert manifest.schema_version == "1"
    assert manifest.upstream_pin == "3e34a981c5e0e5805e21fccf534e316177f4f182"
    assert len(manifest.entries) == 6
    slugs = {e.expected_slug for e in manifest.entries}
    assert len(slugs) == 6
    for entry in manifest.entries:
        path = manifest.library_file(entry)
        assert path.is_file(), f"missing library file for {entry.id}: {path}"


def test_no_duplicate_aliases(project_root: Path) -> None:
    manifest = load_manifest(repo_root=project_root)
    seen: set[str] = set()
    for entry in manifest.entries:
        for alias in entry.model_raw_aliases:
            assert alias not in seen, f"duplicate alias {alias!r}"
            seen.add(alias)


def test_broken_library_path_fails_before_import(project_root: Path, tmp_path: Path) -> None:
    manifest_path = project_root / "gard-catalog/netbox/device-types-manifest.yaml"
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    raw["entries"][0]["library_path"] = "device-types/Cisco/DOES-NOT-EXIST.yaml"
    broken = tmp_path / "broken-manifest.yaml"
    broken.write_text(yaml.dump(raw), encoding="utf-8")
    with pytest.raises(DeviceTypeManifestError, match="library_path not found"):
        load_manifest(manifest_path=broken, repo_root=project_root)


def _csv_supported_model_raw_values(path: Path) -> set[str]:
    supported_vendors = ("cisco", "juniper", "nokia")
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        models: set[str] = set()
        for row in reader:
            model = (row.get("model_raw") or "").strip()
            vendor = (row.get("vendor_raw") or "").strip().lower()
            if not model:
                continue
            if any(v in vendor for v in supported_vendors):
                models.add(model)
        return models


def test_manifest_covers_seed_fixture_models(project_root: Path) -> None:
    manifest = load_manifest(repo_root=project_root)
    alias_map: dict[str, str] = {}
    for entry in manifest.entries:
        for alias in entry.model_raw_aliases:
            alias_map[alias] = entry.id

    for fixture in (
        project_root / "deploy/scripts/fixtures/isr1121-devices.csv",
        project_root / "deploy/scripts/fixtures/devices.csv",
    ):
        models = _csv_supported_model_raw_values(fixture)
        missing = [m for m in models if m not in alias_map]
        assert not missing, f"{fixture.name} models not in manifest aliases: {missing}"
