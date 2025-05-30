"""Tool management and interception for MCPCat."""

from typing import Any, TYPE_CHECKING
from mcp.types import CallToolResult, TextContent
from mcpcat.modules.version_detection import has_fastmcp_support

from .logging import write_to_log

if TYPE_CHECKING or has_fastmcp_support():
    try:
        from mcp.server import FastMCP
    except ImportError:
        FastMCP = None


async def handle_report_missing(arguments: dict[str, Any]) -> CallToolResult:
    """Handle the report_missing tool."""
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=f"Unfortunately, we have shown you the full tool list. We have noted your feedback and will work to improve the tool list in the future.",
            )
        ]
    )
