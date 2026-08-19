# MCP servers: NetBox + Netmiko

Two MCP servers giving an AI read-only access to NetBox as inventory, and read-only `show` command access to live network devices over Netmiko.

Write-up: [Phase 3: Giving an AI Read-Only Access to the Fabric via MCP](https://anproit.com/labs/network-automation-phase3)

## What's here

- `netbox_mcp_server.py` - generated from NetBox's own OpenAPI schema via `FastMCP.from_openapi()`. Exposes NetBox's REST API as MCP tools, with every `DELETE` route excluded at the route-mapping level. Starting point adapted from [PacketCoders' FastMCP + NetBox walkthrough](https://www.packetcoders.io/how-to-dynamically-create-mcp-servers-with-fastmcp-2/).
- `netmiko_mcp_server.py` - hand-written. Looks devices up in NetBox, then runs a validated `show` command over SSH via Netmiko. Includes a safety filter (`is_safe_show_command`) that blocks config/write commands and commands that could leak secrets (`show running-config`, `show tech`, etc.) - including their IOS abbreviations, not just the literal full command text.

## Setup

```bash
uv init
uv add netmiko "mcp[cli]" python-dotenv rich fastmcp httpx pynetbox
cp .env.example .env
# fill in NETBOX_URL, NETBOX_TOKEN, USERNAME, PASSWORD
```

`NETBOX_TOKEN` should belong to a dedicated, non-superuser service account scoped to `view` on `dcim.device` only - see the write-up for why that matters even for a "read-only" integration.

## Running

```bash
uv run netbox_mcp_server.py
uv run netmiko_mcp_server.py
```

Or test either one standalone first with [MCP Inspector](https://github.com/modelcontextprotocol/inspector), no LLM required:

```bash
npx @modelcontextprotocol/inspector uv run netbox_mcp_server.py
```

## Note on scope

`netmiko_mcp_server.py`'s device inventory is currently filtered to a specific lab subnet (`172.20.20.0/24` - see `get_netbox_device()`). Adjust that filter for your own environment.
