"""Contract tests for F12 alignment policy manifest."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from gard.integrations.netbox.alignment_manifest import (
    AlignmentManifestError,
    load_alignment_manifest,
)


def test_manifest_schema_valid(project_root: Path) -> None:
    manifest = load_alignment_manifest(repo_root=project_root)
    assert manifest.schema_version == "1"
    assert len(manifest.interface_policies) >= 1
    assert "oslo" in manifest.sites


def test_unique_policy_ids(project_root: Path) -> None:
    manifest = load_alignment_manifest(repo_root=project_root)
    ids = [p.id for p in manifest.interface_policies]
    assert len(ids) == len(set(ids))


def test_broken_manifest_fails(project_root: Path, tmp_path: Path) -> None:
    manifest_path = project_root / "gard-catalog/netbox/alignment-policy-manifest.yaml"
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    raw["interface_policies"][0]["id"] = "INVALID ID"
    broken = tmp_path / "broken-alignment-manifest.yaml"
    broken.write_text(yaml.dump(raw), encoding="utf-8")
    with pytest.raises(AlignmentManifestError, match="schema validation failed"):
        load_alignment_manifest(manifest_path=broken, repo_root=project_root)


def test_catalogue_site_role_references(project_root: Path) -> None:
    manifest = load_alignment_manifest(repo_root=project_root)
    for policy in manifest.interface_policies:
        if policy.site != "*":
            assert policy.site in manifest.sites
        if policy.role != "*":
            assert policy.role in manifest.roles
