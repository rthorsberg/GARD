"""Contract tests for F13 platform lab stack manifest."""

from __future__ import annotations

from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_lab_stack_manifest_validates(project_root: Path) -> None:
    schema_path = (
        project_root / "specs/013-netbox-platform-lab/contracts/lab-stack-manifest.schema.yaml"
    )
    manifest_path = project_root / "specs/013-netbox-platform-lab/contracts/lab-stack-manifest.yaml"
    schema = _load_yaml(schema_path)
    manifest = _load_yaml(manifest_path)
    Draft202012Validator(schema).validate(manifest)
    assert manifest["project_name"] == "gard-f7-netbox"


def test_lab_stack_manifest_minimum_services(project_root: Path) -> None:
    manifest_path = project_root / "specs/013-netbox-platform-lab/contracts/lab-stack-manifest.yaml"
    manifest = _load_yaml(manifest_path)
    names = {svc["name"] for svc in manifest["services"]}
    required = {"netbox", "diode-nginx", "orb-agent", "lab-sim-1", "lab-sim-2", "lab-sim-3"}
    assert required.issubset(names)


def test_lab_stack_netbox_port_default(project_root: Path) -> None:
    manifest_path = project_root / "specs/013-netbox-platform-lab/contracts/lab-stack-manifest.yaml"
    manifest = _load_yaml(manifest_path)
    netbox_ui = next(p for p in manifest["ports"] if p["name"] == "netbox_ui")
    assert netbox_ui["host_port"] == 18888
