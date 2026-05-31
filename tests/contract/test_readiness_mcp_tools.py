"""Contract test for F4 MCP tool definitions.

Parses ``specs/004-readiness-prerequisites/contracts/mcp-tools.yaml``
and asserts:

- Every tool declares ``name``, ``description``, ``auth``,
  ``input_schema``, ``output_schema``.
- ``auth`` resolves to a Permission attribute that is bound to at
  least one role.
- A delegate module exists under ``gard/mcp/tools/<name>.py`` with the
  expected ``TOOL_NAME`` + ``REQUIRED_PERMISSION`` + ``invoke`` surface.

Per ADR-0013 the MCP server itself ships with F008; this test ensures
that when F008 lands every contracted F4 tool already has a working
delegate.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import yaml

from gard.core.rbac import Permission, all_permissions

CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "004-readiness-prerequisites"
    / "contracts"
    / "mcp-tools.yaml"
)


def _load_tools() -> list[dict]:
    with CONTRACT.open() as fp:
        doc = yaml.safe_load(fp)
    return doc["mcp_tools"]


def test_contract_yaml_exists_and_parses() -> None:
    assert CONTRACT.exists(), f"missing F4 MCP contract: {CONTRACT}"
    tools = _load_tools()
    assert tools, "contract declares zero tools"
    assert len(tools) == 4, f"F4 declares 4 MCP tools, got {len(tools)}"


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
