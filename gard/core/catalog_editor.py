"""Lab catalog editor — write YAML on disk and reload into DB.

ADR-0011 keeps git/PR as the production authority. When
``catalog_editor_enabled`` is true (dev/lab), operators may mutate
catalog files via the admin API and UI instead of hand-editing YAML.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.api.schemas.csv_row import CsvRow
from gard.catalog.normalization_loader import load_catalog
from gard.core.device_controller import upsert_from_row
from gard.core.firmware_catalog_controller import reload as fw_reload
from gard.core.normalization_engine import normalize
from gard.core.scope_selector import validate_keys
from gard.core.settings import get_settings
from gard.models import Device, DeviceObservation, NormalizationRule
from gard.models._enums import Confidence, RuleSource

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


class CatalogEditorError(ValueError):
    pass


@dataclass(frozen=True)
class ReloadSummary:
    normalization_loaded: int
    normalization_errors: list[str]
    firmware_loaded: int
    firmware_removed: int
    devices_reevaluated: int


def _targets_dir() -> Path:
    return get_settings().firmware_catalog_root / "targets"


def _upgrade_paths_dir() -> Path:
    return get_settings().firmware_catalog_root / "upgrade-paths"


def _validate_name(name: str) -> str:
    slug = name.strip().lower()
    if not _NAME_RE.match(slug):
        raise CatalogEditorError(
            "name must be lowercase alphanumeric/hyphen, 1–63 chars (e.g. cisco-ios-isr1121)"
        )
    return slug


def upsert_firmware_target(
    *,
    name: str,
    platform_family: str,
    target_version: str,
    scope_selector: dict[str, Any],
    notes: str | None = None,
) -> Path:
    slug = _validate_name(name)
    try:
        validate_keys(scope_selector)
    except Exception as exc:
        raise CatalogEditorError(str(exc)) from exc
    if not scope_selector:
        raise CatalogEditorError("scope_selector must include at least one key")

    doc: dict[str, Any] = {
        "catalog_schema_version": "1.0.0",
        "name": slug,
        "platform_family": platform_family.strip(),
        "target_version": str(target_version),
        "scope_selector": scope_selector,
    }
    if notes:
        doc["notes"] = notes.strip()

    path = _targets_dir() / f"{slug}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def delete_firmware_target(name: str) -> None:
    slug = _validate_name(name)
    path = _targets_dir() / f"{slug}.yaml"
    if not path.exists():
        raise CatalogEditorError(f"target file not found: {slug}")
    path.unlink()


def add_upgrade_path_edge(
    *,
    platform_family: str,
    from_version: str,
    to_version: str,
    weight: int = 1,
    notes: str | None = None,
    file_stem: str | None = None,
) -> Path:
    pf = platform_family.strip()
    stem = file_stem or pf.replace("_", "-")
    path = _upgrade_paths_dir() / f"{stem}.yaml"

    doc: dict[str, Any]
    if path.exists():
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    else:
        doc = {
            "catalog_schema_version": "1.0.0",
            "platform_family": pf,
            "edges": [],
        }

    if doc.get("platform_family") != pf:
        doc["platform_family"] = pf
    edges: list[dict[str, Any]] = list(doc.get("edges") or [])

    for edge in edges:
        if edge.get("from_version") == from_version and edge.get("to_version") == to_version:
            raise CatalogEditorError(f"edge {from_version} → {to_version} already exists")

    new_edge: dict[str, Any] = {
        "from_version": str(from_version),
        "to_version": str(to_version),
        "weight": weight,
    }
    if notes:
        new_edge["notes"] = notes.strip()
    edges.append(new_edge)
    doc["edges"] = edges

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def create_db_normalization_rule(
    session: Session,
    *,
    model_pattern: str,
    vendor_normalized: str,
    platform_family: str,
    model_normalized: str | None = None,
    priority: int = 200,
    notes: str | None = None,
) -> NormalizationRule:
    rule_id = f"ui-{uuid.uuid4().hex[:12]}"
    output: dict[str, Any] = {
        "vendor_normalized": vendor_normalized.strip().lower(),
        "platform_family": platform_family.strip().lower(),
    }
    if model_normalized and model_normalized.strip():
        output["model_normalized"] = model_normalized.strip()
    rule = NormalizationRule(
        id=rule_id,
        priority=priority,
        match={"model_raw_regex": model_pattern},
        output=output,
        confidence=Confidence.high,
        source=RuleSource.db,
        enabled=True,
        notes=notes,
    )
    session.add(rule)
    session.flush()
    return rule


def list_db_normalization_rules(session: Session) -> list[NormalizationRule]:
    return list(
        session.scalars(
            select(NormalizationRule)
            .where(NormalizationRule.source == RuleSource.db)
            .order_by(NormalizationRule.priority.desc(), NormalizationRule.created_at.desc())
        )
    )


def renormalize_estate(session: Session) -> int:
    """Re-apply normalization rules to every device from its latest observation."""
    updated = 0
    devices = session.scalars(select(Device)).all()
    for device in devices:
        latest = session.scalar(
            select(DeviceObservation)
            .where(DeviceObservation.device_id == device.id)
            .order_by(DeviceObservation.created_at.desc())
            .limit(1)
        )
        raw = (latest.raw_payload if latest else {}) or {}
        row = CsvRow(
            hostname=device.hostname,
            site=device.site,
            serial_number=device.serial_number,
            vendor_raw=device.vendor_raw,
            model_raw=device.model_raw,
            platform_family_raw=raw.get("platform_family_raw") or device.platform_family,
            hardware_revision=device.hardware_revision,
            management_ip=str(device.management_ip) if device.management_ip else None,
            region=device.region,
            role=device.role,
            observed_firmware=latest.observed_firmware if latest else None,
            observed_bootloader=latest.observed_bootloader if latest else None,
            observed_at=latest.observed_at if latest else None,
            ram_mb=device.ram_mb,
            disk_mb=device.disk_mb,
            licenses=";".join(device.licenses) if device.licenses else None,
        )
        norm = normalize(session=session, row=row, observation_id=latest.id if latest else None)
        upsert_from_row(
            session=session,
            row=row,
            normalization=norm,
            source_system=device.source_system,
        )
        updated += 1
    return updated


def reload_catalogs(
    *,
    session: Session,
    audit_session: Session,
    actor: str,
) -> ReloadSummary:
    settings = get_settings()
    norm_report = load_catalog(session, settings.catalog_root)
    fw_outcome = fw_reload(
        session=session,
        audit_session=audit_session,
        catalog_root=settings.firmware_catalog_root,
        actor=actor,
    )
    if not fw_outcome.success:
        err = fw_outcome.error
        raise CatalogEditorError(
            f"firmware catalog reload failed: {err.file_relpath if err else '?'} — "
            f"{err.reason if err else 'unknown'}"
        )
    report = fw_outcome.report
    return ReloadSummary(
        normalization_loaded=norm_report.loaded,
        normalization_errors=list(norm_report.errors),
        firmware_loaded=report.loaded if report else 0,
        firmware_removed=report.removed if report else 0,
        devices_reevaluated=fw_outcome.devices_reevaluated,
    )
