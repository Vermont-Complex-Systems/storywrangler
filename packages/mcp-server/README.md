# storywrangler-mcp

MCP server that lets AI agents work with the Storywrangler platform. Modeled on
the Svelte team's `@sveltejs/mcp` and vcsi-starter's `@the-vcsi/scrolly-mcp`:
the server holds no content — it fetches documentation from the docs site's
`llms.txt` exports and dataset metadata from the live registry API, so nothing
can drift.

## Tools

| Tool | Source | Purpose |
| --- | --- | --- |
| `list-sections` | docs site `/sections.json` | Discover documentation sections (guides + per-tag API reference) |
| `get-documentation` | docs site `/{slug}/llms.txt` | Fetch section markdown, with fuzzy matching |
| `list-datasets` | API `/registry/` | List registered datasets with queryable dimensions |
| `get-dataset` | API `/registry/{domain}/{dataset_id}` | Ground-truth metadata: level_order, filter_values, availability |
| `validate-submission` | local (storywrangler-schemas) | Dry-run a DatasetCreate payload: real Pydantic contract, mirrored server guards, conflation lints, on-disk hive layout checks when reachable |

## Usage

**Remote (streamable HTTP)** — the backend mounts this same server at `/mcp`
(see `backend/app/main.py`). No install needed:

```json
{
  "mcpServers": {
    "storywrangler": {
      "type": "http",
      "url": "https://storywrangler.uvm.edu/mcp/"
    }
  }
}
```

Keep the trailing slash — `/mcp` works but costs a 307 redirect per request.
On the server, set `STORYWRANGLER_DOCS_URL`/`STORYWRANGLER_URL` to localhost
addresses so tool fetches don't loop through the public proxy. Note: remote
clients validate TLS strictly; this endpoint is unusable externally until the
uvm.edu certificate mismatch is fixed.

**Local (stdio)** — works offline and pins a version:

```json
{
  "mcpServers": {
    "storywrangler": {
      "command": "uvx",
      "args": ["storywrangler-mcp"]
    }
  }
}
```

## CLI mode

Every tool also works as a shell command — the fallback for subagents and CI
where no MCP connection exists:

```bash
uvx storywrangler-mcp list-sections
uvx storywrangler-mcp get-documentation register querying
uvx storywrangler-mcp list-datasets
uvx storywrangler-mcp get-dataset wikimedia ngrams --full
uvx storywrangler-mcp validate-submission payload.json   # '-' reads stdin
```

`validate-submission` exits non-zero on blocking errors, so a pipeline can
gate its submit step on it (add `--no-disk` to skip layout checks).

## Configuration

| Env var | Default | Meaning |
| --- | --- | --- |
| `STORYWRANGLER_DOCS_URL` | `https://storywrangler.uvm.edu` | Docs site base URL |
| `STORYWRANGLER_URL` | `https://storywrangler.uvm.edu` | API base URL (same var the SDK uses) |
| `STORYWRANGLER_INSECURE` | unset | Set to `1` to skip TLS verification (the uvm.edu deployment currently serves a mismatched certificate — fix pending) |

Point both at `http://localhost:5173` / `http://localhost:8000` for local development.
