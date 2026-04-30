"""MCP server entrypoint for medmcp-dicom."""

from importlib.resources import files as _pkg_files

from mcp.server.fastmcp import FastMCP

from medmcp_dicom.tools.bids import build_bids_dataset
from medmcp_dicom.tools.convert import convert_dcm_to_nifti
from medmcp_dicom.tools.explore_bids import explore_bids
from medmcp_dicom.tools.explore_dicom import explore_dicom
from medmcp_dicom.tools.inspect_nifti import inspect_nifti

mcp = FastMCP("medmcp-dicom")

mcp.add_tool(explore_dicom)
mcp.add_tool(explore_bids)
mcp.add_tool(convert_dcm_to_nifti)
mcp.add_tool(build_bids_dataset)
mcp.add_tool(inspect_nifti)


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
