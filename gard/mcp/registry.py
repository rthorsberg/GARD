"""Central MCP tool registry (F8).

Explicit imports for all 22 published tools from F1-F7 contracts.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from gard.mcp.tools import (
    count_devices_outside_target,
    create_exception_review_draft,
    create_uplift_wave_draft,
    explain_blockers,
    explain_wave,
    get_compliance_summary,
    get_device_lifecycle_status,
    get_netbox_sync_summary,
    get_readiness_summary,
    get_ready_for_uplift_devices,
    get_target_firmware,
    get_unknown_lifecycle_items,
    get_upgrade_path,
    get_uplift_plan_summary,
    list_active_exceptions,
    list_blocked_devices,
    list_devices,
    list_devices_outside_target,
    list_firmware_packages,
    list_firmware_targets,
    list_open_waves,
    list_upgrade_paths,
)


@dataclass(frozen=True)
class ToolEntry:
    name: str
    input_model: type[BaseModel]
    required_permission: str
    invoke: Callable[..., BaseModel]


def _input_model_for(mod: Any) -> type[BaseModel]:
    for attr in dir(mod):
        if attr.endswith("Input") and attr[0].isupper():
            cls = getattr(mod, attr)
            if isinstance(cls, type) and issubclass(cls, BaseModel):
                return cls
    raise AttributeError(f"no Input model on {mod.TOOL_NAME}")


TOOL_REGISTRY: dict[str, ToolEntry] = {
    mod.TOOL_NAME: ToolEntry(
        name=mod.TOOL_NAME,
        input_model=_input_model_for(mod),
        required_permission=mod.REQUIRED_PERMISSION,
        invoke=mod.invoke,
    )
    for mod in (
        list_devices,
        get_device_lifecycle_status,
        get_target_firmware,
        get_upgrade_path,
        list_firmware_targets,
        list_firmware_packages,
        list_upgrade_paths,
        count_devices_outside_target,
        list_devices_outside_target,
        get_compliance_summary,
        get_unknown_lifecycle_items,
        get_readiness_summary,
        list_blocked_devices,
        explain_blockers,
        get_ready_for_uplift_devices,
        create_uplift_wave_draft,
        create_exception_review_draft,
        get_uplift_plan_summary,
        list_open_waves,
        list_active_exceptions,
        explain_wave,
        get_netbox_sync_summary,
    )
}
