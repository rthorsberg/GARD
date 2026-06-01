"""CLI: bootstrap NetBox custom fields and tags for F10 write-back."""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from gard.core.settings import Settings, get_settings
from gard.integrations.netbox.field_bootstrap import FieldBootstrapReport, run_field_bootstrap
from gard.integrations.netbox.write_client import (
    NetboxWriteClient,
    NetboxWriteError,
    NetboxWriteNotConfigured,
)
from gard.integrations.netbox.writeback_manifest import (
    WritebackManifestError,
    load_writeback_manifest,
    validate_manifest_dry_run,
)


def _is_local_netbox(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1")


def _resolve_netbox_url(settings: Settings) -> str:
    if settings.netbox_url is None:
        raise NetboxWriteNotConfigured("GARD_NETBOX_URL is not set")
    return str(settings.netbox_url).rstrip("/")


def _resolve_write_token(*, write_token: str | None, settings: Settings) -> str:
    token = write_token or settings.resolved_netbox_write_token()
    if not token:
        raise NetboxWriteNotConfigured(
            "NetBox write token required (GARD_NETBOX_WRITE_TOKEN or GARD_NETBOX_TOKEN in dev)"
        )
    return token


def _requires_confirm(settings: Settings, netbox_url: str) -> bool:
    if settings.env == "prod":
        return True
    return not _is_local_netbox(netbox_url)


def _report_to_dict(
    report: FieldBootstrapReport, *, started_at: datetime, completed_at: datetime
) -> dict[str, Any]:
    return {
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "entries": [
            {
                "id": e.id,
                "kind": e.kind,
                "status": e.status.value,
                "message": e.message,
            }
            for e in report.entries
        ],
        "summary": {
            "created": report.summary.created,
            "skipped": report.summary.skipped,
            "failed": report.summary.failed,
        },
    }


def bootstrap_writeback_fields_cli(
    argv: Sequence[str] | None = None,
    *,
    settings: Settings | None = None,
) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Bootstrap NetBox custom fields and tags for F10 write-back",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate manifest without NetBox writes",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required for non-localhost NetBox or GARD_ENV=prod",
    )
    parser.add_argument(
        "--write-token",
        default=None,
        help="NetBox write token (default: GARD_NETBOX_WRITE_TOKEN)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    cfg = settings or get_settings()
    started_at = datetime.now(tz=UTC)

    try:
        manifest = load_writeback_manifest()
    except WritebackManifestError as exc:
        sys.stderr.write(f"manifest error: {exc}\n")
        return 1

    if args.dry_run:
        payload = validate_manifest_dry_run(manifest)
        payload["dry_run"] = True
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return 0

    try:
        netbox_url = _resolve_netbox_url(cfg)
        token = _resolve_write_token(write_token=args.write_token, settings=cfg)
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
        report = run_field_bootstrap(client, manifest)
    except NetboxWriteError as exc:
        sys.stderr.write(f"netbox write error: {exc}\n")
        return 1

    completed_at = datetime.now(tz=UTC)
    sys.stdout.write(
        json.dumps(
            _report_to_dict(report, started_at=started_at, completed_at=completed_at),
            indent=2,
        )
        + "\n"
    )

    if report.summary.failed:
        return 1
    return 0
