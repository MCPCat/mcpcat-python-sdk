"""Compatibility checks for MCP servers."""

from typing import Any, Protocol, runtime_checkable

from mcp import ServerResult

# Supported version ranges for MCP and FastMCP
SUPPORTED_MCP_VERSIONS = ">=1.2.0"
SUPPORTED_OFFICIAL_FASTMCP_VERSIONS = ">=1.2.0"
SUPPORTED_COMMUNITY_FASTMCP_VERSIONS = ">=2.7.0"

# Version compatibility message for errors
COMPATIBILITY_ERROR_MESSAGE = (
    f"Server must be a supported version of a FastMCP instance "
    f"(official: {SUPPORTED_OFFICIAL_FASTMCP_VERSIONS}, community: {SUPPORTED_COMMUNITY_FASTMCP_VERSIONS}) "
    f"or MCP Low-level Server instance ({SUPPORTED_MCP_VERSIONS})"
)

@runtime_checkable
class MCPServerProtocol(Protocol):
    """Protocol for MCP server compatibility."""

    def list_tools(self) -> Any:
        """List available tools."""
        ...

    def call_tool(self, name: str, arguments: dict) -> Any:
        """Call a tool by name."""
        ...

def is_community_fastmcp_server(server: Any) -> bool:
    """Check if the server is a community FastMCP instance.
    
    Community FastMCP comes from the 'fastmcp' package.
    """
    # Check by class name and module
    class_name = server.__class__.__name__
    module_name = server.__class__.__module__
    
    # Community FastMCP has class name 'FastMCP' and module starts with 'fastmcp'
    return (
        class_name == "FastMCP" and 
        module_name.startswith("fastmcp") and
        hasattr(server, "_mcp_server") and 
        hasattr(server, "_tool_manager")
    )

def is_official_fastmcp_server(server: Any) -> bool:
    """Check if the server is an official FastMCP instance.
    
    Official FastMCP comes from the 'mcp.server.fastmcp' module.
    """
    # Check by class name and module
    class_name = server.__class__.__name__
    module_name = server.__class__.__module__
    
    # Official FastMCP has class name 'FastMCP' and module 'mcp.server.fastmcp'
    return (
        class_name == "FastMCP" and 
        module_name.startswith("mcp.server.fastmcp") and
        hasattr(server, "_mcp_server") and 
        hasattr(server, "_tool_manager")
    )


def has_required_fastmcp_attributes(server: Any) -> bool:
    """Check if a FastMCP server has all required attributes for monkey patching.

    This validates that the server has all the attributes that monkey_patch.py expects.
    """
    # Check for _tool_manager and its required methods
    if not hasattr(server, "_tool_manager"):
        return False

    tool_manager = server._tool_manager
    required_tool_manager_methods = ["add_tool", "call_tool", "list_tools"]
    for method in required_tool_manager_methods:
        if not hasattr(tool_manager, method) or not callable(
            getattr(tool_manager, method)
        ):
            return False

    # Check for _tools dict on tool_manager (used for tracking existing tools)
    if not hasattr(tool_manager, "_tools") or not isinstance(tool_manager._tools, dict):
        return False

    # Check for add_tool method on the server itself (used for adding get_more_tools)
    if not hasattr(server, "add_tool") or not callable(server.add_tool):
        return False

    # Check for _mcp_server (used for event tracking and session management)
    if not hasattr(server, "_mcp_server"):
        return False

    # Check if _mcp_server has _get_cached_tool_definition method (for community FastMCP patching)
    if not hasattr(server._mcp_server, "_get_cached_tool_definition"):
        return False

    return True


def has_neccessary_attributes(server: Any) -> bool:
    """Check if the server has necessary attributes for compatibility."""
    required_methods = ["list_tools", "call_tool"]

    # Check for core methods that both FastMCP and Server implementations have
    for method in required_methods:
        if not hasattr(server, method):
            return False

    # For FastMCP servers, verify all required attributes for monkey patching
    if is_official_fastmcp_server(server):
        # Use the comprehensive FastMCP validation
        if not has_required_fastmcp_attributes(server):
            return False

        # Additional checks for request handling
        # Use dir() to avoid triggering property getters that might raise exceptions
        if "request_context" not in dir(server._mcp_server):
            return False
        # Check for get_context method which is FastMCP specific
        if not hasattr(server, "get_context"):
            return False
        # Check for request_handlers dictionary on internal server
        if not hasattr(server._mcp_server, "request_handlers"):
            return False
        if not isinstance(server._mcp_server.request_handlers, dict):
            return False
    else:
        # Regular Server implementation - check for request_context directly
        # Use dir() to avoid triggering property getters that might raise exceptions
        if "request_context" not in dir(server):
            return False
        # Check for request_handlers dictionary
        if not hasattr(server, "request_handlers"):
            return False
        if not isinstance(server.request_handlers, dict):
            return False

    return True


def is_compatible_server(server: Any) -> bool:
    """Check if the server is compatible with MCPCat."""
    # If it's either official or community FastMCP, it's compatible
    if is_official_fastmcp_server(server) or is_community_fastmcp_server(server):
        return True
    
    # Otherwise, check for necessary attributes
    return has_neccessary_attributes(server)


def get_mcp_compatible_error_message(error: Any) -> str:
    """Get error message in a compatible format."""
    if isinstance(error, Exception):
        return str(error)
    return str(error)


def is_mcp_error_response(response: ServerResult) -> tuple[bool, str]:
    """Check if the response is an MCP error."""
    try:
        # ServerResult is a RootModel, so we need to access its root attribute
        if hasattr(response, "root"):
            result = response.root
            # Check if it's a CallToolResult with an error
            if hasattr(result, "isError") and result.isError:
                # Extract error message from content
                if hasattr(result, "content") and result.content:
                    # content is a list of TextContent/ImageContent/EmbeddedResource
                    for content_item in result.content:
                        # Check if it has a text attribute (TextContent)
                        if hasattr(content_item, "text"):
                            return True, str(content_item.text)
                        # Check if it has type and content attributes
                        elif hasattr(content_item, "type") and hasattr(
                            content_item, "content"
                        ):
                            if content_item.type == "text":
                                return True, str(content_item.content)

                    # If no text content found, stringify the first item
                    if result.content and len(result.content) > 0:
                        return True, str(result.content[0])
                    return True, "Unknown error"
                return True, "Unknown error"
        return False, ""
    except (AttributeError, IndexError):
        # Handle specific exceptions more precisely
        return False, ""
    except Exception as e:
        # Log unexpected errors but still return a valid response
        return False, f"Error checking response: {str(e)}"

__all__ = [
    # Version constants
    "SUPPORTED_MCP_VERSIONS",
    "SUPPORTED_OFFICIAL_FASTMCP_VERSIONS", 
    "SUPPORTED_COMMUNITY_FASTMCP_VERSIONS",
    "COMPATIBILITY_ERROR_MESSAGE",
    # Functions
    "is_compatible_server",
    "is_official_fastmcp_server",
    "is_community_fastmcp_server",
    "has_required_fastmcp_attributes",
    "has_neccessary_attributes",
    "get_mcp_compatible_error_message",
    "is_mcp_error_response",
    # Protocols
    "MCPServerProtocol",
]
