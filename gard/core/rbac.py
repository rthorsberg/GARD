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

    # ---- F2: firmware catalog --------------------------------------------
    # NB: MANAGE_FIRMWARE_CATALOG is lab-only — gated by catalog_editor_enabled
    # in the admin router. Production catalog changes remain git-native (ADR-0011).
    READ_FIRMWARE_CATALOG = "firmware_catalog.read"
    MANAGE_FIRMWARE_CATALOG = "firmware_catalog.manage"
    MANAGE_FIRMWARE_BLOB = "firmware_catalog.blob.manage"

    # ---- F3: compliance & drift evaluation -------------------------------
    # READ_COMPLIANCE gates the three GET endpoints under /api/v1/compliance
    # and /devices/{id}/compliance. RUN_COMPLIANCE_EVAL gates the bounded
    # POST /compliance/evaluate trigger — admin-grade because an unbounded
    # call could pin Postgres for the duration of the batch.
    READ_COMPLIANCE = "compliance.read"
    RUN_COMPLIANCE_EVAL = "compliance.evaluate"

    # ---- F4: readiness & prerequisites -----------------------------------
    # READ_READINESS gates the three GET endpoints under /api/v1/readiness
    # and /devices/{id}/readiness. RUN_READINESS_EVAL gates the bounded
    # POST /readiness/evaluate trigger. Same admin-grade reasoning as
    # F3's RUN_COMPLIANCE_EVAL — unbounded calls would pin Postgres.
    READ_READINESS = "readiness.read"
    RUN_READINESS_EVAL = "readiness.evaluate"

    # ---- F5: uplift planning & waves -------------------------------------
    # READ_UPLIFT gates every GET under /api/v1/uplift/. DRAFT_UPLIFT_WAVE
    # gates create/submit/cancel on waves + plans (lifecycle_manager
    # surface). APPROVE_UPLIFT_WAVE gates approve/reject; this is the
    # second-principal capability required by ADR-0016 §B SoD enforcement.
    # MANAGE_EXCEPTION + APPROVE_EXCEPTION mirror the wave pair for the
    # exception entity.
    READ_UPLIFT = "uplift.read"
    DRAFT_UPLIFT_WAVE = "uplift.wave.draft"
    APPROVE_UPLIFT_WAVE = "uplift.wave.approve"
    MANAGE_EXCEPTION = "uplift.exception.manage"
    APPROVE_EXCEPTION = "uplift.exception.approve"

    # ---- F7: NetBox integration (read-only) ----------------------------
    READ_NETBOX = "netbox.read"
    SYNC_NETBOX = "netbox.sync"


# fmt: off
_ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.viewer: frozenset({
        Permission.READ_DEVICE,
        Permission.LIST_DEVICES,
        Permission.READ_OBSERVATION,
        Permission.READ_AUDIT,
        Permission.READ_EVIDENCE,
        Permission.READ_RULE,
        Permission.READ_FIRMWARE_CATALOG,
        Permission.READ_COMPLIANCE,
        Permission.READ_READINESS,
        Permission.READ_UPLIFT,
        Permission.READ_NETBOX,
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
        Permission.READ_FIRMWARE_CATALOG,
        Permission.MANAGE_FIRMWARE_CATALOG,
        Permission.MANAGE_FIRMWARE_BLOB,
        Permission.READ_COMPLIANCE,
        Permission.RUN_COMPLIANCE_EVAL,
        Permission.READ_READINESS,
        Permission.RUN_READINESS_EVAL,
        Permission.READ_UPLIFT,
        Permission.DRAFT_UPLIFT_WAVE,
        Permission.MANAGE_EXCEPTION,
        Permission.READ_NETBOX,
        Permission.SYNC_NETBOX,
    }),
    Role.mcp_client: frozenset({
        Permission.READ_DEVICE,
        Permission.LIST_DEVICES,
        Permission.READ_OBSERVATION,
        Permission.READ_RULE,
        Permission.INVOKE_MCP_TOOL,
        Permission.READ_FIRMWARE_CATALOG,
        Permission.READ_COMPLIANCE,
        Permission.READ_READINESS,
        Permission.READ_UPLIFT,
        Permission.READ_NETBOX,
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
        Permission.READ_FIRMWARE_CATALOG,
        Permission.MANAGE_FIRMWARE_CATALOG,
        Permission.MANAGE_FIRMWARE_BLOB,
        Permission.READ_COMPLIANCE,
        Permission.RUN_COMPLIANCE_EVAL,
        Permission.READ_READINESS,
        Permission.RUN_READINESS_EVAL,
        Permission.READ_UPLIFT,
        Permission.DRAFT_UPLIFT_WAVE,
        Permission.APPROVE_UPLIFT_WAVE,
        Permission.MANAGE_EXCEPTION,
        Permission.APPROVE_EXCEPTION,
        Permission.READ_NETBOX,
        Permission.SYNC_NETBOX,
    }),
    # F5: pure-approval role (ADR-0016). No catalog mutation, no token
    # management — just the second-principal approval capability plus
    # broad read access for review work.
    Role.change_approver: frozenset({
        Permission.READ_DEVICE,
        Permission.LIST_DEVICES,
        Permission.READ_OBSERVATION,
        Permission.READ_AUDIT,
        Permission.READ_EVIDENCE,
        Permission.READ_RULE,
        Permission.READ_FIRMWARE_CATALOG,
        Permission.READ_COMPLIANCE,
        Permission.READ_READINESS,
        Permission.READ_UPLIFT,
        Permission.APPROVE_UPLIFT_WAVE,
        Permission.APPROVE_EXCEPTION,
        Permission.READ_NETBOX,
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
