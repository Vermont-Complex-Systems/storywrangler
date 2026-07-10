# Agents & MCP

Storywrangler is built to be driven by LLM agents, not just humans. Everything on
this site is also available as plain text and as live tools, so an agent — Claude
Code, or any [Model Context Protocol](https://modelcontextprotocol.io) client —
can read the docs, discover what is registered, and validate a submission without
scraping HTML or guessing.

There are three ways in: the `llms.txt` exports (the docs as plain text), the MCP
server (live tools over the registry and docs), and the Claude skills (durable
workflow craft).

## Machine-readable docs

Every page here has a plain-text twin, generated from the same source:

- `/llms.txt` — the entire documentation as one markdown file.
- `/sections.json` — every section with its discovery keywords.
- `/{slug}/llms.txt` — a single guide (e.g. [`/querying/llms.txt`](/querying/llms.txt)).
- `/api-reference/{tag}/llms.txt` — the endpoint reference for one tag, rendered
  live from the API's OpenAPI spec.

Point an agent at [`/llms.txt`](/llms.txt) and it has the whole platform in context.

## MCP server

`storywrangler-mcp` exposes the registry and the docs as MCP tools — the same
tools over two transports.

**Local (stdio)** — recommended for Claude Code. Drop this into your `.mcp.json`:

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

`uvx` fetches and runs it — no install step. It points at the public deployment by
default; override with `STORYWRANGLER_URL` and `STORYWRANGLER_DOCS_URL`, and set
`STORYWRANGLER_INSECURE=1` while the uvm.edu TLS certificate mismatch persists.

**Remote (streamable HTTP)** — the same server is mounted on the API at `/mcp`
(stateless), for hosted agents that connect over HTTP instead of spawning a
process.

### Tools

| Tool | What it does |
| --- | --- |
| `list-sections` | List the documentation sections (title + discovery keywords). |
| `get-documentation` | Fetch one section as markdown. |
| `list-datasets` | List registered datasets from the live registry. |
| `get-dataset` | One dataset's `level_order`, `filter_values`, and `availability` — the ground truth for building a valid query. |
| `validate-submission` | Dry-run a `DatasetCreate` locally against the real schema and the registration guards, before you POST. |

Because the registry tools return introspected metadata, an agent builds queries
from what actually exists — no guessed entity IDs, granularities, or date ranges.

## Skills

Two Claude skills carry the *when and why* — the discovery-first analyst craft
([querying](/querying)) and the submission craft ([registering](/register)) — while
the exact field and endpoint reference stays in the docs and MCP tools, so nothing
drifts. Here they are in full; copy either into your agent, or let
`storywrangler new` scaffold both:

<!-- SkillViewer -->

## Wire it into your project

`storywrangler new` scaffolds the agent setup into a fresh dataset project — it
writes `.mcp.json` and `.claude/skills/` automatically, so a Claude Code session
in that project has the MCP tools and skills out of the box.

Prefer a plugin? Install from the in-repo marketplace:

```
/plugin marketplace add Vermont-Complex-Systems/storywrangler
```
