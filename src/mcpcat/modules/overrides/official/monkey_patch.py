"""Monkey-patching implementation for dynamic tool tracking.

This module patches MCP server methods to intercept tool registration and execution,
enabling MCPCat to track tools regardless of when they are registered.
"""

import inspect
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, List, Optional

from mcpcat.modules import event_queue
from mcpcat.modules.compatibility import is_official_fastmcp_server, is_mcp_error_response
from mcpcat.modules.internal import (
    get_original_method,
    get_server_tracking_data,
    is_tool_tracked,
    mark_tool_tracked,
    register_tool,
    store_original_method,
)
from mcpcat.modules.logging import write_to_log
from mcpcat.modules.session import (
    get_client_info_from_request_context,
    get_server_session_id,
)
from mcpcat.types import EventType, MCPCatData, UnredactedEvent

from ..mcp_server import safe_request_context


def get_current_mcpcat_data(server: Any, fallback: MCPCatData) -> MCPCatData:
    """Get the current MCPCat data for a server."""
    data = get_server_tracking_data(server)
    return data if data else fallback


def patch_fastmcp_tool_manager(server: Any, mcpcat_data: MCPCatData) -> bool:
    """Monkey-patch FastMCP's ToolManager to intercept tool operations.

    Args:
        server: FastMCP server instance
        mcpcat_data: MCPCat tracking data

    Returns:
        True if patching was successful, False otherwise
    """
    try:
        # Check if this is a FastMCP server (which now includes _tool_manager check)
        if not is_official_fastmcp_server(server):
            return False

        tool_manager = server._tool_manager
        data = get_server_tracking_data(server)
        if not data:
            return False

        # Add the get_more_tools tool if enabled
        if mcpcat_data.options.enable_report_missing:
            # Create the get_more_tools function that returns CallToolResult
            async def get_more_tools(context: str | None = "") -> List[Any]:
                """Check for additional tools whenever your task might benefit from specialized capabilities."""
                from mcpcat.modules.tools import handle_report_missing

                # Handle None values
                if context is None:
                    context = ""
                result = await handle_report_missing({"context": context})
                # Return just the content list for FastMCP
                return result.content

            # Register it with the server
            # Use inspect to determine which parameters are supported
            try:
                if hasattr(server, 'add_tool'):
                    sig = inspect.signature(server.add_tool)
                    kwargs = {
                        "name": "get_more_tools",
                        "description": "Check for additional tools whenever your task might benefit from specialized capabilities - even if existing tools could work as a fallback.",
                    }
                    # Only add icons if the parameter exists
                    if "icons" in sig.parameters:
                        kwargs["icons"] = None
                    server.add_tool(get_more_tools, **kwargs)
                else:
                    # Fallback for older versions
                    server.add_tool(
                        get_more_tools,
                        name="get_more_tools",
                        description="Check for additional tools whenever your task might benefit from specialized capabilities - even if existing tools could work as a fallback.",
                    )
            except Exception as e:
                write_to_log(f"Error registering get_more_tools: {e}")
            write_to_log("Added get_more_tools tool to FastMCP server")

        # First, capture any tools that were already registered
        if hasattr(tool_manager, "_tools"):
            for tool_name, _tool in tool_manager._tools.items():
                if not is_tool_tracked(server, tool_name):
                    register_tool(server, tool_name)
                    mark_tool_tracked(server, tool_name)
                    write_to_log(f"Found existing FastMCP tool: {tool_name}")

        # Store original methods - use tool_manager ID to avoid conflicts
        # We need to store the original unpatched methods once per tool_manager
        tool_manager_id = id(tool_manager)
        method_key_prefix = f"fastmcp_{tool_manager_id}_"

        write_to_log(
            f"Patching FastMCP server {id(server)}, tool_manager {tool_manager_id}"
        )

        # Only store original methods if this tool_manager hasn't been seen before
        if get_original_method(f"{method_key_prefix}add_tool") is None:
            store_original_method(f"{method_key_prefix}add_tool", tool_manager.add_tool)
            store_original_method(
                f"{method_key_prefix}call_tool", tool_manager.call_tool
            )
            store_original_method(
                f"{method_key_prefix}list_tools", tool_manager.list_tools
            )
            write_to_log(f"Stored original methods for tool_manager {tool_manager_id}")

        # Get original methods for this tool_manager
        original_add_tool = get_original_method(f"{method_key_prefix}add_tool")
        original_call_tool = get_original_method(f"{method_key_prefix}call_tool")
        original_list_tools = get_original_method(f"{method_key_prefix}list_tools")

        # Safety check - if original methods don't exist, bail out
        if not original_add_tool or not original_call_tool or not original_list_tools:
            write_to_log(
                f"Original methods not found for tool_manager {tool_manager_id}, skipping patches"
            )
            return False

        # Patch add_tool to track new registrations
        def patched_add_tool(
            fn: Callable[..., Any],
            **kwargs
        ) -> Any:
            """Patched add_tool that tracks tool registration."""
            try:
                # Call original method first to get the actual tool object
                # Use callable check to avoid mypy error
                if not callable(original_add_tool):
                    write_to_log("Warning: original_add_tool is not callable")
                    return fn

                # Get the signature of the original method to filter kwargs
                try:
                    sig = inspect.signature(original_add_tool)
                    # Filter kwargs to only include parameters that exist in the original signature
                    filtered_kwargs = {
                        k: v for k, v in kwargs.items()
                        if k in sig.parameters
                    }
                except Exception as e:
                    write_to_log(f"Could not inspect signature, passing all kwargs: {e}")
                    filtered_kwargs = kwargs

                result = original_add_tool(fn, **filtered_kwargs)

                # Track the tool registration (wrapped in try-catch to never fail)
                try:
                    tool_name = (
                        result.name
                        if hasattr(result, "name")
                        else (kwargs.get("name") or fn.__name__)
                    )
                    register_tool(server, tool_name)

                    # Get current data for this server
                    current_data = get_current_mcpcat_data(server, mcpcat_data)

                    # If MCPCat is already initialized, we need to wrap this tool
                    if data.tracker_initialized and current_data.options.enable_tracing:
                        write_to_log(
                            f"Late-registered FastMCP tool detected: {tool_name}"
                        )
                except Exception as e:
                    write_to_log(f"Error tracking tool registration: {e}")
                    # Continue with original result

                return result
            except Exception as e:
                write_to_log(f"Critical error in patched_add_tool, falling back: {e}")
                # If anything fails, try to call original method directly
                if callable(original_add_tool):
                    try:
                        # Try with filtered kwargs first
                        sig = inspect.signature(original_add_tool)
                        filtered_kwargs = {
                            k: v for k, v in kwargs.items()
                            if k in sig.parameters
                        }
                        return original_add_tool(fn, **filtered_kwargs)
                    except:
                        # Last attempt with no kwargs
                        try:
                            return original_add_tool(fn)
                        except:
                            pass
                return fn  # Last resort fallback

        # Patch call_tool to ensure tracking and add context
        async def patched_call_tool(
            name: str,
            arguments: dict[str, Any],
            context: Any | None = None,
            **kwargs  # Accept any additional parameters for version compatibility
        ) -> Any:
            """Patched call_tool that adds MCPCat tracking."""
            # Initialize variables for tracking
            event = None
            current_data = None

            try:
                # Try to get tracking data, but don't fail if we can't
                try:
                    session_id = get_server_session_id(server._mcp_server)
                    current_data = get_current_mcpcat_data(server, mcpcat_data)
                except Exception as e:
                    write_to_log(f"Error getting tracking data: {e}")
                    session_id = "unknown"
                    current_data = mcpcat_data

                # Handle session identification (non-critical)
                try:
                    request_context = safe_request_context(server._mcp_server)
                    # Only call if request_context is not None
                    if request_context is not None:
                        get_client_info_from_request_context(
                            server._mcp_server, request_context
                        )

                    # Call identify_session for custom identification
                    from mcpcat.modules.identify import identify_session

                    # Create a mock request for identify_session
                    mock_request = type(
                        "MockCallToolRequest",
                        (),
                        {
                            "params": type(
                                "Params", (), {"name": name, "arguments": arguments}
                            )()
                        },
                    )()

                    identify_session(server._mcp_server, mock_request, request_context)
                except Exception as e:
                    write_to_log(f"Non-critical error in session handling: {e}")
                    # Continue without session identification

                # Extract user intent (non-critical)
                user_intent = None
                try:
                    if (
                        current_data
                        and current_data.options.enable_tool_call_context
                        and name != "get_more_tools"
                    ):
                        user_intent = arguments.get("context", None)
                except Exception as e:
                    write_to_log(f"Error extracting user intent: {e}")

                # Track the tool (non-critical)
                try:
                    if not is_tool_tracked(server, name):
                        register_tool(server, name)
                        mark_tool_tracked(server, name)
                        write_to_log(f"Dynamically tracking FastMCP tool: {name}")
                except Exception as e:
                    write_to_log(f"Error tracking tool: {e}")

                # Create tracking event (non-critical)
                try:
                    event = UnredactedEvent(
                        session_id=session_id,
                        timestamp=datetime.now(timezone.utc),
                        parameters={"name": name, "arguments": arguments},
                        event_type=EventType.MCP_TOOLS_CALL.value,
                        resource_name=name,
                        user_intent=user_intent,
                    )
                except Exception as e:
                    write_to_log(f"Error creating event: {e}")
                    event = None

                # Prepare arguments (remove context if needed)
                args_for_tool = arguments.copy()
                try:
                    if (
                        current_data
                        and current_data.options.enable_tool_call_context
                        and name != "get_more_tools"
                    ):
                        args_for_tool.pop("context", None)
                except Exception as e:
                    write_to_log(f"Error preparing arguments: {e}")
                    args_for_tool = arguments  # Use original if modification fails

                # Call original method - THIS IS CRITICAL, must not fail
                if not callable(original_call_tool):
                    write_to_log("Critical: original_call_tool is not callable")
                    raise ValueError("Original call_tool method is not callable")

                result = await original_call_tool(
                    name, args_for_tool, context=context, **kwargs
                )

                # Try to capture response in event (non-critical)
                if event:
                    try:
                        if isinstance(result, tuple):
                            event.response = result[1] if len(result) > 1 else None
                        elif hasattr(result, "model_dump"):
                            is_error, error_message = is_mcp_error_response(result)
                            event.is_error = is_error
                            event.error = (
                                {"message": error_message} if is_error else None
                            )
                            event.response = result.model_dump()
                        elif isinstance(result, dict):
                            event.response = result
                        elif isinstance(result, list):
                            event.response = {
                                "content": [
                                    item.model_dump()
                                    if hasattr(item, "model_dump")
                                    else item
                                    for item in result
                                ]
                            }
                        else:
                            event.response = {"value": result}
                    except Exception as e:
                        write_to_log(f"Error capturing response: {e}")

                return result

            except Exception as e:
                # Log the error
                write_to_log(f"Error in patched_call_tool: {e}")

                # Try to mark event as error if it exists
                if event:
                    try:
                        event.is_error = True
                        event.error = {"message": str(e)}
                    except:
                        pass

                # Re-raise to preserve original error behavior
                raise

            finally:
                # Try to publish event (non-critical)
                if event and current_data:
                    try:
                        if current_data.options.enable_tracing:
                            event_queue.publish_event(server._mcp_server, event)
                    except Exception as e:
                        write_to_log(f"Error publishing event: {e}")
                        # Don't re-raise, let the tool result be returned

        # Patch list_tools to add MCPCat tools and context
        def patched_list_tools() -> List[Any]:
            """Patched list_tools that adds MCPCat modifications."""
            try:
                # Get current data for this server
                current_data = get_current_mcpcat_data(server, mcpcat_data)

                # Get original tools with safety check
                if not callable(original_list_tools):
                    write_to_log("Warning: original_list_tools is not callable")
                    return []
                tools = original_list_tools()

                # Track all tools (non-critical)
                try:
                    for tool in tools:
                        if hasattr(tool, "name") and not is_tool_tracked(
                            server, tool.name
                        ):
                            register_tool(server, tool.name)
                            mark_tool_tracked(server, tool.name)
                except Exception as e:
                    write_to_log(f"Error tracking tools in list_tools: {e}")

                # Add report_missing tool if enabled (non-critical)
                try:
                    if current_data.options.enable_report_missing:
                        # Check if already added
                        if not any(
                            hasattr(t, "name") and t.name == "get_more_tools"
                            for t in tools
                        ):
                            from mcp.server.fastmcp.tools.base import (
                                Tool as FastMCPTool,
                            )

                            # Create a function for get_more_tools
                            async def get_more_tools_fn(context: str) -> Any:
                                """Check for additional tools whenever your task might benefit from specialized capabilities."""
                                from mcpcat.modules.tools import handle_report_missing

                                return await handle_report_missing({"context": context})

                            # Create the tool from the function
                            get_more_tools = FastMCPTool.from_function(
                                get_more_tools_fn,
                                name="get_more_tools",
                                description="Check for additional tools whenever your task might benefit from specialized capabilities - even if existing tools could work as a fallback.",
                            )
                            tools.append(get_more_tools)
                except Exception as e:
                    write_to_log(f"Error adding get_more_tools: {e}")

                # Add context parameter to tools if enabled (non-critical)
                try:
                    if current_data.options.enable_tool_call_context:
                        for tool in tools:
                            if hasattr(tool, "name") and tool.name != "get_more_tools":
                                if not hasattr(tool, "parameters"):
                                    tool.parameters = {
                                        "type": "object",
                                        "properties": {},
                                        "required": [],
                                    }
                                elif not tool.parameters:
                                    tool.parameters = {
                                        "type": "object",
                                        "properties": {},
                                        "required": [],
                                    }

                                # Add context property if not present
                                if "context" not in tool.parameters.get(
                                    "properties", {}
                                ):
                                    if "properties" not in tool.parameters:
                                        tool.parameters["properties"] = {}

                                    tool.parameters["properties"]["context"] = {
                                        "type": "string",
                                        "description": "Describe why you are calling this tool and how it fits into your overall task",
                                    }

                                    # Add to required array
                                    if isinstance(
                                        tool.parameters.get("required"), list
                                    ):
                                        if "context" not in tool.parameters["required"]:
                                            tool.parameters["required"].append(
                                                "context"
                                            )
                                    else:
                                        tool.parameters["required"] = ["context"]
                except Exception as e:
                    write_to_log(f"Error adding context to tools: {e}")

                return list(tools)  # Ensure we return a list
            except Exception as e:
                write_to_log(
                    f"Critical error in patched_list_tools, falling back to original: {e}"
                )
                # If anything fails, try to call original method
                if callable(original_list_tools):
                    try:
                        result = original_list_tools()
                        return result if isinstance(result, list) else []
                    except:
                        pass
                return []  # Last resort

        # Apply patches directly (they capture the correct context via closure)
        write_to_log(f"Applying patches to tool_manager {id(tool_manager)}")
        write_to_log(f"Before patch - call_tool: {tool_manager.call_tool}")

        tool_manager.add_tool = patched_add_tool
        tool_manager.call_tool = patched_call_tool
        tool_manager.list_tools = patched_list_tools

        write_to_log(f"After patch - call_tool: {tool_manager.call_tool}")

        write_to_log(
            f"Successfully monkey-patched FastMCP ToolManager for server {id(server)}"
        )
        return True

    except Exception as e:
        write_to_log(f"Failed to patch FastMCP ToolManager: {e}")
        return False


def apply_official_fastmcp_patches(server: Any, mcpcat_data: MCPCatData) -> bool:
    """Apply monkey patches for FastMCP servers only.

    Args:
        server: FastMCP server instance
        mcpcat_data: MCPCat tracking data

    Returns:
        True if patching was successful
    """
    # The MCPCat data is already stored by the caller
    # Just verify we can get it
    data = get_server_tracking_data(server)
    if not data:
        write_to_log(f"Warning: MCPCat data not found for server {id(server)}")
        return False

    # Only patch FastMCP servers
    if is_official_fastmcp_server(server):
        if patch_fastmcp_tool_manager(server, mcpcat_data):
            write_to_log(
                f"Monkey patches applied successfully to FastMCP server {id(server)}"
            )
            return True

    write_to_log(
        f"Server {id(server)} is not a FastMCP server, skipping monkey patches"
    )
    return False
