"""Tests for the dynamic tracking system."""

import asyncio
from datetime import datetime
from typing import Any, List

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server import Server
from mcp import Tool

from mcpcat import track
from mcpcat.types import MCPCatOptions
from mcpcat.modules.internal import (
    get_server_tracking_data,
    reset_all_tracking_data,
    get_tool_timeline,
)


class TestDynamicTracking:
    """Test suite for dynamic tool tracking."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset the tracker before each test."""
        reset_all_tracking_data()
        yield
        reset_all_tracking_data()

    @pytest.fixture
    def fastmcp_server(self):
        """Create a FastMCP server instance."""
        return FastMCP("test-server")

    @pytest.fixture
    def lowlevel_server(self):
        """Create a low-level MCP server instance."""
        return Server("test-server")

    def test_dynamic_tracking_fastmcp_early_registration(self, fastmcp_server):
        """Test that tools registered before track() are tracked."""

        # Register tools before tracking
        @fastmcp_server.tool()
        def early_tool(x: int) -> str:
            return str(x)

        # Enable tracking (dynamic mode is now always on)
        track(fastmcp_server, "test-project")

        # Verify tool is tracked
        data = get_server_tracking_data(fastmcp_server)
        assert data and "early_tool" in data.tool_registry
        assert data.tool_registry["early_tool"].tracked

    def test_dynamic_tracking_fastmcp_late_registration(self, fastmcp_server):
        """Test that tools registered after track() are tracked with dynamic mode."""
        # Enable tracking first (dynamic mode is now always on)
        track(fastmcp_server, "test-project")

        # Register tool after tracking
        @fastmcp_server.tool()
        def late_tool(x: int) -> str:
            return str(x)

        # Verify tool is tracked
        data = get_server_tracking_data(fastmcp_server)
        assert data and "late_tool" in data.tool_registry
        # Note: The tool will be tracked on first call or list_tools

    def test_late_registration_always_tracked(self, fastmcp_server):
        """Test that late registrations are always tracked now."""
        # Enable tracking
        track(fastmcp_server, "test-project")

        # Register tool after tracking
        @fastmcp_server.tool()
        def late_tool_always_tracked(x: int) -> str:
            return str(x)

        # Check that it's tracked
        data = get_server_tracking_data(fastmcp_server)
        assert data and "late_tool_always_tracked" in data.tool_registry
        # The tool will be tracked on first use or list_tools

    @pytest.mark.asyncio
    async def test_dynamic_tool_execution_tracking(self, fastmcp_server):
        """Test that dynamically added tools are tracked during execution."""
        # Enable tracking (dynamic is now always on)
        track(fastmcp_server, "test-project")

        # Add tool after tracking
        @fastmcp_server.tool()
        async def dynamic_tool(x: int) -> str:
            return f"Result: {x}"

        # Call the tool (this should trigger tracking)
        result = await fastmcp_server.call_tool("dynamic_tool", {"x": 42})

        # Verify tracking
        data = get_server_tracking_data(fastmcp_server)
        assert data and "dynamic_tool" in data.tool_registry
        assert "dynamic_tool" in data.wrapped_tools

    def test_tool_timeline(self, fastmcp_server):
        """Test tool registration timeline tracking."""

        # Register first tool
        @fastmcp_server.tool()
        def tool1(x: int) -> str:
            return str(x)

        # Enable tracking
        options = MCPCatOptions()
        track(fastmcp_server, "test-project", options)

        # Register second tool
        @fastmcp_server.tool()
        def tool2(x: int) -> str:
            return str(x)

        # Get timeline
        timeline = get_tool_timeline(fastmcp_server)

        # Should have both tools in timeline
        tool_names = [t["name"] for t in timeline]
        assert "tool1" in tool_names
        assert "tool2" in tool_names

        # Timeline should be sorted by registration time
        for i in range(1, len(timeline)):
            assert timeline[i]["registered_at"] >= timeline[i - 1]["registered_at"]

    def test_context_injection_with_dynamic_tracking(self, fastmcp_server):
        """Test that context injection works with dynamic tracking."""
        # Enable tracking with context
        options = MCPCatOptions(enable_tool_call_context=True)
        track(fastmcp_server, "test-project", options)

        # Add tool after tracking
        @fastmcp_server.tool()
        def context_tool(x: int) -> str:
            return str(x)

        # List tools should show context parameter
        tools = asyncio.run(fastmcp_server.list_tools())

        # Find our tool
        context_tool_def = next((t for t in tools if t.name == "context_tool"), None)
        assert context_tool_def is not None

        # Should have context in parameters
        if hasattr(context_tool_def, "inputSchema"):
            schema = context_tool_def.inputSchema
        else:
            schema = context_tool_def.parameters

        if schema and "properties" in schema:
            assert "context" in schema["properties"]

    def test_report_missing_tool_with_dynamic_tracking(self, fastmcp_server):
        """Test that the get_more_tools tool is added with dynamic tracking."""
        # Enable tracking with report_missing
        options = MCPCatOptions(enable_report_missing=True)
        track(fastmcp_server, "test-project", options)

        # List tools
        tools = asyncio.run(fastmcp_server.list_tools())

        # Should include get_more_tools
        tool_names = [t.name for t in tools]
        assert "get_more_tools" in tool_names

    @pytest.mark.asyncio
    async def test_lowlevel_server_dynamic_tracking(self, lowlevel_server):
        """Test dynamic tracking with low-level server."""

        # Define tool handler
        @lowlevel_server.list_tools()
        async def list_tools() -> List[Tool]:
            return [
                Tool(
                    name="lowlevel_tool",
                    description="A low-level tool",
                    inputSchema={"type": "object", "properties": {}},
                )
            ]

        @lowlevel_server.call_tool()
        async def call_tool(name: str, arguments: dict) -> List[Any]:
            if name == "lowlevel_tool":
                return [{"type": "text", "text": "Low-level result"}]
            raise ValueError(f"Unknown tool: {name}")

        # Enable dynamic tracking
        options = MCPCatOptions()
        track(lowlevel_server, "test-project", options)

        # Verify tracking setup
        data = get_server_tracking_data(lowlevel_server)
        assert data and data.tracker_initialized

        # The tool will be tracked when list_tools is called

    def test_multiple_servers_isolation(self):
        """Test that multiple servers can be tracked independently."""
        server1 = FastMCP("server1")
        server2 = FastMCP("server2")

        # Track both servers
        options = MCPCatOptions()
        track(server1, "project1", options)
        track(server2, "project2", options)

        # Add tools to each server
        @server1.tool()
        def server1_tool(x: int) -> str:
            return f"Server1: {x}"

        @server2.tool()
        def server2_tool(x: int) -> str:
            return f"Server2: {x}"

        # Verify both tools are tracked separately
        data1 = get_server_tracking_data(server1)
        data2 = get_server_tracking_data(server2)
        assert data1 and "server1_tool" in data1.tool_registry
        assert data2 and "server2_tool" in data2.tool_registry


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
