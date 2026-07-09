"""Dual-mode entry point: MCP stdio server by default, CLI with subcommands.

The CLI exposes the same tools for environments without an MCP connection —
subagents, CI pipelines, plain shells:

    storywrangler-mcp                                  # stdio MCP server
    storywrangler-mcp list-sections
    storywrangler-mcp get-documentation register querying
    storywrangler-mcp list-datasets
    storywrangler-mcp get-dataset wikimedia ngrams --full
    storywrangler-mcp validate-submission payload.json # or '-' for stdin
    storywrangler-mcp validate-submission payload.json --no-disk

`validate-submission` exits non-zero when the payload has blocking errors,
so it can gate a pipeline's submit step in CI.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .validate import format_report, validate_submission


def _run_server() -> None:
    from .server import mcp

    mcp.run()


def _cmd_validate(args: argparse.Namespace) -> int:
    raw = sys.stdin.read() if args.payload == "-" else open(args.payload).read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Payload is not valid JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print("Payload must be a JSON object (the DatasetCreate dict).", file=sys.stderr)
        return 2
    report = validate_submission(payload, check_disk=not args.no_disk)
    print(format_report(report))
    return 0 if report["valid"] else 1


def _cmd_list_sections(_args: argparse.Namespace) -> int:
    from . import server

    print(asyncio.run(server.list_sections()))
    return 0


def _cmd_get_documentation(args: argparse.Namespace) -> int:
    from . import server

    print(asyncio.run(server.get_documentation(args.sections)))
    return 0


def _cmd_list_datasets(_args: argparse.Namespace) -> int:
    from . import server

    print(asyncio.run(server.list_datasets()))
    return 0


def _cmd_get_dataset(args: argparse.Namespace) -> int:
    from . import server

    print(asyncio.run(server.get_dataset(args.domain, args.dataset_id, full=args.full)))
    return 0


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        _run_server()
        return

    parser = argparse.ArgumentParser(
        prog="storywrangler-mcp",
        description="Storywrangler MCP server (no arguments) or CLI (subcommands).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate-submission", help="Dry-run a DatasetCreate payload")
    p.add_argument("payload", help="Path to a JSON payload file, or '-' for stdin")
    p.add_argument("--no-disk", action="store_true", help="Skip on-disk layout checks")
    p.set_defaults(func=_cmd_validate)

    p = sub.add_parser("list-sections", help="List documentation sections")
    p.set_defaults(func=_cmd_list_sections)

    p = sub.add_parser("get-documentation", help="Fetch documentation section(s)")
    p.add_argument("sections", nargs="+", help="Section path(s) or title(s)")
    p.set_defaults(func=_cmd_get_documentation)

    p = sub.add_parser("list-datasets", help="List registered datasets")
    p.set_defaults(func=_cmd_list_datasets)

    p = sub.add_parser("get-dataset", help="Get one dataset's registry metadata")
    p.add_argument("domain")
    p.add_argument("dataset_id")
    p.add_argument("--full", action="store_true", help="Include partition index")
    p.set_defaults(func=_cmd_get_dataset)

    args = parser.parse_args(argv)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
