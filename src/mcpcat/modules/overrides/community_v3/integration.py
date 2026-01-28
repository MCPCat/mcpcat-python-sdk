"""Integration module for Community FastMCP v3.

This module provides the function to apply MCPCat tracking to
FastMCP v3 servers using the middleware system.
"""

from __future__ import annotations

from typing import Any

from mcpcat.modules.logging import write_to_log
from mcpcat.modules.overrides.community_v3.middleware import MCPCatMiddleware
from mcpcat.types import MCPCatData


def apply_community_v3_integration(server: Any, mcpcat_data: MCPCatData) -> None:
    """Apply MCPCat tracking to a Community FastMCP v3 server.

    This function:
    1. Creates an MCPCatMiddleware instance
    2. Inserts it at the beginning of the middleware chain (position 0)
    3. Registers get_more_tools tool if enabled

    Args:
        server: A Community FastMCP v3 server instance.
        mcpcat_data: MCPCat tracking configuration.
    """
    try:
        # Create middleware instance
        middleware = MCPCatMiddleware(mcpcat_data, server)

        # Insert at beginning of middleware chain (position 0)
        # This ensures MCPCat sees all requests first
        server.middleware.insert(0, middleware)
        write_to_log(
            f"Inserted MCPCatMiddleware at position 0 for server {id(server)}"
        )

        # Register get_more_tools if enabled
        if mcpcat_data.options.enable_report_missing:
            _register_get_more_tools_v3(server, mcpcat_data)

        write_to_log(
            f"Successfully applied Community FastMCP v3 integration "
            f"for server {id(server)}"
        )

    except Exception as e:
        write_to_log(f"Error applying Community FastMCP v3 integration: {e}")
        raise


def _register_get_more_tools_v3(server: Any, mcpcat_data: MCPCatData) -> None:
    """Register the get_more_tools tool for FastMCP v3.

    Args:
        server: A Community FastMCP v3 server instance.
        mcpcat_data: MCPCat tracking configuration.
    """
    from mcpcat.modules.tools import handle_report_missing

    # Define the get_more_tools function
    async def get_more_tools(context: str | None = None) -> str:
        """Check for additional tools when your task might benefit from them.

        Args:
            context: A description of your goal and what kind of tool would help.

        Returns:
            A response message indicating the result.
        """
        # Handle None values
        context_str = context if context is not None else ""

        result = await handle_report_missing({"context": context_str})

        # Return text content for FastMCP v3
        # The result.content is a list of TextContent objects
        if result.content and len(result.content) > 0:
            content_item = result.content[0]
            if hasattr(content_item, "text"):
                return content_item.text

        return "No additional tools available."

    try:
        # Note: We don't check if get_more_tools already exists because
        # FastMCP v3's list_tools is async and we're in a sync context.
        # The tool decorator handles duplicates gracefully.

        get_more_tools_desc = (
            "Check for additional tools whenever your task might benefit from "
            "specialized capabilities - even if existing tools could work as a "
            "fallback."
        )

        # Register the tool using the server's tool decorator or add_tool method
        if hasattr(server, "tool"):
            server.tool(
                name="get_more_tools",
                description=get_more_tools_desc,
            )(get_more_tools)
            write_to_log("Registered get_more_tools using server.tool() decorator")
        elif hasattr(server, "add_tool"):
            from fastmcp.tools.tool import Tool

            tool = Tool.from_function(
                get_more_tools,
                name="get_more_tools",
                description=get_more_tools_desc,
            )
            server.add_tool(tool)
            write_to_log("Registered get_more_tools using server.add_tool()")
        else:
            write_to_log("Warning: Could not find method to register get_more_tools")

    except Exception as e:
        write_to_log(f"Error registering get_more_tools: {e}")
