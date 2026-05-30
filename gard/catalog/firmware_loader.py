"""F2 firmware-catalog YAML loader.

Single transactional load function — reads the four YAML trees under
``<root>/{targets,packages,upgrade-paths,prerequisites}/`` and upserts /
soft-deletes the matching ORM rows. Per ADR-0011 the load is **all or
nothing**: any schema violation, FS conflict, duplicate identity, or
unknown scope-selector key raises and the caller (controller) rolls back
the entire transaction.

The loader does NOT emit audit events itself — that's the controller's
job after a successful pass. Returning a structured :class:`LoadReport`
lets the controller diff before/after states and emit the right audit
families with the file's git SHA attached.

Loader keys (used to detect "this file was previously loaded, has it
changed?"):

- target:   ``name``
- package:  ``(vendor, platform_family, version)``
- upgrade:  ``(platform_family, from_version, to_version)`` per edge
- prereq:   ``name``
"""

from __future__ import annotations

import datetime as dt
import importlib.resources as ir
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from gard.core.logging import get_logger
from gard.core.scope_selector import UnknownSelectorKey, validate_keys
from gard.models import (
    FirmwarePackage,
    FirmwarePrerequisiteRule,
    FirmwareTarget,
    FirmwareUpgradePath,
)

_log = get_logger(__name__)

CATALOG_SCHEMA_VERSION = "1.0.0"


# ---- error envelope ---------------------------------------------------


class FirmwareCatalogLoadError(Exception):
    """Raised on any validation / FS / duplicate-identity failure.

    Carries the offending file's relative path + a human-readable reason
    so the controller can emit ``firmware_catalog.reload_failed`` with
    structured ``after`` payload.
    """

    def __init__(self, *, file_relpath: str, reason: str, schema_path: str | None = None) -> None:
        self.file_relpath = file_relpath
        self.reason = reason
        self.schema_path = schema_path
        super().__init__(f"{file_relpath}: {reason}")


# ---- reports ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RowDelta:
    """One row's change observed during a load pass."""

    kind: str  # "target" | "package" | "upgrade_path" | "prerequisite"
    entity_id: str  # str(uuid)
    action: str  # "loaded" | "removed" | "unchanged"
    natural_key: str  # human-readable
    source_file_relpath: str
    after: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoadReport:
    """Aggregate result of a single load pass.

    The controller post-processes this into a sequence of AuditEvent emits;
    callers wanting the rolled-up counts can read the totals directly.
    """

    deltas: list[RowDelta] = field(default_factory=list)
    file_relpaths_seen: set[str] = field(default_factory=set)

    @property
    def loaded(self) -> int:
        return sum(1 for d in self.deltas if d.action == "loaded")

    @property
    def removed(self) -> int:
        return sum(1 for d in self.deltas if d.action == "removed")

    @property
    def unchanged(self) -> int:
        return sum(1 for d in self.deltas if d.action == "unchanged")


# ---- schema loading ---------------------------------------------------


def _runtime_schemas() -> dict[str, dict[str, Any]]:
    """Load the five JSON Schema YAMLs from the runtime path."""
    files = {
        "firmware-target.schema.yaml": "target",
        "firmware-package.schema.yaml": "package",
        "firmware-upgrade-path.schema.yaml": "upgrade_path",
        "firmware-prerequisite.schema.yaml": "prerequisite",
        "scope-selector.schema.yaml": "scope_selector",
    }
    out: dict[str, dict[str, Any]] = {}
    pkg = ir.files("gard.catalog.schemas.firmware")
    for fname, key in files.items():
        out[key] = yaml.safe_load((pkg / fname).read_text(encoding="utf-8"))
    return out


def _make_validators() -> dict[str, Draft202012Validator]:
    schemas = _runtime_schemas()
    # The schemas reference scope-selector.schema.yaml via $ref. The
    # jsonschema library needs a registry to resolve that — we inline the
    # selector schema instead, since it's only referenced from two places
    # and the indirection adds no value at v1 scale.
    selector_schema = schemas["scope_selector"]
    target_schema = dict(schemas["target"])
    target_schema["properties"] = dict(target_schema["properties"])
    target_schema["properties"]["scope_selector"] = selector_schema
    prereq_schema = dict(schemas["prerequisite"])
    prereq_schema["properties"] = dict(prereq_schema["properties"])
    prereq_schema["properties"]["applies_to"] = selector_schema
    return {
        "target": Draft202012Validator(target_schema),
        "package": Draft202012Validator(schemas["package"]),
        "upgrade_path": Draft202012Validator(schemas["upgrade_path"]),
        "prerequisite": Draft202012Validator(prereq_schema),
    }


_VALIDATORS: dict[str, Draft202012Validator] | None = None


def get_validators() -> dict[str, Draft202012Validator]:
    """Lazy module-global validator cache. Test helper: clears via reset()."""
    global _VALIDATORS
    if _VALIDATORS is None:
        _VALIDATORS = _make_validators()
    return _VALIDATORS


def reset_validator_cache() -> None:  # pragma: no cover -- test helper
    global _VALIDATORS
    _VALIDATORS = None


# ---- file walkers -----------------------------------------------------


def _iter_yaml_files(root: Path, subdir: str) -> list[tuple[Path, str]]:
    """Return [(absolute_path, relpath_from_root)] sorted by relpath."""
    dir_ = root / subdir
    if not dir_.exists():
        return []
    out: list[tuple[Path, str]] = []
    for p in sorted(dir_.glob("*.yaml")):
        rel = str(p.relative_to(root))
        out.append((p, rel))
    return out


def _load_yaml(path: Path, relpath: str) -> dict[str, Any]:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise FirmwareCatalogLoadError(
            file_relpath=relpath, reason=f"yaml parse error: {exc}"
        ) from exc
    if not isinstance(doc, dict):
        raise FirmwareCatalogLoadError(file_relpath=relpath, reason="root must be a mapping")
    if doc.get("catalog_schema_version") != CATALOG_SCHEMA_VERSION:
        raise FirmwareCatalogLoadError(
            file_relpath=relpath,
            reason=(
                f"catalog_schema_version must be {CATALOG_SCHEMA_VERSION!r}, "
                f"got {doc.get('catalog_schema_version')!r}"
            ),
        )
    return doc


def _validate(doc: dict[str, Any], kind: str, relpath: str) -> None:
    validator = get_validators()[kind]
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    if errors:
        e = errors[0]
        path_str = "/".join(str(p) for p in e.path) or "<root>"
        raise FirmwareCatalogLoadError(
            file_relpath=relpath,
            reason=f"schema violation at {path_str}: {e.message}",
            schema_path="/".join(str(p) for p in e.schema_path),
        )


# ---- per-entity loaders ----------------------------------------------


def _load_targets(session: Session, root: Path, report: LoadReport) -> None:
    files = _iter_yaml_files(root, "targets")
    loaded_keys: set[str] = set()
    for path, relpath in files:
        report.file_relpaths_seen.add(relpath)
        doc = _load_yaml(path, relpath)
        _validate(doc, "target", relpath)
        try:
            validate_keys(doc["scope_selector"])
        except UnknownSelectorKey as exc:
            raise FirmwareCatalogLoadError(file_relpath=relpath, reason=str(exc)) from exc

        name = doc["name"]
        if name in loaded_keys:
            raise FirmwareCatalogLoadError(
                file_relpath=relpath, reason=f"duplicate target name {name!r} in this load"
            )
        loaded_keys.add(name)

        valid_from = _parse_iso_date(doc.get("valid_from"), relpath, "valid_from")
        valid_until = _parse_iso_date(doc.get("valid_until"), relpath, "valid_until")

        existing = session.scalar(select(FirmwareTarget).where(FirmwareTarget.name == name))
        after_payload = {
            "name": name,
            "platform_family": doc["platform_family"],
            "target_version": doc["target_version"],
            "source_file_relpath": relpath,
        }
        if existing is None:
            row = FirmwareTarget(
                name=name,
                platform_family=doc["platform_family"],
                target_version=doc["target_version"],
                scope_selector=doc["scope_selector"],
                valid_from=valid_from,
                valid_until=valid_until,
                notes=doc.get("notes"),
                source_file_relpath=relpath,
                catalog_schema_version=CATALOG_SCHEMA_VERSION,
            )
            session.add(row)
            session.flush()
            report.deltas.append(
                RowDelta(
                    kind="target",
                    entity_id=str(row.id),
                    action="loaded",
                    natural_key=name,
                    source_file_relpath=relpath,
                    after=after_payload,
                )
            )
        else:
            changed = (
                existing.removed_at is not None
                or existing.platform_family != doc["platform_family"]
                or existing.target_version != doc["target_version"]
                or existing.scope_selector != doc["scope_selector"]
                or existing.valid_from != valid_from
                or existing.valid_until != valid_until
                or existing.notes != doc.get("notes")
                or existing.source_file_relpath != relpath
            )
            existing.removed_at = None
            existing.platform_family = doc["platform_family"]
            existing.target_version = doc["target_version"]
            existing.scope_selector = doc["scope_selector"]
            existing.valid_from = valid_from
            existing.valid_until = valid_until
            existing.notes = doc.get("notes")
            existing.source_file_relpath = relpath
            existing.catalog_schema_version = CATALOG_SCHEMA_VERSION
            report.deltas.append(
                RowDelta(
                    kind="target",
                    entity_id=str(existing.id),
                    action="loaded" if changed else "unchanged",
                    natural_key=name,
                    source_file_relpath=relpath,
                    after=after_payload,
                )
            )

    # Soft-delete every target whose source_file_relpath is no longer on disk
    seen_relpaths = {rp for _, rp in files}
    stale = session.scalars(select(FirmwareTarget).where(FirmwareTarget.removed_at.is_(None))).all()
    for row in stale:
        if row.source_file_relpath in seen_relpaths:
            continue
        row.removed_at = dt.datetime.now(dt.UTC)
        report.deltas.append(
            RowDelta(
                kind="target",
                entity_id=str(row.id),
                action="removed",
                natural_key=row.name,
                source_file_relpath=row.source_file_relpath,
                after={"name": row.name, "source_file_relpath": row.source_file_relpath},
            )
        )


def _parse_iso_date(value: Any, relpath: str, field: str) -> dt.date | None:
    """Normalize a YAML scalar into a ``datetime.date`` for DB comparison.

    PyYAML safe_load returns ``date`` for unquoted ``YYYY-MM-DD`` literals,
    but our sample fixtures quote them (to avoid YAML 1.1 / 1.2 ambiguity).
    Without normalization, ``existing.release_date (date) != doc[...] (str)``
    is always True and the row reloads every pass, breaking the idempotency
    contract in spec.md (Assumptions / FR-014).
    """
    if value is None:
        return None
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value)
        except ValueError as exc:
            raise FirmwareCatalogLoadError(
                file_relpath=relpath,
                reason=f"{field}: expected ISO date, got {value!r}: {exc}",
            ) from exc
    raise FirmwareCatalogLoadError(
        file_relpath=relpath,
        reason=f"{field}: expected ISO date string, got {type(value).__name__}",
    )


def _load_packages(session: Session, root: Path, report: LoadReport) -> None:
    files = _iter_yaml_files(root, "packages")
    loaded_keys: set[tuple[str, str, str]] = set()
    for path, relpath in files:
        report.file_relpaths_seen.add(relpath)
        doc = _load_yaml(path, relpath)
        _validate(doc, "package", relpath)
        nk = (doc["vendor"], doc["platform_family"], doc["version"])
        if nk in loaded_keys:
            raise FirmwareCatalogLoadError(
                file_relpath=relpath,
                reason=f"duplicate package natural key {nk!r} in this load",
            )
        loaded_keys.add(nk)

        release_date = _parse_iso_date(doc.get("release_date"), relpath, "release_date")

        existing = session.scalar(
            select(FirmwarePackage)
            .where(FirmwarePackage.vendor == doc["vendor"])
            .where(FirmwarePackage.platform_family == doc["platform_family"])
            .where(FirmwarePackage.version == doc["version"])
        )
        after_payload = {
            "vendor": doc["vendor"],
            "platform_family": doc["platform_family"],
            "version": doc["version"],
            "sha256": doc["sha256"],
            "byte_size": doc["byte_size"],
            "source_file_relpath": relpath,
        }
        if existing is None:
            row = FirmwarePackage(
                vendor=doc["vendor"],
                platform_family=doc["platform_family"],
                version=doc["version"],
                sha256=doc["sha256"],
                byte_size=doc["byte_size"],
                signed_by=doc["signed_by"],
                release_date=release_date,
                download_url=doc.get("download_url"),
                notes=doc.get("notes"),
                source_file_relpath=relpath,
                catalog_schema_version=CATALOG_SCHEMA_VERSION,
            )
            session.add(row)
            session.flush()
            report.deltas.append(
                RowDelta(
                    kind="package",
                    entity_id=str(row.id),
                    action="loaded",
                    natural_key=f"{nk[0]}/{nk[1]}/{nk[2]}",
                    source_file_relpath=relpath,
                    after=after_payload,
                )
            )
        else:
            # SHA collision check: if the live row carries a different SHA
            # for the same natural key, that's a hard conflict (FR-007).
            if existing.removed_at is None and existing.sha256 != doc["sha256"]:
                raise FirmwareCatalogLoadError(
                    file_relpath=relpath,
                    reason=(
                        f"package {nk!r} already declared with sha256="
                        f"{existing.sha256!r}; refusing to overwrite with "
                        f"{doc['sha256']!r} from {relpath}"
                    ),
                )
            changed = (
                existing.removed_at is not None
                or existing.sha256 != doc["sha256"]
                or existing.byte_size != doc["byte_size"]
                or existing.signed_by != doc["signed_by"]
                or existing.release_date != release_date
                or existing.download_url != doc.get("download_url")
                or existing.notes != doc.get("notes")
                or existing.source_file_relpath != relpath
            )
            existing.removed_at = None
            existing.sha256 = doc["sha256"]
            existing.byte_size = doc["byte_size"]
            existing.signed_by = doc["signed_by"]
            existing.release_date = release_date
            existing.download_url = doc.get("download_url")
            existing.notes = doc.get("notes")
            existing.source_file_relpath = relpath
            existing.catalog_schema_version = CATALOG_SCHEMA_VERSION
            report.deltas.append(
                RowDelta(
                    kind="package",
                    entity_id=str(existing.id),
                    action="loaded" if changed else "unchanged",
                    natural_key=f"{nk[0]}/{nk[1]}/{nk[2]}",
                    source_file_relpath=relpath,
                    after=after_payload,
                )
            )

    seen_relpaths = {rp for _, rp in files}
    stale = session.scalars(
        select(FirmwarePackage).where(FirmwarePackage.removed_at.is_(None))
    ).all()
    for row in stale:
        if row.source_file_relpath in seen_relpaths:
            continue
        row.removed_at = dt.datetime.now(dt.UTC)
        report.deltas.append(
            RowDelta(
                kind="package",
                entity_id=str(row.id),
                action="removed",
                natural_key=f"{row.vendor}/{row.platform_family}/{row.version}",
                source_file_relpath=row.source_file_relpath,
                after={
                    "vendor": row.vendor,
                    "platform_family": row.platform_family,
                    "version": row.version,
                    "source_file_relpath": row.source_file_relpath,
                },
            )
        )


def _load_upgrade_paths(session: Session, root: Path, report: LoadReport) -> None:
    files = _iter_yaml_files(root, "upgrade-paths")
    # Per-(platform_family, from, to) deduplication across files.
    seen_edges: dict[tuple[str, str, str], str] = {}
    for path, relpath in files:
        report.file_relpaths_seen.add(relpath)
        doc = _load_yaml(path, relpath)
        _validate(doc, "upgrade_path", relpath)
        pf = doc["platform_family"]
        for edge in doc["edges"]:
            ek = (pf, edge["from_version"], edge["to_version"])
            prior = seen_edges.get(ek)
            if prior is not None:
                raise FirmwareCatalogLoadError(
                    file_relpath=relpath,
                    reason=(f"edge {ek!r} also declared in {prior!r}; refusing duplicate"),
                )
            seen_edges[ek] = relpath

            existing = session.scalar(
                select(FirmwareUpgradePath)
                .where(FirmwareUpgradePath.platform_family == pf)
                .where(FirmwareUpgradePath.from_version == edge["from_version"])
                .where(FirmwareUpgradePath.to_version == edge["to_version"])
            )
            weight = int(edge.get("weight", 1))
            after_payload = {
                "platform_family": pf,
                "from_version": edge["from_version"],
                "to_version": edge["to_version"],
                "weight": weight,
                "source_file_relpath": relpath,
            }
            natural = f"{pf}:{edge['from_version']}->{edge['to_version']}"
            if existing is None:
                row = FirmwareUpgradePath(
                    platform_family=pf,
                    from_version=edge["from_version"],
                    to_version=edge["to_version"],
                    weight=weight,
                    notes=edge.get("notes"),
                    source_file_relpath=relpath,
                    catalog_schema_version=CATALOG_SCHEMA_VERSION,
                )
                session.add(row)
                session.flush()
                report.deltas.append(
                    RowDelta(
                        kind="upgrade_path",
                        entity_id=str(row.id),
                        action="loaded",
                        natural_key=natural,
                        source_file_relpath=relpath,
                        after=after_payload,
                    )
                )
            else:
                changed = (
                    existing.removed_at is not None
                    or existing.weight != weight
                    or existing.notes != edge.get("notes")
                    or existing.source_file_relpath != relpath
                )
                existing.removed_at = None
                existing.weight = weight
                existing.notes = edge.get("notes")
                existing.source_file_relpath = relpath
                existing.catalog_schema_version = CATALOG_SCHEMA_VERSION
                report.deltas.append(
                    RowDelta(
                        kind="upgrade_path",
                        entity_id=str(existing.id),
                        action="loaded" if changed else "unchanged",
                        natural_key=natural,
                        source_file_relpath=relpath,
                        after=after_payload,
                    )
                )

    # Soft-delete edges no longer in any file
    seen_relpaths = {rp for _, rp in files}
    stale_edges = session.scalars(
        select(FirmwareUpgradePath).where(FirmwareUpgradePath.removed_at.is_(None))
    ).all()
    for row in stale_edges:
        ek = (row.platform_family, row.from_version, row.to_version)
        if ek in seen_edges and row.source_file_relpath == seen_edges[ek]:
            continue
        if row.source_file_relpath in seen_relpaths:
            # File still exists but didn't redeclare this edge → remove.
            row.removed_at = dt.datetime.now(dt.UTC)
        else:
            row.removed_at = dt.datetime.now(dt.UTC)
        if row.removed_at is not None:
            report.deltas.append(
                RowDelta(
                    kind="upgrade_path",
                    entity_id=str(row.id),
                    action="removed",
                    natural_key=f"{row.platform_family}:{row.from_version}->{row.to_version}",
                    source_file_relpath=row.source_file_relpath,
                    after={
                        "platform_family": row.platform_family,
                        "from_version": row.from_version,
                        "to_version": row.to_version,
                        "source_file_relpath": row.source_file_relpath,
                    },
                )
            )


def _load_prerequisites(session: Session, root: Path, report: LoadReport) -> None:
    files = _iter_yaml_files(root, "prerequisites")
    loaded_keys: set[str] = set()
    for path, relpath in files:
        report.file_relpaths_seen.add(relpath)
        doc = _load_yaml(path, relpath)
        _validate(doc, "prerequisite", relpath)
        try:
            validate_keys(doc["applies_to"])
        except UnknownSelectorKey as exc:
            raise FirmwareCatalogLoadError(file_relpath=relpath, reason=str(exc)) from exc

        name = doc["name"]
        if name in loaded_keys:
            raise FirmwareCatalogLoadError(
                file_relpath=relpath, reason=f"duplicate prerequisite name {name!r} in this load"
            )
        loaded_keys.add(name)

        predicate = doc["predicate"]
        predicate_kind = predicate["kind"]
        predicate_args = {k: v for k, v in predicate.items() if k != "kind"}
        evaluable = predicate_kind != "tagged_with"  # FR-024
        severity = doc.get("severity", "required")

        existing = session.scalar(
            select(FirmwarePrerequisiteRule).where(FirmwarePrerequisiteRule.name == name)
        )
        after_payload = {
            "name": name,
            "predicate_kind": predicate_kind,
            "evaluable": evaluable,
            "source_file_relpath": relpath,
        }
        if existing is None:
            row = FirmwarePrerequisiteRule(
                name=name,
                applies_to=doc["applies_to"],
                predicate_kind=predicate_kind,
                predicate_args=predicate_args,
                severity=severity,
                evaluable=evaluable,
                source_file_relpath=relpath,
                catalog_schema_version=CATALOG_SCHEMA_VERSION,
            )
            session.add(row)
            session.flush()
            report.deltas.append(
                RowDelta(
                    kind="prerequisite",
                    entity_id=str(row.id),
                    action="loaded",
                    natural_key=name,
                    source_file_relpath=relpath,
                    after=after_payload,
                )
            )
        else:
            changed = (
                existing.removed_at is not None
                or existing.applies_to != doc["applies_to"]
                or existing.predicate_kind != predicate_kind
                or existing.predicate_args != predicate_args
                or existing.severity != severity
                or existing.evaluable != evaluable
                or existing.source_file_relpath != relpath
            )
            existing.removed_at = None
            existing.applies_to = doc["applies_to"]
            existing.predicate_kind = predicate_kind
            existing.predicate_args = predicate_args
            existing.severity = severity
            existing.evaluable = evaluable
            existing.source_file_relpath = relpath
            existing.catalog_schema_version = CATALOG_SCHEMA_VERSION
            report.deltas.append(
                RowDelta(
                    kind="prerequisite",
                    entity_id=str(existing.id),
                    action="loaded" if changed else "unchanged",
                    natural_key=name,
                    source_file_relpath=relpath,
                    after=after_payload,
                )
            )

    seen_relpaths = {rp for _, rp in files}
    stale = session.scalars(
        select(FirmwarePrerequisiteRule).where(FirmwarePrerequisiteRule.removed_at.is_(None))
    ).all()
    for row in stale:
        if row.source_file_relpath in seen_relpaths:
            continue
        row.removed_at = dt.datetime.now(dt.UTC)
        report.deltas.append(
            RowDelta(
                kind="prerequisite",
                entity_id=str(row.id),
                action="removed",
                natural_key=row.name,
                source_file_relpath=row.source_file_relpath,
                after={"name": row.name, "source_file_relpath": row.source_file_relpath},
            )
        )


# ---- public entry point ----------------------------------------------


def load_firmware_catalog(session: Session, root: Path) -> LoadReport:
    """Load every YAML under ``<root>/{targets,packages,upgrade-paths,prerequisites}``.

    Raises :class:`FirmwareCatalogLoadError` on any failure; the caller is
    expected to roll back the session and emit a ``firmware_catalog.reload_failed``
    audit row.

    The function uses ``session.flush()`` (not ``commit()``) so the caller
    owns the transaction boundary. This is what makes the loader composable
    with other startup work (e.g. F1 normalization rules) in a single
    transaction.
    """
    if not root.exists():
        raise FirmwareCatalogLoadError(
            file_relpath=str(root),
            reason=f"firmware catalog root does not exist: {root}",
        )

    report = LoadReport()
    _load_targets(session, root, report)
    _load_packages(session, root, report)
    _load_upgrade_paths(session, root, report)
    _load_prerequisites(session, root, report)
    session.flush()
    _log.info(
        "firmware_catalog.loaded",
        loaded=report.loaded,
        removed=report.removed,
        unchanged=report.unchanged,
        files=len(report.file_relpaths_seen),
    )
    return report
