"""Load and validate the F10 NetBox write-back manifest."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from gard.core.logging import get_logger

_log = get_logger(__name__)

DEFAULT_MANIFEST_REL = Path("gard-catalog/netbox/write-back-manifest.yaml")
SCHEMA_REL = Path("specs/010-netbox-writeback/contracts/write-back-manifest.schema.yaml")

ALLOWED_GARD_SOURCES = frozenset(
    {
        "lifecycle_state",
        "compliance_summary",
        "readiness_summary",
        "target_firmware",
        "compliance_evaluated_at",
        "readiness_evaluated_at",
        "ipam_alignment_status",
    }
)

_NETBOX_FIELD_RE = re.compile(r"^[a-z0-9_]+$")


class WritebackManifestError(Exception):
    """Manifest load or semantic validation failed."""


@dataclass(frozen=True)
class CustomFieldMapping:
    id: str
    gard_source: str
    netbox_field: str
    netbox_type: str
    description: str | None


@dataclass(frozen=True)
class TagRule:
    slug: str
    apply_when: str
    description: str | None


@dataclass(frozen=True)
class WritebackManifest:
    schema_version: str
    object_type: str
    unknown_sentinel: str
    custom_fields: tuple[CustomFieldMapping, ...]
    tags: tuple[TagRule, ...]
    manifest_path: Path

    @property
    def manifest_tag_slugs(self) -> frozenset[str]:
        return frozenset(t.slug for t in self.tags)

    @property
    def netbox_field_names(self) -> frozenset[str]:
        return frozenset(f.netbox_field for f in self.custom_fields)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_manifest_path(repo_root: Path | None = None) -> Path:
    root = repo_root or _repo_root()
    return root / DEFAULT_MANIFEST_REL


def _load_schema(repo_root: Path) -> dict[str, Any]:
    schema_path = repo_root / SCHEMA_REL
    if not schema_path.is_file():
        raise WritebackManifestError(f"manifest schema not found: {schema_path}")
    with schema_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise WritebackManifestError("manifest schema is not a mapping")
    return data


def _parse_custom_field(raw: dict[str, Any]) -> CustomFieldMapping:
    return CustomFieldMapping(
        id=str(raw["id"]),
        gard_source=str(raw["gard_source"]),
        netbox_field=str(raw["netbox_field"]),
        netbox_type=str(raw["netbox_type"]),
        description=raw.get("description"),
    )


def _parse_tag(raw: dict[str, Any]) -> TagRule:
    return TagRule(
        slug=str(raw["slug"]),
        apply_when=str(raw["apply_when"]),
        description=raw.get("description"),
    )


def _lint_manifest(
    custom_fields: tuple[CustomFieldMapping, ...],
    tags: tuple[TagRule, ...],
) -> None:
    seen_ids: set[str] = set()
    seen_fields: set[str] = set()
    seen_slugs: set[str] = set()

    for field in custom_fields:
        if field.id in seen_ids:
            raise WritebackManifestError(f"duplicate custom field id: {field.id!r}")
        seen_ids.add(field.id)

        if field.gard_source not in ALLOWED_GARD_SOURCES:
            raise WritebackManifestError(
                f"custom field {field.id!r}: unknown gard_source {field.gard_source!r}"
            )

        if field.netbox_field in seen_fields:
            raise WritebackManifestError(f"duplicate netbox_field: {field.netbox_field!r}")
        if not _NETBOX_FIELD_RE.match(field.netbox_field):
            raise WritebackManifestError(
                f"netbox_field {field.netbox_field!r} must match [a-z0-9_]+"
            )
        seen_fields.add(field.netbox_field)

    for tag in tags:
        if tag.slug in seen_slugs:
            raise WritebackManifestError(f"duplicate tag slug: {tag.slug!r}")
        seen_slugs.add(tag.slug)


def load_writeback_manifest(
    *,
    manifest_path: Path | None = None,
    repo_root: Path | None = None,
) -> WritebackManifest:
    """Load manifest YAML, validate schema, and lint semantic rules."""
    root = repo_root or _repo_root()
    mpath = manifest_path or default_manifest_path(root)

    if not mpath.is_file():
        raise WritebackManifestError(f"manifest not found: {mpath}")

    with mpath.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise WritebackManifestError("manifest root must be a mapping")

    schema = _load_schema(root)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(raw), key=lambda e: list(e.path))
    if errors:
        msg = "; ".join(f"{'/'.join(str(p) for p in err.path)}: {err.message}" for err in errors)
        raise WritebackManifestError(f"manifest schema validation failed: {msg}")

    fields_raw = raw.get("custom_fields") or []
    tags_raw = raw.get("tags") or []
    custom_fields = tuple(
        _parse_custom_field(item) for item in fields_raw if isinstance(item, dict)
    )
    tags = tuple(_parse_tag(item) for item in tags_raw if isinstance(item, dict))
    _lint_manifest(custom_fields, tags)

    return WritebackManifest(
        schema_version=str(raw["schema_version"]),
        object_type=str(raw["object_type"]),
        unknown_sentinel=str(raw["unknown_sentinel"]),
        custom_fields=custom_fields,
        tags=tags,
        manifest_path=mpath,
    )


def validate_manifest_dry_run(manifest: WritebackManifest) -> dict[str, Any]:
    """Return a validation report without NetBox I/O."""
    report = {
        "schema_version": manifest.schema_version,
        "object_type": manifest.object_type,
        "unknown_sentinel": manifest.unknown_sentinel,
        "custom_field_count": len(manifest.custom_fields),
        "tag_count": len(manifest.tags),
        "custom_fields": [
            {
                "id": f.id,
                "gard_source": f.gard_source,
                "netbox_field": f.netbox_field,
                "netbox_type": f.netbox_type,
            }
            for f in manifest.custom_fields
        ],
        "tags": [{"slug": t.slug, "apply_when": t.apply_when} for t in manifest.tags],
    }
    _log.info(
        "writeback_manifest.dry_run",
        custom_fields=len(manifest.custom_fields),
        tags=len(manifest.tags),
    )
    return report
