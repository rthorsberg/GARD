"""Role → permission catalogue.

Single source of truth for RBAC checks. Every REST route and every MCP
tool calls :func:`require` (via :class:`gard.api.middleware.rbac.RBAC`)
to gate access; this module defines what each role is allowed to do.

Roles are defined in :class:`gard.models._enums.Role`. Permissions are
plain strings — they are *not* a closed enum because future features
add new ones (we can't churn the enum every PR).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from gard.models._enums import Role


# Permissions used in F1; later features extend the catalogue.
class Permission:
    READ_DEVICE = "device.read"
    LIST_DEVICES = "device.list"
    READ_OBSERVATION = "observation.read"
    READ_AUDIT = "audit.read"
    READ_EVIDENCE = "evidence.read"
    READ_RULE = "rule.read"

    IMPORT_DEVICES = "device.import"
    REEVALUATE_OBSERVATION = "observation.reevaluate"
    MANAGE_RULES = "rule.manage"
    CREATE_MANUAL_MAPPING = "observation.manual_map"

    INVOKE_MCP_TOOL = "mcp.tool.invoke"

    MANAGE_TOKENS = "token.manage"
    MANAGE_MCP_TOOLS = "mcp.tool.manage"


# fmt: off
_ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.viewer: frozenset({
        Permission.READ_DEVICE,
        Permission.LIST_DEVICES,
        Permission.READ_OBSERVATION,
        Permission.READ_AUDIT,
        Permission.READ_EVIDENCE,
        Permission.READ_RULE,
    }),
    Role.lifecycle_manager: frozenset({
        Permission.READ_DEVICE,
        Permission.LIST_DEVICES,
        Permission.READ_OBSERVATION,
        Permission.READ_AUDIT,
        Permission.READ_EVIDENCE,
        Permission.READ_RULE,
        Permission.IMPORT_DEVICES,
        Permission.REEVALUATE_OBSERVATION,
        Permission.MANAGE_RULES,
        Permission.CREATE_MANUAL_MAPPING,
    }),
    Role.mcp_client: frozenset({
        Permission.READ_DEVICE,
        Permission.LIST_DEVICES,
        Permission.READ_OBSERVATION,
        Permission.READ_RULE,
        Permission.INVOKE_MCP_TOOL,
    }),
    Role.system_admin: frozenset({
        Permission.READ_DEVICE,
        Permission.LIST_DEVICES,
        Permission.READ_OBSERVATION,
        Permission.READ_AUDIT,
        Permission.READ_EVIDENCE,
        Permission.READ_RULE,
        Permission.IMPORT_DEVICES,
        Permission.REEVALUATE_OBSERVATION,
        Permission.MANAGE_RULES,
        Permission.CREATE_MANUAL_MAPPING,
        Permission.INVOKE_MCP_TOOL,
        Permission.MANAGE_TOKENS,
        Permission.MANAGE_MCP_TOOLS,
    }),
}
# fmt: on


@dataclass(frozen=True)
class Principal:
    """Authenticated caller, populated by :mod:`gard.api.middleware.auth`."""

    subject: str
    actor_type: str  # gard.models._enums.ActorType value
    roles: tuple[Role, ...]

    @property
    def permissions(self) -> frozenset[str]:
        out: set[str] = set()
        for r in self.roles:
            out |= _ROLE_PERMISSIONS.get(r, frozenset())
        return frozenset(out)

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    def has_any(self, permissions: Iterable[str]) -> bool:
        ps = self.permissions
        return any(p in ps for p in permissions)


def role_permissions(role: Role) -> frozenset[str]:
    return _ROLE_PERMISSIONS.get(role, frozenset())


def all_permissions() -> frozenset[str]:
    """Every permission the catalogue knows about."""
    out: set[str] = set()
    for ps in _ROLE_PERMISSIONS.values():
        out |= ps
    return frozenset(out)
