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
    reload_p = catalog_sub.add_parser("reload", help="Reload normalization rules from YAML into DB")
    reload_p.add_argument(
        "--root",
        default=None,
        help="Override catalog root (default: GARD_CATALOG_ROOT or gard-catalog)",
    )

    issue = sub.add_parser("issue-token", help="Mint a service API token")
    issue.add_argument("--subject", required=True)
    issue.add_argument(
        "--role",
        required=True,
        choices=["viewer", "lifecycle_manager", "mcp_client", "system_admin"],
    )
    issue.add_argument("--ttl-seconds", type=int, default=None)

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
            from gard.core.settings import get_settings
            from gard.db.session import session_scope

            root = Path(args.root) if args.root else get_settings().catalog_root
            with session_scope() as session:
                report = load_catalog(session, root)
            sys.stdout.write(
                f"loaded={report.loaded} skipped={report.skipped} errors={len(report.errors)}\n"
            )
            for e in report.errors:
                sys.stderr.write(f"!! {e}\n")
            return 0 if not report.errors else 1
        return 2

    if args.cmd == "issue-token":
        from gard.core.tokens import issue_token_cli

        return issue_token_cli(args.subject, args.role, args.ttl_seconds)

    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
