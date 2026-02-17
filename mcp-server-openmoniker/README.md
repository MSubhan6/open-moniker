# MCP Server for Open Moniker

An [MCP](https://modelcontextprotocol.io/) server that exposes the Open Moniker data catalog to AI coding assistants. Browse the catalog, resolve monikers, inspect ownership, search for data assets, and submit governance requests — all from your editor.

## Quick Start

```bash
cd mcp-server-openmoniker
pip install -e .
python server.py          # starts on localhost:8051
```

The server prints **two auth tokens** on startup — one for submitting requests, one for approving them. Reads are anonymous.

## Adding to Claude Code

**HTTP transport (recommended — server must already be running):**

```bash
claude mcp add --transport http --scope user open-moniker http://localhost:8051/mcp
```

**stdio transport (Claude Code launches the server for you):**

```bash
claude mcp add --transport stdio --scope user open-moniker \
  -- python /path/to/open-moniker/mcp-server-openmoniker/server.py --transport stdio
```

Use `--scope project` instead of `--scope user` to store the config in `.mcp.json` (shared with the team) rather than your personal settings.

Verify it's registered:

```bash
claude mcp list
```

Remove it later with:

```bash
claude mcp remove open-moniker
```

## Adding to OpenCode

OpenCode uses a config file. Add to `.opencode.json` (project root or `~/.opencode.json`):

```json
{
  "mcpServers": {
    "open-moniker": {
      "type": "stdio",
      "command": "python",
      "args": ["/path/to/open-moniker/mcp-server-openmoniker/server.py", "--transport", "stdio"]
    }
  }
}
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MCP_PORT` | `8051` | Server port |
| `MCP_HOST` | `0.0.0.0` | Bind address |
| `MCP_SUBMIT_TOKEN` | *(auto-generated)* | Token for `submit_request`, `list_requests` |
| `MCP_APPROVE_TOKEN` | *(auto-generated)* | Token for `approve_request`, `reject_request`, `update_node_status` |
| `MCP_WRITE_TOKEN` | — | Legacy fallback — grants both if split tokens are unset |
| `CATALOG_YAML` | `../sample_catalog.yaml` | Path to catalog definition |
| `DOMAINS_YAML` | `../sample_domains.yaml` | Path to domains definition |
| `MODELS_YAML` | `../sample_models.yaml` | Path to models definition |

**Separation of duties**: Give the submit token to automation bots that propose new monikers. Give the approve token only to governance reviewers. The two tokens should be different.

To pass env vars in Claude Code:

```bash
# Automation bot — can submit but NOT approve
claude mcp add --transport stdio --scope user \
  --env MCP_SUBMIT_TOKEN=bot-submit-token-here \
  open-moniker-submit \
  -- python /path/to/open-moniker/mcp-server-openmoniker/server.py --transport stdio

# Governance reviewer — can approve/reject
claude mcp add --transport stdio --scope user \
  --env MCP_APPROVE_TOKEN=reviewer-approve-token-here \
  open-moniker-approve \
  -- python /path/to/open-moniker/mcp-server-openmoniker/server.py --transport stdio
```

## Available Tools

### Read (no auth)

| Tool | Description |
|---|---|
| `resolve_moniker` | Resolve a moniker to source connection info (type, query, params) |
| `list_children` | List direct children of a catalog path |
| `describe_moniker` | Full metadata: ownership, schema, data quality, docs |
| `search_catalog` | Full-text search across paths, names, descriptions, tags |
| `get_lineage` | Ownership lineage — where each role is defined |
| `get_catalog_tree` | Browse the catalog as a nested tree |
| `get_catalog_stats` | Summary counts by status and source type |
| `get_domains` | List all data domains |
| `get_models` | List all business models/measures |
| `get_model_detail` | Details for a specific model (formula, ownership, appearances) |

### Submit (require `MCP_SUBMIT_TOKEN`)

| Tool | Description |
|---|---|
| `submit_request` | Submit a moniker creation request for governance review |
| `list_requests` | List requests, optionally filtered by status |

### Approve (require `MCP_APPROVE_TOKEN`)

| Tool | Description |
|---|---|
| `approve_request` | Approve a pending request and activate the moniker |
| `reject_request` | Reject a pending request |
| `update_node_status` | Change a node's lifecycle status |

### Prompts

| Prompt | Description |
|---|---|
| `explore_domain` | Walk through a domain's monikers, ownership, and sources |
| `find_data` | Find data assets by keyword |
| `check_ownership` | Investigate ownership for a moniker or domain |

## Example Queries

Once connected, ask your AI assistant things like:

- *"What data domains are available?"*
- *"Search the catalog for treasury data"*
- *"Who owns risk.cvar?"*
- *"Resolve the moniker for prices.equity/AAPL"*
- *"Show me the schema for fixed_income/govies/treasury"*
- *"Submit a request for a new moniker under prices"*
