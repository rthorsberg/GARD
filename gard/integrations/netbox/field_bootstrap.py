"""Dev/lab bootstrap for NetBox custom fields and tags (F10)."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from gard.integrations.netbox.write_client import NetboxWriteClient, NetboxWriteError
from gard.integrations.netbox.writeback_manifest import WritebackManifest

_NETBOX_TYPE_MAP = {
    "text": "text",
    "longtext": "longtext",
    "integer": "integer",
    "date": "date",
    "datetime": "datetime",
}


class BootstrapEntryStatus(enum.StrEnum):
    created = "created"
    skipped = "skipped"
    failed = "failed"


@dataclass
class FieldBootstrapEntry:
    id: str
    kind: str
    status: BootstrapEntryStatus
    message: str | None = None


@dataclass
class FieldBootstrapSummary:
    created: int = 0
    skipped: int = 0
    failed: int = 0


@dataclass
class FieldBootstrapReport:
    entries: list[FieldBootstrapEntry] = field(default_factory=list)
    summary: FieldBootstrapSummary = field(default_factory=FieldBootstrapSummary)


def _object_type_to_netbox(object_type: str) -> list[str]:
    # NetBox REST expects content type labels like "dcim.device"
    return [object_type]


def run_field_bootstrap(
    client: NetboxWriteClient,
    manifest: WritebackManifest,
) -> FieldBootstrapReport:
    report = FieldBootstrapReport()
    object_types = _object_type_to_netbox(manifest.object_type)

    for mapping in manifest.custom_fields:
        nb_type = _NETBOX_TYPE_MAP.get(mapping.netbox_type)
        if nb_type is None:
            report.entries.append(
                FieldBootstrapEntry(
                    id=mapping.id,
                    kind="custom_field",
                    status=BootstrapEntryStatus.failed,
                    message=f"unsupported netbox_type {mapping.netbox_type!r}",
                )
            )
            report.summary.failed += 1
            continue
        try:
            existing = client.get_by_name("api/extras/custom-fields/", mapping.netbox_field)
            if existing:
                report.entries.append(
                    FieldBootstrapEntry(
                        id=mapping.id,
                        kind="custom_field",
                        status=BootstrapEntryStatus.skipped,
                        message="already exists",
                    )
                )
                report.summary.skipped += 1
            else:
                client.ensure_custom_field(
                    name=mapping.netbox_field,
                    label=mapping.netbox_field.replace("_", " ").title(),
                    field_type=nb_type,
                    object_types=object_types,
                    description=mapping.description,
                )
                report.entries.append(
                    FieldBootstrapEntry(
                        id=mapping.id,
                        kind="custom_field",
                        status=BootstrapEntryStatus.created,
                    )
                )
                report.summary.created += 1
        except NetboxWriteError as exc:
            report.entries.append(
                FieldBootstrapEntry(
                    id=mapping.id,
                    kind="custom_field",
                    status=BootstrapEntryStatus.failed,
                    message=str(exc),
                )
            )
            report.summary.failed += 1

    for tag in manifest.tags:
        try:
            existing = client.get_by_slug("api/extras/tags/", tag.slug)
            if existing:
                report.entries.append(
                    FieldBootstrapEntry(
                        id=tag.slug,
                        kind="tag",
                        status=BootstrapEntryStatus.skipped,
                        message="already exists",
                    )
                )
                report.summary.skipped += 1
            else:
                client.ensure_tag(slug=tag.slug, name=tag.slug.replace("-", " ").title())
                report.entries.append(
                    FieldBootstrapEntry(
                        id=tag.slug,
                        kind="tag",
                        status=BootstrapEntryStatus.created,
                    )
                )
                report.summary.created += 1
        except NetboxWriteError as exc:
            report.entries.append(
                FieldBootstrapEntry(
                    id=tag.slug,
                    kind="tag",
                    status=BootstrapEntryStatus.failed,
                    message=str(exc),
                )
            )
            report.summary.failed += 1

    return report
