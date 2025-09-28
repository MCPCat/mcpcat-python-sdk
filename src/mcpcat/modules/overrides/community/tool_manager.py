from typing import Any

from mcpcat.modules.compatibility import is_community_fastmcp_server
from mcpcat.modules.internal import (
    get_server_tracking_data,
    get_original_method,
    store_original_method,
    is_tool_tracked,
    register_tool,
    mark_tool_tracked,
)
from mcpcat.modules.logging import write_to_log
from mcpcat.modules.tools import handle_report_missing

from fastmcp import FastMCP


def patch_community_fastmcp_tool_manager(server: Any) -> None:
    """Patch the community FastMCP tool manager to add MCPCat tracking.

    This function modifies the tool manager to:
    1. Add context parameter to existing tools
    2. Automatically add context to new tools via add_tool patching
    3. Add get_more_tools if enabled
    """
    # Check that the server is a community FastMCP server
    if not is_community_fastmcp_server(server):
        write_to_log("WARNING: Incompatible community FastMCP server detected. Tracking not properly enabled.")
        return

    # Get tracking data from the low-level server
    data = get_server_tracking_data(server._mcp_server)
    if not data:
        write_to_log("WARNING: Unknown error when tracking community FastMCP. Tracking data for server not initialized.")
        return

    write_to_log(f"Patching community FastMCP tool manager for server {id(server)}")

    # Add get_more_tools if enabled
    if data.options.enable_report_missing:
        try:
            # Create the get_more_tools function that returns the proper format
            async def get_more_tools(context: str | None = "") -> str:
                """Check for additional tools whenever your task might benefit from specialized capabilities."""
                # Handle None values
                if context is None:
                    context = ""
                result = await handle_report_missing({"context": context})
                # Return just the text content for community FastMCP
                if result.content and len(result.content) > 0:
                    return result.content[0].text
                return "No additional tools available"

            # Register it with the server
            server.tool(
                get_more_tools,
                name="get_more_tools",
                description="Check for additional tools whenever your task might benefit from specialized capabilities - even if existing tools could work as a fallback.",
            )
            write_to_log("Added get_more_tools tool to community FastMCP server")
        except Exception as e:
            write_to_log(f"Error adding get_more_tools: {e}")

    # Track existing tools and optionally add context parameter
    if hasattr(server._tool_manager, "_tools"):
        for tool_name, tool in server._tool_manager._tools.items():
            # Track the tool
            if not is_tool_tracked(server._mcp_server, tool_name):
                register_tool(server._mcp_server, tool_name)
                mark_tool_tracked(server._mcp_server, tool_name)
                write_to_log(f"Found existing community FastMCP tool: {tool_name}")

    # Patch existing tools if context injection is enabled
    if data.options.enable_tool_call_context:
        patch_existing_tools(server)
        patch_add_tool_fn(server)


def patch_existing_tools(server: FastMCP) -> None:
    """Modify existing tools to include the context parameter."""
    try:
        tool_manager = server._tool_manager
        if not hasattr(tool_manager, "_tools"):
            write_to_log("No _tools dictionary found on tool manager")
            return

        for tool_name, tool in tool_manager._tools.items():
            # Skip get_more_tools
            if tool_name == "get_more_tools":
                continue

            # Ensure tool has parameters
            if not hasattr(tool, "parameters"):
                tool.parameters = {"type": "object", "properties": {}, "required": []}
            elif not tool.parameters:
                tool.parameters = {"type": "object", "properties": {}, "required": []}

            # Ensure properties exists
            if "properties" not in tool.parameters:
                tool.parameters["properties"] = {}

            # Always overwrite the context property with MCPCat's version
            tool.parameters["properties"]["context"] = {
                "type": "string",
                "description": "Describe why you are calling this tool and how it fits into your overall task"
            }

            # Add to required array
            if "required" not in tool.parameters:
                tool.parameters["required"] = []
            if isinstance(tool.parameters["required"], list):
                if "context" not in tool.parameters["required"]:
                    tool.parameters["required"].append("context")
            else:
                tool.parameters["required"] = ["context"]

            write_to_log(f"Added/updated context parameter for existing tool: {tool_name}")

    except Exception as e:
        write_to_log(f"Error patching existing tools: {e}")


def patch_add_tool_fn(server: FastMCP) -> None:
    """Patch the add_tool method to automatically add context parameter to new tools."""
    try:
        tool_manager = server._tool_manager
        tool_manager_id = id(tool_manager)
        method_key = f"community_{tool_manager_id}_add_tool"

        # Store original method if not already stored
        if get_original_method(method_key) is None:
            store_original_method(method_key, tool_manager.add_tool)
            write_to_log(f"Stored original add_tool for community tool_manager {tool_manager_id}")

        original_add_tool = get_original_method(method_key)
        if not original_add_tool:
            write_to_log("Failed to get original add_tool method")
            return

        def patched_add_tool(tool: Any) -> Any:
            """Patched add_tool that adds context parameter to new tools."""
            try:
                # Call original method first
                result = original_add_tool(tool)

                # Track the tool
                tool_name = tool.key if hasattr(tool, "key") else (tool.name if hasattr(tool, "name") else "unknown")
                if not is_tool_tracked(server._mcp_server, tool_name):
                    register_tool(server._mcp_server, tool_name)
                    mark_tool_tracked(server._mcp_server, tool_name)
                    write_to_log(f"Tracked new community FastMCP tool: {tool_name}")

                # Add context parameter if it's not get_more_tools
                if tool_name != "get_more_tools":
                    # Get tracking data to check if context injection is enabled
                    data = get_server_tracking_data(server._mcp_server)
                    if data and data.options.enable_tool_call_context:
                        # Ensure tool has parameters
                        if not hasattr(tool, "parameters"):
                            tool.parameters = {"type": "object", "properties": {}, "required": []}
                        elif not tool.parameters:
                            tool.parameters = {"type": "object", "properties": {}, "required": []}

                        # Ensure properties exists
                        if "properties" not in tool.parameters:
                            tool.parameters["properties"] = {}

                        # Always overwrite the context property with MCPCat's version
                        tool.parameters["properties"]["context"] = {
                            "type": "string",
                            "description": "Describe why you are calling this tool and how it fits into your overall task"
                        }

                        # Add to required array
                        if "required" not in tool.parameters:
                            tool.parameters["required"] = []
                        if isinstance(tool.parameters["required"], list):
                            if "context" not in tool.parameters["required"]:
                                tool.parameters["required"].append("context")
                        else:
                            tool.parameters["required"] = ["context"]

                        write_to_log(f"Added/updated context parameter for new tool: {tool_name}")

                return result
            except Exception as e:
                write_to_log(f"Error in patched add_tool: {e}")
                # Fall back to original if something goes wrong
                if callable(original_add_tool):
                    return original_add_tool(tool)
                return tool

        # Apply the patch
        tool_manager.add_tool = patched_add_tool
        write_to_log(f"Successfully patched add_tool for community tool_manager {tool_manager_id}")

    except Exception as e:
        write_to_log(f"Error patching add_tool: {e}")
