"""`python -m gard` / `gard` console-script entry point.

Tiny dispatcher: keeps real logic in subcommand modules so this file
stays no-op-importable.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gard", description="GARD service control plane")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("serve", help="Run the FastAPI application (uvicorn)")
    sub.add_parser("mcp", help="Run the MCP Streamable HTTP server")

    catalog = sub.add_parser("catalog", help="Catalog operations")
    catalog_sub = catalog.add_subparsers(dest="catalog_cmd", required=True)
    reload_p = catalog_sub.add_parser(
        "reload",
        help="Reload normalization AND firmware catalogs from YAML into DB",
    )
    reload_p.add_argument(
        "--root",
        default=None,
        help="Override normalization catalog root (default: GARD_CATALOG_ROOT)",
    )
    reload_p.add_argument(
        "--firmware-root",
        default=None,
        help="Override firmware catalog root (default: GARD_FIRMWARE_CATALOG_ROOT)",
    )
    reload_p.add_argument(
        "--only",
        choices=["normalization", "firmware", "both"],
        default="both",
        help="Limit which catalog(s) to reload (default: both)",
    )

    issue = sub.add_parser("issue-token", help="Mint a service API token")
    issue.add_argument("--subject", required=True)
    issue.add_argument(
        "--role",
        required=True,
        choices=[
            "viewer",
            "lifecycle_manager",
            "change_approver",
            "mcp_client",
            "system_admin",
        ],
    )
    issue.add_argument("--ttl-seconds", type=int, default=None)

    netbox = sub.add_parser("netbox", help="NetBox integration utilities")
    netbox_sub = netbox.add_subparsers(dest="netbox_cmd", required=True)
    bootstrap_p = netbox_sub.add_parser(
        "bootstrap-device-types",
        help="Import curated community device types into NetBox (F9)",
    )
    bootstrap_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate manifest without NetBox writes",
    )
    bootstrap_p.add_argument(
        "--confirm",
        action="store_true",
        help="Required for non-localhost NetBox or GARD_ENV=prod",
    )
    bootstrap_p.add_argument(
        "--force",
        action="store_true",
        help="Add missing components when slug already exists",
    )
    bootstrap_p.add_argument(
        "--write-token",
        default=None,
        help="NetBox write token override",
    )
    wb_bootstrap_p = netbox_sub.add_parser(
        "bootstrap-writeback-fields",
        help="Bootstrap NetBox custom fields and tags for F10 write-back",
    )
    wb_bootstrap_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate manifest without NetBox writes",
    )
    wb_bootstrap_p.add_argument(
        "--confirm",
        action="store_true",
        help="Required for non-localhost NetBox or GARD_ENV=prod",
    )
    wb_bootstrap_p.add_argument(
        "--write-token",
        default=None,
        help="NetBox write token override",
    )

    args = parser.parse_args(argv)

    if args.cmd == "serve":
        from gard.api.app import run_uvicorn

        return run_uvicorn()
    if args.cmd == "mcp":
        from gard.mcp.server import run_mcp

        return run_mcp()
    if args.cmd == "catalog":
        if args.catalog_cmd == "reload":
            from pathlib import Path

            from gard.catalog.normalization_loader import load_catalog
            from gard.core.firmware_catalog_controller import reload as fw_reload
            from gard.core.settings import get_settings
            from gard.db.session import append_only_scope, session_scope

            settings = get_settings()
            norm_root = Path(args.root) if args.root else settings.catalog_root
            fw_root = (
                Path(args.firmware_root) if args.firmware_root else settings.firmware_catalog_root
            )
            only = args.only

            rc = 0
            if only in ("normalization", "both"):
                with session_scope() as session:
                    report = load_catalog(session, norm_root)
                sys.stdout.write(
                    f"normalization: loaded={report.loaded} "
                    f"skipped={report.skipped} errors={len(report.errors)}\n"
                )
                for e in report.errors:
                    sys.stderr.write(f"!! norm: {e}\n")
                if report.errors:
                    rc = 1

            if only in ("firmware", "both"):
                with session_scope() as session, append_only_scope() as audit:
                    outcome = fw_reload(
                        session=session,
                        audit_session=audit,
                        catalog_root=fw_root,
                    )
                    if not outcome.success:
                        session.rollback()
                        sys.stderr.write(
                            f"!! firmware: reload failed: "
                            f"{outcome.error.file_relpath if outcome.error else '?'}: "
                            f"{outcome.error.reason if outcome.error else '?'}\n"
                        )
                        return 1
                    rep = outcome.report
                    if rep is None:
                        sys.stderr.write(
                            "!! firmware: success outcome had no report (unreachable)\n"
                        )
                        return 1
                    sys.stdout.write(
                        f"firmware: loaded={rep.loaded} removed={rep.removed} "
                        f"unchanged={rep.unchanged} files={len(rep.file_relpaths_seen)} "
                        f"dirty={outcome.dirty}\n"
                    )

            return rc
        return 2

    if args.cmd == "issue-token":
        from gard.core.tokens import issue_token_cli

        return issue_token_cli(args.subject, args.role, args.ttl_seconds)

    if args.cmd == "netbox":
        if args.netbox_cmd == "bootstrap-device-types":
            from gard.cli.netbox_bootstrap import bootstrap_device_types_cli

            dt_extra: list[str] = []
            if args.dry_run:
                dt_extra.append("--dry-run")
            if args.confirm:
                dt_extra.append("--confirm")
            if args.force:
                dt_extra.append("--force")
            if args.write_token:
                dt_extra.extend(["--write-token", args.write_token])
            return bootstrap_device_types_cli(dt_extra)
        if args.netbox_cmd == "bootstrap-writeback-fields":
            from gard.cli.netbox_writeback_bootstrap import bootstrap_writeback_fields_cli

            wb_extra: list[str] = []
            if args.dry_run:
                wb_extra.append("--dry-run")
            if args.confirm:
                wb_extra.append("--confirm")
            if args.write_token:
                wb_extra.extend(["--write-token", args.write_token])
            return bootstrap_writeback_fields_cli(wb_extra)
        return 2

    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
