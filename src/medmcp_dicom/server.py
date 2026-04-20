"""MCP server entrypoint for medmcp-dicom."""

from importlib.resources import files as _pkg_files

from mcp.server.fastmcp import FastMCP

from medmcp_dicom.tools.explore import explore_data

mcp = FastMCP("medmcp-dicom")

mcp.add_tool(explore_data)


def server_config() -> dict[str, object]:
    """Return MCP server metadata for autodiscovery by the local agent."""
    return {
        "name": "medmcp-dicom",
        "command": "medmcp-dicom",
        "tool_timeout_sec": 1800.0,
        "skills_path": str(_pkg_files("medmcp_dicom") / "skills"),
    }


def main() -> None:
    """Launch the MCP server over stdio (JSON-RPC)."""
    mcp.run(transport="stdio")
