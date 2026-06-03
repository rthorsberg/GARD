"""Contract tests for F13 platform lab health-check JSON schema."""

from __future__ import annotations

from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


def _validator(project_root: Path) -> Draft202012Validator:
    schema_path = (
        project_root / "specs/013-netbox-platform-lab/contracts/health-check.schema.yaml"
    )
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def test_health_report_healthy(project_root: Path) -> None:
    sample = {
        "status": "healthy",
        "branching_enabled": True,
        "checks": [
            {"name": "netbox_ui", "ok": True, "detail": "HTTP 200"},
            {"name": "diode_grpc", "ok": True},
            {"name": "orb_agent", "ok": True},
            {"name": "netbox_diode_plugin", "ok": True},
            {"name": "branching_plugin", "ok": True},
        ],
    }
    _validator(project_root).validate(sample)


def test_health_report_degraded(project_root: Path) -> None:
    sample = {
        "status": "degraded",
        "branching_enabled": False,
        "checks": [
            {"name": "netbox_ui", "ok": True},
            {"name": "diode_grpc", "ok": True},
            {"name": "orb_agent", "ok": True},
            {"name": "netbox_diode_plugin", "ok": True},
            {"name": "branching_plugin", "ok": False, "detail": "skipped"},
        ],
    }
    _validator(project_root).validate(sample)


def test_health_report_unhealthy(project_root: Path) -> None:
    sample = {
        "status": "unhealthy",
        "branching_enabled": False,
        "checks": [
            {"name": "netbox_ui", "ok": False, "detail": "connection refused"},
            {"name": "diode_grpc", "ok": False},
            {"name": "orb_agent", "ok": False},
            {"name": "netbox_diode_plugin", "ok": False},
        ],
    }
    _validator(project_root).validate(sample)
