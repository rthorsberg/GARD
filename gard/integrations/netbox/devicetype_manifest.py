"""Load and validate the F9 curated NetBox device type manifest."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from gard.core.logging import get_logger

_log = get_logger(__name__)

DEFAULT_MANIFEST_REL = Path("gard-catalog/netbox/device-types-manifest.yaml")
DEFAULT_SUBMODULE_REL = Path("vendor/netbox-devicetype-library")
SCHEMA_REL = Path(
    "specs/009-netbox-devicetype-bootstrap/contracts/device-types-manifest.schema.yaml"
)


class DeviceTypeManifestError(Exception):
    """Manifest load or semantic validation failed."""


@dataclass(frozen=True)
class ManifestEntry:
    """One curated device type row."""

    id: str
    vendor_normalized: str
    model_normalized: str | None
    model_raw_aliases: tuple[str, ...]
    library_path: str
    expected_slug: str
    notes: str | None


@dataclass(frozen=True)
class DeviceTypeManifest:
    """Validated manifest with resolved library file paths."""

    schema_version: str
    upstream_repo: str
    upstream_pin: str
    entries: tuple[ManifestEntry, ...]
    manifest_path: Path
    submodule_root: Path

    def library_file(self, entry: ManifestEntry) -> Path:
        return self.submodule_root / entry.library_path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_manifest_path(repo_root: Path | None = None) -> Path:
    root = repo_root or _repo_root()
    return root / DEFAULT_MANIFEST_REL


def default_submodule_root(repo_root: Path | None = None) -> Path:
    root = repo_root or _repo_root()
    return root / DEFAULT_SUBMODULE_REL


def _load_schema(repo_root: Path) -> dict[str, Any]:
    schema_path = repo_root / SCHEMA_REL
    if not schema_path.is_file():
        raise DeviceTypeManifestError(f"manifest schema not found: {schema_path}")
    with schema_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise DeviceTypeManifestError("manifest schema is not a mapping")
    return data


def _parse_entry(raw: dict[str, Any]) -> ManifestEntry:
    aliases = raw.get("model_raw_aliases") or []
    if not isinstance(aliases, list):
        raise DeviceTypeManifestError(f"entry {raw.get('id')!r}: model_raw_aliases must be a list")
    return ManifestEntry(
        id=str(raw["id"]),
        vendor_normalized=str(raw["vendor_normalized"]),
        model_normalized=raw.get("model_normalized"),
        model_raw_aliases=tuple(str(a) for a in aliases),
        library_path=str(raw["library_path"]),
        expected_slug=str(raw["expected_slug"]),
        notes=raw.get("notes"),
    )


def _lint_entries(entries: tuple[ManifestEntry, ...]) -> None:
    seen_ids: set[str] = set()
    seen_slugs: set[str] = set()
    seen_aliases: dict[str, str] = {}

    for entry in entries:
        if entry.id in seen_ids:
            raise DeviceTypeManifestError(f"duplicate manifest entry id: {entry.id!r}")
        seen_ids.add(entry.id)

        if entry.expected_slug in seen_slugs:
            raise DeviceTypeManifestError(
                f"duplicate expected_slug across entries: {entry.expected_slug!r}"
            )
        seen_slugs.add(entry.expected_slug)

        for alias in entry.model_raw_aliases:
            if alias in seen_aliases:
                raise DeviceTypeManifestError(
                    f"alias {alias!r} appears on both {seen_aliases[alias]!r} and {entry.id!r}"
                )
            seen_aliases[alias] = entry.id


def load_manifest(
    *,
    manifest_path: Path | None = None,
    submodule_root: Path | None = None,
    repo_root: Path | None = None,
    require_library_files: bool = True,
) -> DeviceTypeManifest:
    """Load manifest YAML, validate schema, and lint semantic rules."""
    root = repo_root or _repo_root()
    mpath = manifest_path or default_manifest_path(root)
    sub_root = submodule_root or default_submodule_root(root)

    if not mpath.is_file():
        raise DeviceTypeManifestError(f"manifest not found: {mpath}")

    with mpath.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise DeviceTypeManifestError("manifest root must be a mapping")

    schema = _load_schema(root)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(raw), key=lambda e: list(e.path))
    if errors:
        msg = "; ".join(f"{'/'.join(str(p) for p in err.path)}: {err.message}" for err in errors)
        raise DeviceTypeManifestError(f"manifest schema validation failed: {msg}")

    entries_raw = raw.get("entries") or []
    entries = tuple(_parse_entry(item) for item in entries_raw if isinstance(item, dict))
    _lint_entries(entries)

    manifest = DeviceTypeManifest(
        schema_version=str(raw["schema_version"]),
        upstream_repo=str(raw["upstream_repo"]),
        upstream_pin=str(raw["upstream_pin"]),
        entries=entries,
        manifest_path=mpath,
        submodule_root=sub_root,
    )

    if require_library_files:
        validate_library_paths(manifest)

    return manifest


def validate_library_paths(manifest: DeviceTypeManifest) -> None:
    """Ensure every library_path resolves under the submodule root."""
    if not manifest.submodule_root.is_dir():
        raise DeviceTypeManifestError(
            f"device type library submodule missing at {manifest.submodule_root}; "
            "run: git submodule update --init vendor/netbox-devicetype-library"
        )
    for entry in manifest.entries:
        path = manifest.library_file(entry)
        if not path.is_file():
            raise DeviceTypeManifestError(
                f"entry {entry.id!r}: library_path not found at pin: {entry.library_path}"
            )


def resolve_dry_run(manifest: DeviceTypeManifest) -> list[dict[str, str]]:
    """Return resolved paths for dry-run reporting (no NetBox I/O)."""
    out: list[dict[str, str]] = []
    for entry in manifest.entries:
        path = manifest.library_file(entry)
        out.append(
            {
                "id": entry.id,
                "expected_slug": entry.expected_slug,
                "library_path": entry.library_path,
                "resolved_path": str(path),
            }
        )
    _log.info("devicetype_manifest.dry_run", entry_count=len(out), pin=manifest.upstream_pin)
    return out
