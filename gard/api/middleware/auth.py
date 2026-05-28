"""FastAPI auth dependency (OIDC bearer or GARD-issued JWT)."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from gard.core.logging import get_logger
from gard.core.rbac import Principal
from gard.core.settings import Settings, get_settings
from gard.core.tokens import InvalidTokenError, verify_token
from gard.db.session import get_session

_log = get_logger(__name__)


def _strip_bearer(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing Authorization header",
        )
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="malformed Authorization header",
        )
    return parts[1].strip()


def get_principal(
    authorization: str | None = Header(default=None, alias="Authorization"),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Principal:
    """Resolve the calling :class:`Principal`.

    v1 supports two token sources:

    1. **GARD-issued service tokens** — verified locally against
       ``GARD_JWT_SECRET`` and revocation-checked via the
       :class:`ApiToken` table.
    2. **OIDC ID tokens (placeholder)** — when ``GARD_OIDC_ISSUER`` is
       configured the framework will (in F1) accept these tokens by
       falling through; full JWKS verification is wired up by the next
       feature. F1 ships service-token verification as the production
       path; OIDC remains stubbed so endpoint contracts can be exercised.
    """
    raw = _strip_bearer(authorization)

    try:
        return verify_token(session=session, token=raw, settings=settings)
    except InvalidTokenError as exc:
        _log.info("auth.denied", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid token: {exc}",
        ) from exc
