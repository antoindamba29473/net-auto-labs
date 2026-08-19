
"""
MCP has gained a huge amount of popularity. And for good reason, it's easy to use and can allow you to really harness the benefits of LLMs. So here's a quick MCP tip!

Dynamically create MCP servers with FastMCP by passing a REST API's OpenAPI schema to the from_openapi function.

The example below builds a NetBox MCP with full read/write access, DELETE endpoint exclusion, and schema caching:
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx", "python-dotenv", "fastmcp"]
# ///

import os
import json
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.providers.openapi import RouteMap, MCPType

load_dotenv()

NETBOX_URL = os.environ["NETBOX_URL"]
NETBOX_TOKEN = os.environ["NETBOX_TOKEN"]
SCHEMA_CACHE = Path(__file__).parent / "netbox_schema.json"

auth_headers = {"Authorization": f"Token {NETBOX_TOKEN}"}

# Authenticated client for the NetBox API
client = httpx.AsyncClient(
    base_url=f"{NETBOX_URL}",
    headers=auth_headers,
    timeout=120,
)

# Load the OpenAPI schema from the cache file if it exists
if SCHEMA_CACHE.exists():
    openapi_spec = json.loads(SCHEMA_CACHE.read_text())
else:
    # Fetch the OpenAPI schema from NetBox and cache it
    response = httpx.get(
        f"{NETBOX_URL}/api/schema/?format=json",
        headers=auth_headers,
        timeout=120,
    )
    response.raise_for_status()
    openapi_spec = response.json()
    SCHEMA_CACHE.write_text(json.dumps(openapi_spec))


# Build the MCP server, excluding every DELETE endpoint
mcp = FastMCP.from_openapi(
    openapi_spec=openapi_spec,
    client=client,
    name="NetBox MCP",
    route_maps=[
        RouteMap(methods=["DELETE"], mcp_type=MCPType.EXCLUDE),
    ],
    validate_output=False,
)

if __name__ == "__main__":
    mcp.run()