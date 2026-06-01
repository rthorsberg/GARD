"""Contract test: F8 merged MCP registry manifest."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import yaml

from gard.core.rbac import Permission, all_permissions
from gard.mcp.registry import TOOL_REGISTRY

CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "008-mcp-transport"
    / "contracts"
    / "mcp-tools.yaml"
)

# Manifest uses shorthand auth labels; map to Permission string values.
_AUTH_ALIASES: dict[str, set[str]] = {
    "read_device_lifecycle": {Permission.LIST_DEVICES, Permission.READ_DEVICE},
    "read_firmware_catalog": {Permission.READ_FIRMWARE_CATALOG},
    "read_compliance": {Permission.READ_COMPLIANCE},
    "read_readiness": {Permission.READ_READINESS},
    "read_uplift": {Permission.READ_UPLIFT},
    "read_netbox_integration": {Permission.READ_NETBOX},
}


def _load_manifest() -> dict:
    with CONTRACT.open() as fp:
        return yaml.safe_load(fp)


def test_manifest_lists_22_tools_and_6_disallowed() -> None:
    doc = _load_manifest()
    assert len(doc["tools"]) == 22
    assert len(doc["disallowed"]) == 6


@pytest.mark.parametrize("tool", _load_manifest()["tools"], ids=lambda t: t["name"])
def test_registry_entry_matches_manifest(tool: dict) -> None:
    entry = TOOL_REGISTRY.get(tool["name"])
    assert entry is not None, f"missing registry entry for {tool['name']!r}"
    assert entry.name == tool["name"]
    allowed = _AUTH_ALIASES.get(tool["auth"], {getattr(Permission, tool["auth"], tool["auth"])})
    assert entry.required_permission in allowed, (
        f"{tool['name']}: {entry.required_permission!r} not in {allowed}"
    )
    assert entry.required_permission in all_permissions()


@pytest.mark.parametrize("tool", _load_manifest()["tools"], ids=lambda t: t["name"])
def test_delegate_module_metadata(tool: dict) -> None:
    mod = importlib.import_module(f"gard.mcp.tools.{tool['name']}")
    assert tool["name"] == mod.TOOL_NAME
    assert mod.REQUIRED_PERMISSION in _AUTH_ALIASES.get(tool["auth"], {mod.REQUIRED_PERMISSION})
    assert callable(mod.invoke)


def test_registry_count_is_22() -> None:
    assert len(TOOL_REGISTRY) == 22
