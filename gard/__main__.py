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
    if args.cmd == "issue-token":
        from gard.core.tokens import issue_token_cli

        return issue_token_cli(args.subject, args.role, args.ttl_seconds)

    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
