"""MCP tool invocation: auth, RBAC, validation, audit, delegate dispatch."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from gard.core.audit import emit as audit_emit
from gard.core.logging import get_correlation_id
from gard.core.rbac import Permission, Principal
from gard.db.session import append_only_scope, session_scope
from gard.mcp.context import get_mcp_principal
from gard.mcp.registry import TOOL_REGISTRY, ToolEntry
from gard.models._enums import AuditResult

_MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "008-mcp-transport"
    / "contracts"
    / "mcp-tools.yaml"
)


class McpHandlerError(Exception):
    """Base MCP handler error surfaced to the transport layer."""

    def __init__(self, message: str, *, code: str = "handler_error") -> None:
        super().__init__(message)
        self.code = code


class McpAuthRequired(McpHandlerError):
    def __init__(self, message: str = "authentication required") -> None:
        super().__init__(message, code="unauthorized")


class McpPermissionDenied(McpHandlerError):
    def __init__(self, message: str = "permission denied") -> None:
        super().__init__(message, code="forbidden")


class McpValidationFailed(McpHandlerError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="invalid_params")


class McpToolNotFound(McpHandlerError):
    def __init__(self, tool_name: str) -> None:
        super().__init__(f"tool not found: {tool_name}", code="tool_not_found")
        self.tool_name = tool_name


def _load_disallowed() -> frozenset[str]:
    with _MANIFEST.open() as fp:
        doc = yaml.safe_load(fp)
    return frozenset(doc.get("disallowed") or [])


DISALLOWED_TOOLS: frozenset[str] = _load_disallowed()


def _records_returned(output: BaseModel) -> int:
    data = output.model_dump()
    if isinstance(data.get("items"), list):
        return len(data["items"])
    if "count" in data and isinstance(data["count"], int):
        return data["count"]
    if "total_returned" in data and isinstance(data["total_returned"], int):
        return data["total_returned"]
    return 1


def _audit_tool(
    *,
    audit_session: Any,
    principal: Principal,
    tool_name: str,
    result: AuditResult,
    records_returned: int = 0,
    extra: dict[str, Any] | None = None,
) -> None:
    after: dict[str, Any] = {
        "tool": tool_name,
        "records_returned": records_returned,
    }
    if extra:
        after.update(extra)
    audit_emit(
        session=audit_session,
        action="mcp.tool.invoked",
        object_type="McpTool",
        object_id=tool_name,
        result=result,
        principal=principal,
        after=after,
        correlation_id=get_correlation_id(),
    )


def _audit_disallowed(*, audit_session: Any, principal: Principal, tool_name: str) -> None:
    audit_emit(
        session=audit_session,
        action="mcp.disallowed_tool_attempt",
        object_type="McpTool",
        object_id=tool_name,
        result=AuditResult.denied,
        principal=principal,
        after={"tool_name": tool_name, "client_identity": principal.subject},
        correlation_id=get_correlation_id(),
    )


def _require_principal() -> Principal:
    principal = get_mcp_principal()
    if principal is None:
        raise McpAuthRequired()
    return principal


def _check_permissions(principal: Principal, entry: ToolEntry) -> None:
    if not principal.has(Permission.INVOKE_MCP_TOOL):
        raise McpPermissionDenied("missing permission: mcp.tool.invoke")
    if not principal.has(entry.required_permission):
        raise McpPermissionDenied(f"missing permission: {entry.required_permission}")


def invoke_tool(name: str, raw_arguments: dict[str, Any] | BaseModel) -> dict[str, Any]:
    """Synchronous tool dispatch used by the MCP transport layer."""
    principal = _require_principal()

    if name in DISALLOWED_TOOLS:
        with append_only_scope() as audit_session:
            _audit_disallowed(audit_session=audit_session, principal=principal, tool_name=name)
            audit_session.commit()
        raise McpToolNotFound(name)

    entry = TOOL_REGISTRY.get(name)
    if entry is None:
        with append_only_scope() as audit_session:
            _audit_disallowed(audit_session=audit_session, principal=principal, tool_name=name)
            audit_session.commit()
        raise McpToolNotFound(name)

    try:
        body = (
            raw_arguments
            if isinstance(raw_arguments, entry.input_model)
            else entry.input_model.model_validate(raw_arguments)
        )
    except ValidationError as exc:
        raise McpValidationFailed(json.dumps(exc.errors())) from exc

    try:
        _check_permissions(principal, entry)
    except McpPermissionDenied:
        with append_only_scope() as audit_session:
            _audit_tool(
                audit_session=audit_session,
                principal=principal,
                tool_name=name,
                result=AuditResult.denied,
                extra={"permission": entry.required_permission},
            )
            audit_session.commit()
        raise

    with session_scope() as session, append_only_scope() as audit_session:
        output = entry.invoke(session=session, body=body)
        n = _records_returned(output)
        _audit_tool(
            audit_session=audit_session,
            principal=principal,
            tool_name=name,
            result=AuditResult.success,
            records_returned=n,
        )
        audit_session.commit()
        return output.model_dump(mode="json")


def invoke_disallowed_stub(name: str) -> dict[str, Any]:
    """Entry point for deny-list tools registered on the MCP server."""
    invoke_tool(name, {})
    return {}  # pragma: no cover
