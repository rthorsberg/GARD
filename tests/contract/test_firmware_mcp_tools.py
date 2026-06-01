"""Contract tests for F2 MCP firmware tool delegates."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import yaml

from gard.core.rbac import Permission, all_permissions

CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "002-firmware-catalog"
    / "contracts"
    / "mcp-tools.yaml"
)


def _f2_tools() -> list[dict]:
    with CONTRACT.open() as fp:
        doc = yaml.safe_load(fp)
    return doc["tools"]


@pytest.mark.parametrize("tool", _f2_tools(), ids=lambda t: t["name"])
def test_f2_tool_metadata(tool: dict) -> None:
    mod = importlib.import_module(f"gard.mcp.tools.{tool['name']}")
    assert tool["name"] == mod.TOOL_NAME
    assert mod.REQUIRED_PERMISSION == Permission.READ_FIRMWARE_CATALOG
    assert mod.REQUIRED_PERMISSION in all_permissions()
    assert hasattr(mod, "invoke")
