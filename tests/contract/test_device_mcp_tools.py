"""Contract tests for F1 MCP tool delegates."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import yaml

from gard.core.rbac import Permission, all_permissions

CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "001-device-import-normalize"
    / "contracts"
    / "mcp-tools.yaml"
)


def _f1_tools() -> list[dict]:
    with CONTRACT.open() as fp:
        doc = yaml.safe_load(fp)
    return doc["tools"]


@pytest.mark.parametrize("tool", _f1_tools(), ids=lambda t: t["name"])
def test_f1_tool_metadata(tool: dict) -> None:
    mod = importlib.import_module(f"gard.mcp.tools.{tool['name']}")
    assert tool["name"] == mod.TOOL_NAME
    assert mod.REQUIRED_PERMISSION in (
        Permission.LIST_DEVICES,
        Permission.READ_DEVICE,
    )
    assert mod.REQUIRED_PERMISSION in all_permissions()
    assert hasattr(mod, "invoke")
