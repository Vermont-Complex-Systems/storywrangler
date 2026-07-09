# storywrangler Claude plugin

Skills + MCP server for working with the Storywrangler data platform.

Install from the in-repo marketplace:

```
/plugin marketplace add Vermont-Complex-Systems/storywrangler
/plugin install storywrangler@storywrangler
```

Contents:

- `skills/storywrangler-analyst` — discovery-first querying craft
- `skills/storywrangler-submitter` — dataset registration craft
- `.mcp.json` — the `storywrangler-mcp` server (stdio via uvx; switch to the
  remote `https://storywrangler.uvm.edu/mcp/` endpoint once the TLS
  certificate is fixed)

`skills/` is generated — the canonical skills live in `.claude/skills/` at the
repo root; run `scripts/sync_agent_assets.py` after editing them.
