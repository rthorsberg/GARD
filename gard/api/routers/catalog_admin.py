"""Lab catalog editor REST surface.

Write endpoints are available only when ``catalog_editor_enabled`` is true
or ``GARD_ENV`` is ``dev``/``test``. Production deployments should leave
the flag false and continue using git-native catalog changes (ADR-0011).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from gard.api.middleware.rbac import require
from gard.api.schemas.catalog_admin import (
    AddUpgradePathEdgeRequest,
    CatalogReloadResponse,
    CreateNormalizationRuleRequest,
    NormalizationRuleList,
    NormalizationRuleResponse,
    RenormalizeResponse,
    UpsertFirmwareTargetRequest,
)
from gard.core.catalog_editor import (
    CatalogEditorError,
    add_upgrade_path_edge,
    create_db_normalization_rule,
    list_db_normalization_rules,
    reload_catalogs,
    renormalize_estate,
    upsert_firmware_target,
)
from gard.core.rbac import Permission, Principal
from gard.core.settings import get_settings
from gard.db.session import get_append_only_session, get_session

router = APIRouter(prefix="/api/v1/admin/catalog", tags=["catalog-admin"])


def _editor_enabled() -> bool:
    s = get_settings()
    return s.catalog_editor_enabled or s.env in ("dev", "test")


def _require_editor() -> None:
    if not _editor_enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="catalog editor is disabled in this environment",
        )


@router.post(
    "/reload",
    response_model=CatalogReloadResponse,
    summary="Reload normalization + firmware catalogs from disk",
)
def reload_(
    principal: Principal = Depends(require(Permission.MANAGE_FIRMWARE_CATALOG)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> CatalogReloadResponse:
    _require_editor()
    try:
        summary = reload_catalogs(
            session=session,
            audit_session=audit_session,
            actor=principal.subject,
        )
    except CatalogEditorError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    audit_session.commit()
    return CatalogReloadResponse(
        normalization_loaded=summary.normalization_loaded,
        normalization_errors=summary.normalization_errors,
        firmware_loaded=summary.firmware_loaded,
        firmware_removed=summary.firmware_removed,
        devices_reevaluated=summary.devices_reevaluated,
    )


@router.put(
    "/firmware/targets",
    response_model=CatalogReloadResponse,
    summary="Create or update a firmware target YAML file",
)
def upsert_target(
    body: UpsertFirmwareTargetRequest,
    principal: Principal = Depends(require(Permission.MANAGE_FIRMWARE_CATALOG)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> CatalogReloadResponse:
    _require_editor()
    try:
        upsert_firmware_target(
            name=body.name,
            platform_family=body.platform_family,
            target_version=body.target_version,
            scope_selector=body.scope_selector,
            notes=body.notes,
        )
        if not body.reload:
            return CatalogReloadResponse(
                normalization_loaded=0,
                normalization_errors=[],
                firmware_loaded=0,
                firmware_removed=0,
                devices_reevaluated=0,
            )
        summary = reload_catalogs(
            session=session,
            audit_session=audit_session,
            actor=principal.subject,
        )
    except CatalogEditorError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    audit_session.commit()
    return CatalogReloadResponse(
        normalization_loaded=summary.normalization_loaded,
        normalization_errors=summary.normalization_errors,
        firmware_loaded=summary.firmware_loaded,
        firmware_removed=summary.firmware_removed,
        devices_reevaluated=summary.devices_reevaluated,
    )


@router.post(
    "/firmware/upgrade-paths/edges",
    response_model=CatalogReloadResponse,
    summary="Append an upgrade-path edge to the platform YAML",
)
def add_upgrade_edge(
    body: AddUpgradePathEdgeRequest,
    principal: Principal = Depends(require(Permission.MANAGE_FIRMWARE_CATALOG)),
    session: Session = Depends(get_session),
    audit_session: Session = Depends(get_append_only_session),
) -> CatalogReloadResponse:
    _require_editor()
    try:
        add_upgrade_path_edge(
            platform_family=body.platform_family,
            from_version=body.from_version,
            to_version=body.to_version,
            weight=body.weight,
            notes=body.notes,
            file_stem=body.file_stem,
        )
        if not body.reload:
            return CatalogReloadResponse(
                normalization_loaded=0,
                normalization_errors=[],
                firmware_loaded=0,
                firmware_removed=0,
                devices_reevaluated=0,
            )
        summary = reload_catalogs(
            session=session,
            audit_session=audit_session,
            actor=principal.subject,
        )
    except CatalogEditorError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    audit_session.commit()
    return CatalogReloadResponse(
        normalization_loaded=summary.normalization_loaded,
        normalization_errors=summary.normalization_errors,
        firmware_loaded=summary.firmware_loaded,
        firmware_removed=summary.firmware_removed,
        devices_reevaluated=summary.devices_reevaluated,
    )


@router.get(
    "/normalization/rules",
    response_model=NormalizationRuleList,
    summary="List DB-sourced normalization rules (UI-created)",
)
def list_norm_rules(
    _: Principal = Depends(require(Permission.READ_RULE)),
    session: Session = Depends(get_session),
) -> NormalizationRuleList:
    _require_editor()
    rows = list_db_normalization_rules(session)
    items = [
        NormalizationRuleResponse(
            id=r.id,
            priority=r.priority,
            match=dict(r.match),
            output=dict(r.output),
            confidence=r.confidence.value,
            enabled=r.enabled,
            notes=r.notes,
        )
        for r in rows
    ]
    return NormalizationRuleList(items=items, total_returned=len(items))


@router.post(
    "/normalization/rules",
    response_model=NormalizationRuleResponse,
    summary="Create a DB normalization rule for vendor/model mapping",
)
def create_norm_rule(
    body: CreateNormalizationRuleRequest,
    _: Principal = Depends(require(Permission.MANAGE_RULES)),
    session: Session = Depends(get_session),
) -> NormalizationRuleResponse:
    _require_editor()
    try:
        rule = create_db_normalization_rule(
            session,
            model_pattern=body.model_pattern,
            vendor_normalized=body.vendor_normalized,
            platform_family=body.platform_family,
            model_normalized=body.model_normalized,
            priority=body.priority,
            notes=body.notes,
        )
        if body.renormalize:
            renormalize_estate(session)
    except CatalogEditorError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    return NormalizationRuleResponse(
        id=rule.id,
        priority=rule.priority,
        match=dict(rule.match),
        output=dict(rule.output),
        confidence=rule.confidence.value,
        enabled=rule.enabled,
        notes=rule.notes,
    )


@router.post(
    "/devices/renormalize",
    response_model=RenormalizeResponse,
    summary="Re-apply normalization rules to all devices",
)
def renormalize_(
    _: Principal = Depends(require(Permission.MANAGE_RULES)),
    session: Session = Depends(get_session),
) -> RenormalizeResponse:
    _require_editor()
    count = renormalize_estate(session)
    session.commit()
    return RenormalizeResponse(devices_updated=count)
