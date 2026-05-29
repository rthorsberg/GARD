"""Service / MCP-client API token issuance, verification, and CLI.

Tokens are signed JWTs. The DB row in :class:`gard.models.ApiToken` is
the revocation record — we look up the ``jti`` claim on every
verification to refuse revoked tokens.
"""

from __future__ import annotations

import datetime as dt
import sys
import uuid
from dataclasses import dataclass
from typing import Any

from jose import jwt
from jose.exceptions import JWTError
from sqlalchemy.orm import Session

from gard.core.logging import get_logger
from gard.core.rbac import Principal
from gard.core.settings import Settings, get_settings
from gard.models import ApiToken, utcnow
from gard.models._enums import ActorType, Role

_log = get_logger(__name__)


class InvalidTokenError(Exception):
    """Raised by :func:`verify_token` when the token cannot be trusted."""


@dataclass(frozen=True)
class IssuedToken:
    token_id: uuid.UUID
    jwt: str
    expires_at: dt.datetime


def issue_token(
    *,
    session: Session,
    name: str,
    subject: str,
    roles: list[Role],
    created_by: str,
    ttl_seconds: int | None = None,
    settings: Settings | None = None,
) -> IssuedToken:
    """Mint a new API token, persist its DB record, return JWT + metadata.

    The DB row's ``expires_at`` is never null (FR-025). When
    ``ttl_seconds`` is omitted we apply :attr:`Settings.api_token_ttl_seconds`.
    """
    s = settings or get_settings()
    ttl = ttl_seconds if ttl_seconds is not None else s.api_token_ttl_seconds
    if ttl < 60:
        raise ValueError("token TTL must be >= 60 seconds")

    issued_at = utcnow()
    expires_at = issued_at + dt.timedelta(seconds=ttl)
    token_id = uuid.UUID(str(uuid.uuid4()))  # jti is independent of UUID7 ordering

    db_row = ApiToken(
        id=token_id,
        name=name,
        subject=subject,
        roles=[r.value for r in roles],
        issued_at=issued_at,
        expires_at=expires_at,
        revoked_at=None,
        created_by=created_by,
    )
    session.add(db_row)
    session.flush()

    claims: dict[str, Any] = {
        "iss": "gard",
        "aud": "gard",
        "sub": subject,
        "jti": str(token_id),
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "roles": [r.value for r in roles],
        "actor_type": ActorType.mcp_client.value,
    }
    encoded = jwt.encode(claims, s.jwt_secret, algorithm=s.jwt_algorithm)
    return IssuedToken(token_id=token_id, jwt=encoded, expires_at=expires_at)


def revoke_token(*, session: Session, token_id: uuid.UUID) -> ApiToken | None:
    row = session.get(ApiToken, token_id)
    if row is None:
        return None
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        session.flush()
    return row


def verify_token(
    *,
    session: Session,
    token: str,
    settings: Settings | None = None,
) -> Principal:
    """Decode + validate + revocation-check.

    Raises :class:`InvalidTokenError` for any failure. The caller
    converts to an HTTP 401 / MCP error.
    """
    s = settings or get_settings()
    try:
        claims = jwt.decode(
            token,
            s.jwt_secret,
            algorithms=[s.jwt_algorithm],
            audience="gard",
            issuer="gard",
        )
    except JWTError as exc:
        raise InvalidTokenError(f"invalid jwt: {exc}") from exc

    jti_str = claims.get("jti")
    if not jti_str:
        raise InvalidTokenError("missing jti")
    try:
        jti = uuid.UUID(jti_str)
    except ValueError as exc:
        raise InvalidTokenError("malformed jti") from exc

    row = session.get(ApiToken, jti)
    if row is None:
        raise InvalidTokenError("unknown token")
    if row.revoked_at is not None:
        raise InvalidTokenError("token revoked")
    if row.expires_at < utcnow():
        raise InvalidTokenError("token expired")

    role_values = claims.get("roles", [])
    roles: list[Role] = []
    for r in role_values:
        try:
            roles.append(Role(r))
        except ValueError:
            # Unknown role in claims — drop silently rather than reject;
            # the token is still tamper-proof.
            continue

    return Principal(
        subject=str(claims.get("sub", row.subject)),
        actor_type=str(claims.get("actor_type", ActorType.mcp_client.value)),
        roles=tuple(roles),
    )


# ---------- CLI entry point used by `gard issue-token` ----------------


def issue_token_cli(subject: str, role: str, ttl_seconds: int | None) -> int:  # pragma: no cover
    from gard.db.session import session_scope

    try:
        role_enum = Role(role)
    except ValueError:
        sys.stderr.write(f"Unknown role: {role}\n")
        return 2

    with session_scope() as session:
        issued = issue_token(
            session=session,
            name=f"cli:{subject}",
            subject=subject,
            roles=[role_enum],
            created_by="cli",
            ttl_seconds=ttl_seconds,
        )
        sys.stdout.write(issued.jwt + "\n")
        sys.stderr.write(f"jti={issued.token_id} expires_at={issued.expires_at.isoformat()}\n")
    return 0
