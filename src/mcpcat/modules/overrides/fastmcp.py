from typing import Any, TYPE_CHECKING

from mcp import ServerResult, Tool
from mcp.types import CallToolRequest, CallToolResult, ListToolsRequest, TextContent

from mcpcat.modules.overrides.mcp_server import override_lowlevel_mcp_server
from mcpcat.modules.tools import handle_report_missing

from ...types import MCPCatData
from ..version_detection import has_fastmcp_support

"""Tool management and interception for MCPCat."""

if TYPE_CHECKING or has_fastmcp_support():
    try:
        from mcp.server import FastMCP
    except ImportError:
        FastMCP = None
else:
    FastMCP = None


def override_fastmcp(server: Any, data: MCPCatData) -> None:
    """Set up tool list and call handlers for FastMCP."""
    if FastMCP is None:
        raise ImportError("FastMCP is not available in this MCP version")
    from mcp.types import CallToolResult, ListToolsResult
    override_lowlevel_mcp_server(server._mcp_server, data)
