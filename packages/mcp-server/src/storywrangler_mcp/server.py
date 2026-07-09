"""Storywrangler MCP server.

Four tools, two live sources:

- Documentation (docs site): list-sections, get-documentation — fetched from
  the docs site's /sections.json and /{slug}/llms.txt exports.
- Dataset registry (API): list-datasets, get-dataset — fetched from the
  Storywrangler API's /registry endpoints, which hold the introspected ground
  truth (level_order, filter_values, availability) for what is queryable.

Configuration (env vars):
- STORYWRANGLER_DOCS_URL — docs site base (default https://storywrangler.uvm.edu)
- STORYWRANGLER_URL — API base (default https://api.storywrangler.uvm.edu, same
  env var the SDK uses)
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP

from .matching import Section, match_section, suggest_sections
from .validate import format_report, validate_submission

DOCS_BASE_URL = os.getenv("STORYWRANGLER_DOCS_URL", "https://storywrangler.uvm.edu").rstrip("/")
API_BASE_URL = os.getenv("STORYWRANGLER_URL", "https://api.storywrangler.uvm.edu").rstrip("/")

# TLS verification is on by default; set STORYWRANGLER_INSECURE=1 for
# deployments with self-signed certificates (mirrors the SDK's behavior).
VERIFY_TLS = os.getenv("STORYWRANGLER_INSECURE", "").lower() not in ("1", "true")

SECTIONS_CACHE_TTL = 300.0  # seconds

mcp = FastMCP("storywrangler")

_sections_cache: tuple[float, list[Section]] | None = None


_CERT_HINT = (
    "TLS certificate verification failed for {url}. As of mid-2026 the "
    "storywrangler.uvm.edu deployment serves a certificate issued for a "
    "different hostname (known infrastructure issue, fix pending). If you "
    "trust the deployment, set STORYWRANGLER_INSECURE=1 to skip verification."
)


async def _get(url: str) -> httpx.Response:
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True, verify=VERIFY_TLS) as client:
            res = await client.get(url)
            res.raise_for_status()
            return res
    except httpx.ConnectError as exc:
        if "certificate" in str(exc).lower():
            raise RuntimeError(_CERT_HINT.format(url=url)) from exc
        raise


async def _fetch_json(url: str) -> Any:
    return (await _get(url)).json()


async def _fetch_text(url: str) -> str:
    return (await _get(url)).text


async def _get_sections() -> list[Section]:
    global _sections_cache
    if _sections_cache and time.monotonic() - _sections_cache[0] < SECTIONS_CACHE_TTL:
        return _sections_cache[1]
    sections = await _fetch_json(f"{DOCS_BASE_URL}/sections.json")
    _sections_cache = (time.monotonic(), sections)
    return sections


@mcp.tool(name="list-sections")
async def list_sections() -> str:
    """List all Storywrangler documentation sections with their use cases.

    Call this first to discover available documentation, then call
    get-documentation with the relevant section paths. Match the user's task
    against each section's use_cases keywords.
    """
    sections = await _get_sections()
    lines = [
        f"- title: {s['title']}, use_cases: {s.get('use_cases', '')}, path: {s['slug']}"
        for s in sections
    ]
    return "Available documentation sections:\n" + "\n".join(lines)


@mcp.tool(name="get-documentation")
async def get_documentation(sections: list[str] | str) -> str:
    """Fetch Storywrangler documentation section(s) as markdown.

    Pass one section path/title or a list of them (from list-sections), e.g.
    "register", "querying", or "api-reference/wikimedia". Fuzzy matching is
    applied when no exact match exists.
    """
    if isinstance(sections, str):
        sections = [sections]
    all_sections = await _get_sections()

    parts: list[str] = []
    for query in sections:
        matched = match_section(query, all_sections)
        if matched is None:
            similar = suggest_sections(query, all_sections)
            hints = "\n".join(f"- {s['title']} (path: {s['slug']})" for s in similar)
            parts.append(f"## Section not found: {query}\n\nSimilar sections:\n{hints}")
            continue
        try:
            content = await _fetch_text(f"{DOCS_BASE_URL}/{matched['slug']}/llms.txt")
            parts.append(content)
        except httpx.HTTPError as exc:
            parts.append(f"## Error fetching '{matched['slug']}': {exc}")
    return "\n\n---\n\n".join(parts)


@mcp.tool(name="list-datasets")
async def list_datasets() -> str:
    """List all datasets registered in the Storywrangler platform.

    Returns each dataset's domain/dataset_id identity, description, storage
    format, and queryable dimensions. Use get-dataset for full metadata
    (filter values, availability) before constructing queries.
    """
    payload = await _fetch_json(f"{API_BASE_URL}/registry/")
    lines = []
    for ds in payload.get("datasets", []):
        dims = ", ".join(
            f"{level['column']} ({level['type']})" for level in (ds.get("level_order") or [])
        )
        lines.append(
            f"- {ds['domain']}/{ds['dataset_id']} [{ds.get('data_format', '?')}]"
            f" — {ds.get('description') or 'no description'}"
            + (f"\n  dimensions: {dims}" if dims else "")
        )
    total = payload.get("total", len(lines))
    return f"{total} registered dataset(s):\n" + "\n".join(lines)


@mcp.tool(name="get-dataset")
async def get_dataset(domain: str, dataset_id: str, full: bool = False, version: Optional[str] = None) -> str:
    """Get registry metadata for one dataset — the ground truth for queries.

    Returns level_order (queryable dimensions with defaults), filter_values
    (valid values per dimension), manifest.availability (date coverage per
    entity), and endpoint_schema (output shape). Always check this before
    constructing a query. Set full=true to include the partition index.
    """
    params = []
    if full:
        params.append("full=true")
    if version:
        params.append(f"version={version}")
    qs = ("?" + "&".join(params)) if params else ""
    payload = await _fetch_json(f"{API_BASE_URL}/registry/{domain}/{dataset_id}{qs}")
    return json.dumps(payload, indent=2, default=str)


@mcp.tool(name="validate-submission")
async def validate_submission_tool(payload: dict | str, check_disk: bool = True) -> str:
    """Dry-run a DatasetCreate registration payload before POSTing it.

    Validates against the real storywrangler-schemas Pydantic contract, mirrors
    the server's registration guards (comparison axes, identifier rules), and
    lints for silently-ignored keys (e.g. query axes placed in endpoint_schema).
    When data_location is reachable from this machine, the hive col=val layout
    is checked directly. Run this after writing or editing a submit.py and fix
    all errors before registering; re-run after fixing.
    """
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            return f"Payload is not valid JSON: {exc}"
    if not isinstance(payload, dict):
        return "Payload must be a JSON object (the DatasetCreate dict passed to register())."

    return format_report(validate_submission(payload, check_disk=check_disk))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
