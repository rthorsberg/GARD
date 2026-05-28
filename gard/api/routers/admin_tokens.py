"""Admin endpoints for service / MCP-client API tokens (T045)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from gard.api.middleware.rbac import require
from gard.api.schemas.tokens import IssueTokenRequest, IssueTokenResponse, TokenSummary
from gard.core.audit import emit as emit_audit
from gard.core.rbac import Permission, Principal
from gard.core.tokens import issue_token, revoke_token
from gard.db.session import get_append_only_session, get_session
from gard.models._enums import ActorType

router = APIRouter(prefix="/api/v1/admin/tokens", tags=["admin"])


@router.post(
    "",
    response_model=IssueTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue an API token",
)
def issue(
    body: IssueTokenRequest,
    principal: Principal = Depends(require(Permission.MANAGE_TOKENS)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> IssueTokenResponse:
    issued = issue_token(
        session=session,
        name=body.name,
        subject=body.subject,
        roles=body.roles,
        created_by=principal.subject,
        ttl_seconds=body.ttl_seconds,
    )
    emit_audit(
        session=audit_session,
        action="auth.token.issued",
        object_type="ApiToken",
        object_id=str(issued.token_id),
        principal=principal,
        actor_type=ActorType.user,
        after={"subject": body.subject, "roles": [r.value for r in body.roles]},
    )
    audit_session.commit()
    return IssueTokenResponse(
        token_id=issued.token_id,
        jwt=issued.jwt,
        expires_at=issued.expires_at,
        name=body.name,
        subject=body.subject,
        roles=body.roles,
    )


@router.post(
    "/{token_id}/revoke",
    response_model=TokenSummary,
    summary="Revoke an API token",
)
def revoke(
    token_id: uuid.UUID,
    principal: Principal = Depends(require(Permission.MANAGE_TOKENS)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> TokenSummary:
    row = revoke_token(session=session, token_id=token_id)
    if row is None:
        raise HTTPException(status_code=404, detail="token not found")
    emit_audit(
        session=audit_session,
        action="auth.token.revoked",
        object_type="ApiToken",
        object_id=str(token_id),
        principal=principal,
        actor_type=ActorType.user,
        after={"revoked_at": row.revoked_at.isoformat() if row.revoked_at else None},
    )
    audit_session.commit()
    return TokenSummary(
        id=row.id,
        name=row.name,
        subject=row.subject,
        roles=list(row.roles),
        issued_at=row.issued_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
    )
