"""NetBox REST API token header helpers (v1 Token / v2 Bearer)."""

from __future__ import annotations


def netbox_authorization_header(token: str) -> str:
    """Return Authorization header value for NetBox v1 or v2 API tokens."""
    value = token.strip()
    if value.lower().startswith("bearer "):
        return value
    if value.startswith("nbt_") and "." in value:
        return f"Bearer {value}"
    return f"Token {value}"
