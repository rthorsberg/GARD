"""Contract test for F5 MCP tool definitions."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import yaml

from gard.core.rbac import Permission, all_permissions

CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "005-uplift-planning-waves"
    / "contracts"
    / "mcp-tools.yaml"
)


def _load_tools() -> list[dict]:
    with CONTRACT.open() as fp:
        doc = yaml.safe_load(fp)
    return doc["mcp_tools"]


def test_contract_yaml_exists_and_parses() -> None:
    assert CONTRACT.exists(), f"missing F5 MCP contract: {CONTRACT}"
    tools = _load_tools()
    assert tools, "contract declares zero tools"
    assert len(tools) == 6, f"F5 declares 6 MCP tools, got {len(tools)}"


@pytest.mark.parametrize("tool", _load_tools(), ids=lambda t: t["name"])
def test_tool_has_required_metadata(tool: dict) -> None:
    for key in ("name", "description", "auth", "input_schema", "output_schema"):
        assert tool.get(key), f"tool {tool.get('name')!r} missing key {key!r}"


@pytest.mark.parametrize("tool", _load_tools(), ids=lambda t: t["name"])
def test_auth_is_a_known_permission_attribute(tool: dict) -> None:
    name = tool["auth"]
    assert hasattr(Permission, name), f"Permission has no attribute {name!r}"
    value = getattr(Permission, name)
    assert value in all_permissions(), (
        f"Permission.{name} value {value!r} not registered with any role"
    )


@pytest.mark.parametrize("tool", _load_tools(), ids=lambda t: t["name"])
def test_delegate_module_exists(tool: dict) -> None:
    mod = importlib.import_module(f"gard.mcp.tools.{tool['name']}")
    assert getattr(mod, "TOOL_NAME", None) == tool["name"], (
        f"{tool['name']} delegate has wrong TOOL_NAME"
    )
    assert hasattr(mod, "REQUIRED_PERMISSION"), (
        f"{tool['name']} delegate must declare REQUIRED_PERMISSION"
    )
    assert callable(getattr(mod, "invoke", None)), f"{tool['name']} delegate must expose invoke()"
