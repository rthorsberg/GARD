"""`require(permission)` dependency factory."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from gard.api.middleware.auth import get_principal
from gard.core.audit import emit as emit_audit
from gard.core.rbac import Principal
from gard.db.session import get_append_only_session
from gard.models._enums import AuditResult


def require(permission: str) -> Callable[..., Principal]:
    """Return a FastAPI dependency that asserts ``permission`` on the caller.

    On denial, an ``auth.denied`` audit event is recorded and a 403 is
    raised. Audit emission uses a separate append-only session so the
    failure is recorded even if the request session is rolled back.
    """

    def _dep(
        principal: Principal = Depends(get_principal),
        audit_session: Session = Depends(get_append_only_session),
    ) -> Principal:
        if not principal.has(permission):
            emit_audit(
                session=audit_session,
                action="auth.denied",
                object_type="Permission",
                object_id=permission,
                result=AuditResult.denied,
                principal=principal,
                after={"permission": permission, "subject": principal.subject},
            )
            audit_session.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"missing permission: {permission}",
            )
        return principal

    return _dep
