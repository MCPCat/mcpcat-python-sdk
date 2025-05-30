"""Context parameter injection for MCP tools."""

from typing import Any


def add_context_parameter_to_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add context parameter to tool schemas."""
    modified_tools = []

    for tool in tools:
        # Create a copy to avoid modifying original
        modified_tool = tool.copy()

        if "inputSchema" in modified_tool:
            modified_tool["inputSchema"] = add_context_parameter_to_schema(
                modified_tool["inputSchema"]
            )

        modified_tools.append(modified_tool)

    return modified_tools


def add_context_parameter_to_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Add context parameter to a JSON schema."""
    # Create a copy to avoid modifying original
    modified_schema = schema.copy()

    # Ensure properties exists
    if "properties" not in modified_schema:
        modified_schema["properties"] = {}
    else:
        # Deep copy properties
        modified_schema["properties"] = modified_schema["properties"].copy()

    # Add context parameter
    modified_schema["properties"]["context"] = {
        "type": "string",
        "description": "Describe why you are calling this tool and how it fits into your overall task"
    }

    # Add to required fields
    if "required" not in modified_schema:
        modified_schema["required"] = []
    else:
        # Copy required list
        modified_schema["required"] = list(modified_schema["required"])

    if "context" not in modified_schema["required"]:
        modified_schema["required"].append("context")

    return modified_schema
