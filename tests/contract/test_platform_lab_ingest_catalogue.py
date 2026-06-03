"""Contract tests for F13 platform lab ingest fixture catalogue."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator


def _catalogue_path(project_root: Path) -> Path:
    return project_root / "deploy/scripts/fixtures/platform-lab/ingest-catalogue.yaml"


def test_ingest_catalogue_validates(project_root: Path) -> None:
    catalogue_path = _catalogue_path(project_root)
    if not catalogue_path.exists():
        pytest.skip("ingest catalogue not yet created (deploy phase)")

    schema_path = (
        project_root
        / "specs/013-netbox-platform-lab/contracts/ingest-fixture-catalogue.schema.yaml"
    )
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    catalogue = yaml.safe_load(catalogue_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(catalogue)
    assert catalogue["minimum_device_count"] >= 3
    assert len(catalogue["devices"]) >= catalogue["minimum_device_count"]


def test_ingest_catalogue_unique_device_names(project_root: Path) -> None:
    catalogue_path = _catalogue_path(project_root)
    if not catalogue_path.exists():
        pytest.skip("ingest catalogue not yet created (deploy phase)")

    catalogue = yaml.safe_load(catalogue_path.read_text(encoding="utf-8"))
    names = [d["name"] for d in catalogue["devices"]]
    assert len(names) == len(set(names))
