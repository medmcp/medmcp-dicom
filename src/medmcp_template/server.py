"""MCP server entrypoint for medmcp-template.

Replace this module's tool registrations with your domain tools after
scaffolding a new repo from the template. See README.md for the full workflow.
"""

from mcp.server.fastmcp import FastMCP

from medmcp_template.tools.example import add_numbers

mcp = FastMCP("medmcp-template")

# Register tools here — one add_tool call per domain tool.
mcp.add_tool(add_numbers)


def server_config() -> dict[str, str]:
    """Return MCP server metadata for autodiscovery by the local agent."""
    return {"name": "medmcp-template", "command": "medmcp-template"}


def main() -> None:
    """Launch the MCP server over stdio (JSON-RPC)."""
    mcp.run(transport="stdio")
