"""CLI: bootstrap NetBox device types from curated community manifest (F9)."""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from gard.core.settings import Settings, get_settings
from gard.integrations.netbox.devicetype_importer import BootstrapReport, run_bootstrap
from gard.integrations.netbox.devicetype_manifest import (
    DeviceTypeManifestError,
    load_manifest,
    resolve_dry_run,
)
from gard.integrations.netbox.write_client import (
    NetboxWriteClient,
    NetboxWriteError,
    NetboxWriteNotConfigured,
)


def _is_local_netbox(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1")


def _resolve_netbox_url(settings: Settings) -> str:
    if settings.netbox_url is None:
        raise NetboxWriteNotConfigured("GARD_NETBOX_URL is not set")
    return str(settings.netbox_url).rstrip("/")


def _resolve_token(*, write_token: str | None, settings: Settings) -> str:
    token = write_token or settings.netbox_token
    if not token:
        raise NetboxWriteNotConfigured("NetBox token required (GARD_NETBOX_TOKEN or --write-token)")
    return token


def _requires_confirm(settings: Settings, netbox_url: str) -> bool:
    return settings.env == "prod" or not _is_local_netbox(netbox_url)


def _report_to_dict(
    report: BootstrapReport, *, started_at: datetime, completed_at: datetime
) -> dict[str, Any]:
    return {
        "upstream_pin": report.upstream_pin,
        "netbox_url": report.netbox_url,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "entries": [
            {
                "id": e.id,
                "status": e.status.value,
                "netbox_device_type_id": e.netbox_device_type_id,
                "message": e.message,
            }
            for e in report.entries
        ],
        "summary": {
            "created": report.summary.created,
            "updated": report.summary.updated,
            "skipped": report.summary.skipped,
            "conflict": report.summary.conflict,
            "failed": report.summary.failed,
        },
    }


def _print_report(report: BootstrapReport, *, started_at: datetime, completed_at: datetime) -> None:
    payload = _report_to_dict(report, started_at=started_at, completed_at=completed_at)
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")


def bootstrap_device_types_cli(
    argv: Sequence[str] | None = None,
    *,
    settings: Settings | None = None,
) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Import curated community device types into NetBox (F9 bootstrap)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate manifest and resolve library paths without NetBox writes",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required for non-localhost NetBox or GARD_ENV=prod",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Add missing components when device type slug already exists",
    )
    parser.add_argument(
        "--write-token",
        default=None,
        help="NetBox write token (default: GARD_NETBOX_TOKEN)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    cfg = settings or get_settings()
    started_at = datetime.now(tz=UTC)

    try:
        manifest = load_manifest()
    except DeviceTypeManifestError as exc:
        sys.stderr.write(f"manifest error: {exc}\n")
        return 1

    if args.dry_run:
        resolved = resolve_dry_run(manifest)
        sys.stdout.write(
            json.dumps(
                {
                    "dry_run": True,
                    "upstream_pin": manifest.upstream_pin,
                    "entry_count": len(resolved),
                    "entries": resolved,
                },
                indent=2,
            )
            + "\n"
        )
        return 0

    try:
        netbox_url = _resolve_netbox_url(cfg)
        token = _resolve_token(write_token=args.write_token, settings=cfg)
    except NetboxWriteNotConfigured as exc:
        sys.stderr.write(f"{exc}\n")
        return 1

    if _requires_confirm(cfg, netbox_url) and not args.confirm:
        sys.stderr.write(
            "refusing bootstrap: non-local NetBox or GARD_ENV=prod requires --confirm\n"
        )
        return 2

    client = NetboxWriteClient(
        base_url=netbox_url,
        token=token,
        verify_tls=cfg.netbox_verify_tls,
        timeout_seconds=cfg.netbox_timeout_seconds,
    )

    try:
        report = run_bootstrap(client, manifest, netbox_url=netbox_url, force=args.force)
    except NetboxWriteError as exc:
        sys.stderr.write(f"netbox write error: {exc}\n")
        return 1

    completed_at = datetime.now(tz=UTC)
    _print_report(report, started_at=started_at, completed_at=completed_at)

    if report.summary.failed or report.summary.conflict:
        return 1
    return 0
