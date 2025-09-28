"""Tests for dynamic tracking with community FastMCP."""

from datetime import datetime
from typing import Any, List

import pytest

from mcpcat import track
from mcpcat.types import MCPCatOptions
from mcpcat.modules.internal import (
    get_server_tracking_data,
    reset_all_tracking_data,
    get_tool_timeline,
)

from ..test_utils.community_client import create_community_test_client
from ..test_utils.community_todo_server import (
    HAS_COMMUNITY_FASTMCP,
    create_community_todo_server,
)

# Skip all tests if community FastMCP is not available
pytestmark = pytest.mark.skipif(
    not HAS_COMMUNITY_FASTMCP,
    reason="Community FastMCP not available. Install with: pip install fastmcp"
)


class TestCommunityDynamicTracking:
    """Test suite for dynamic tool tracking with community FastMCP."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset the tracker before each test."""
        reset_all_tracking_data()
        yield
        reset_all_tracking_data()

    @pytest.mark.asyncio
    async def test_dynamic_tracking_early_registration(self):
        """Test that tools registered before track() are tracked and work correctly."""
        if not HAS_COMMUNITY_FASTMCP:
            pytest.skip("Community FastMCP not available")

        from fastmcp import FastMCP

        server = FastMCP("test-server")

        # Register tools before tracking
        @server.tool
        def early_tool(x: int) -> str:
            return str(x)

        # Enable tracking
        track(server, "test-project")

        # Test the tool actually works
        async with create_community_test_client(server) as client:
            result = await client.call_tool("early_tool", {"x": 42})
            assert "42" in str(result), f"Expected '42' in result, got {result}"

            # Test with different value
            result2 = await client.call_tool("early_tool", {"x": 999})
            assert "999" in str(result2), f"Expected '999' in result, got {result2}"

        # Verify tool is tracked
        data = get_server_tracking_data(server._mcp_server)
        assert data and "early_tool" in data.tool_registry
        assert data.tool_registry["early_tool"].tracked

    @pytest.mark.asyncio
    async def test_dynamic_tracking_late_registration(self):
        """Test that tools registered after track() are tracked with dynamic mode and work correctly."""
        if not HAS_COMMUNITY_FASTMCP:
            pytest.skip("Community FastMCP not available")

        from fastmcp import FastMCP

        server = FastMCP("test-server")

        # Enable tracking first
        track(server, "test-project")

        # Register tool after tracking
        @server.tool
        def late_tool(x: int) -> str:
            return str(x)

        # Test the tool actually works
        async with create_community_test_client(server) as client:
            result = await client.call_tool("late_tool", {"x": 123})
            assert "123" in str(result), f"Expected '123' in result, got {result}"

            # Test with another value
            result2 = await client.call_tool("late_tool", {"x": -456})
            assert "-456" in str(result2), f"Expected '-456' in result, got {result2}"

        # Verify tool is tracked
        data = get_server_tracking_data(server._mcp_server)
        assert data and "late_tool" in data.tool_registry
        assert data.tool_registry["late_tool"].tracked

    @pytest.mark.asyncio
    async def test_late_registration_always_tracked(self):
        """Test that late registrations are always tracked and function correctly."""
        if not HAS_COMMUNITY_FASTMCP:
            pytest.skip("Community FastMCP not available")

        from fastmcp import FastMCP

        server = FastMCP("test-server")

        # Enable tracking
        track(server, "test-project")

        # Register tool after tracking
        @server.tool
        def late_tool_always_tracked(x: int) -> str:
            return str(x)

        # Test the tool works correctly
        async with create_community_test_client(server) as client:
            result = await client.call_tool("late_tool_always_tracked", {"x": 777})
            assert "777" in str(result), f"Expected '777' in result, got {result}"

            # Test with zero
            result2 = await client.call_tool("late_tool_always_tracked", {"x": 0})
            assert "0" in str(result2), f"Expected '0' in result, got {result2}"

        # Check that it's tracked
        data = get_server_tracking_data(server._mcp_server)
        assert data and "late_tool_always_tracked" in data.tool_registry
        assert data.tool_registry["late_tool_always_tracked"].tracked

    @pytest.mark.asyncio
    async def test_dynamic_tool_execution_tracking(self):
        """Test that dynamically added tools are tracked during execution and return correct results."""
        if not HAS_COMMUNITY_FASTMCP:
            pytest.skip("Community FastMCP not available")

        from fastmcp import FastMCP

        server = FastMCP("test-server")

        # Enable tracking
        track(server, "test-project")

        # Add tool after tracking
        @server.tool
        async def dynamic_tool(x: int) -> str:
            return f"Result: {x}"

        # Call the tool through client and verify results
        async with create_community_test_client(server) as client:
            result = await client.call_tool("dynamic_tool", {"x": 42})
            assert "Result: 42" in str(result), f"Expected 'Result: 42' in result, got {result}"

            # Test with different value
            result2 = await client.call_tool("dynamic_tool", {"x": 100})
            assert "Result: 100" in str(result2), f"Expected 'Result: 100' in result, got {result2}"

            # Test with negative value
            result3 = await client.call_tool("dynamic_tool", {"x": -5})
            assert "Result: -5" in str(result3), f"Expected 'Result: -5' in result, got {result3}"

        # Verify tracking
        data = get_server_tracking_data(server._mcp_server)
        assert data and "dynamic_tool" in data.tool_registry
        assert data.tool_registry["dynamic_tool"].tracked

    @pytest.mark.asyncio
    async def test_tool_timeline(self):
        """Test tool registration timeline tracking and that both tools work."""
        if not HAS_COMMUNITY_FASTMCP:
            pytest.skip("Community FastMCP not available")

        from fastmcp import FastMCP

        server = FastMCP("test-server")

        # Register first tool
        @server.tool
        def tool1(x: int) -> str:
            return str(x)

        # Enable tracking
        options = MCPCatOptions()
        track(server, "test-project", options)

        # Register second tool
        @server.tool
        def tool2(x: int) -> str:
            return str(x * 2)  # Different logic to distinguish

        # Test both tools work correctly
        async with create_community_test_client(server) as client:
            result1 = await client.call_tool("tool1", {"x": 5})
            assert "5" in str(result1), f"tool1: Expected '5' in result, got {result1}"

            result2 = await client.call_tool("tool2", {"x": 5})
            assert "10" in str(result2), f"tool2: Expected '10' in result, got {result2}"

            # Test with different values
            result3 = await client.call_tool("tool1", {"x": 100})
            assert "100" in str(result3), f"tool1: Expected '100' in result, got {result3}"

            result4 = await client.call_tool("tool2", {"x": 100})
            assert "200" in str(result4), f"tool2: Expected '200' in result, got {result4}"

        # Get timeline
        timeline = get_tool_timeline(server._mcp_server)

        # Should have both tools in timeline
        tool_names = [t["name"] for t in timeline]
        assert "tool1" in tool_names
        assert "tool2" in tool_names

        # Timeline should be sorted by registration time
        for i in range(1, len(timeline)):
            assert timeline[i]["registered_at"] >= timeline[i - 1]["registered_at"]

    @pytest.mark.asyncio
    async def test_context_injection_with_dynamic_tracking(self):
        """Test that context injection works with dynamic tracking and tool still functions."""
        if not HAS_COMMUNITY_FASTMCP:
            pytest.skip("Community FastMCP not available")

        from fastmcp import FastMCP

        server = FastMCP("test-server")

        # Enable tracking with context
        options = MCPCatOptions(enable_tool_call_context=True)
        track(server, "test-project", options)

        # Add tool after tracking
        @server.tool
        def context_tool(x: int) -> str:
            return str(x * 3)  # Multiply by 3 to verify logic

        # Test the tool works with context parameter
        async with create_community_test_client(server) as client:
            result = await client.call_tool(
                "context_tool",
                {"x": 7, "context": "Testing context injection"}
            )
            assert "21" in str(result), f"Expected '21' in result, got {result}"

            # Test without context (should still work as context is stripped)
            result2 = await client.call_tool("context_tool", {"x": 10})
            assert "30" in str(result2), f"Expected '30' in result, got {result2}"

            # Test with empty context
            result3 = await client.call_tool(
                "context_tool",
                {"x": 4, "context": ""}
            )
            assert "12" in str(result3), f"Expected '12' in result, got {result3}"

        # List tools should show context parameter
        tools = await server.get_tools()

        # Find our tool
        context_tool_def = tools.get("context_tool")
        assert context_tool_def is not None

        # Should have context in parameters
        if hasattr(context_tool_def, "parameters"):
            schema = context_tool_def.parameters
            if schema and "properties" in schema:
                assert "context" in schema["properties"]

    @pytest.mark.asyncio
    async def test_report_missing_tool_with_dynamic_tracking(self):
        """Test that the get_more_tools tool is added with dynamic tracking and works correctly."""
        if not HAS_COMMUNITY_FASTMCP:
            pytest.skip("Community FastMCP not available")

        from fastmcp import FastMCP

        server = FastMCP("test-server")

        # Enable tracking with report_missing
        options = MCPCatOptions(enable_report_missing=True)
        track(server, "test-project", options)

        # Test calling get_more_tools
        async with create_community_test_client(server) as client:
            result = await client.call_tool(
                "get_more_tools",
                {"context": "Need a tool to translate text"}
            )
            # Should return the standard "Unfortunately" message
            assert "Unfortunately" in str(result), f"Expected 'Unfortunately' in result, got: {result}"

            # Test with empty context
            result2 = await client.call_tool("get_more_tools", {"context": ""})
            assert "Unfortunately" in str(result2), f"Expected 'Unfortunately' in result, got: {result2}"

            # Test with missing context parameter
            result3 = await client.call_tool("get_more_tools", {})
            assert "Unfortunately" in str(result3), f"Expected 'Unfortunately' in result, got: {result3}"

        # List tools
        tools = await server.get_tools()

        # Should include get_more_tools
        tool_names = list(tools.keys())
        assert "get_more_tools" in tool_names

    @pytest.mark.asyncio
    async def test_multiple_servers_isolation(self):
        """Test that multiple servers can be tracked independently and both function correctly."""
        if not HAS_COMMUNITY_FASTMCP:
            pytest.skip("Community FastMCP not available")

        from fastmcp import FastMCP

        server1 = FastMCP("server1")
        server2 = FastMCP("server2")

        # Track both servers
        options = MCPCatOptions()
        track(server1, "project1", options)
        track(server2, "project2", options)

        # Add tools to each server
        @server1.tool
        def server1_tool(x: int) -> str:
            return f"Server1: {x}"

        @server2.tool
        def server2_tool(x: int) -> str:
            return f"Server2: {x}"

        # Test server1 tool works correctly
        async with create_community_test_client(server1) as client:
            result1 = await client.call_tool("server1_tool", {"x": 10})
            assert "Server1: 10" in str(result1), f"Expected 'Server1: 10' in result, got {result1}"

            result1b = await client.call_tool("server1_tool", {"x": 25})
            assert "Server1: 25" in str(result1b), f"Expected 'Server1: 25' in result, got {result1b}"

        # Test server2 tool works correctly
        async with create_community_test_client(server2) as client:
            result2 = await client.call_tool("server2_tool", {"x": 20})
            assert "Server2: 20" in str(result2), f"Expected 'Server2: 20' in result, got {result2}"

            result2b = await client.call_tool("server2_tool", {"x": 50})
            assert "Server2: 50" in str(result2b), f"Expected 'Server2: 50' in result, got {result2b}"

        # Verify both tools are tracked separately
        data1 = get_server_tracking_data(server1._mcp_server)
        data2 = get_server_tracking_data(server2._mcp_server)
        assert data1 and "server1_tool" in data1.tool_registry
        assert data2 and "server2_tool" in data2.tool_registry

    @pytest.mark.asyncio
    async def test_existing_todo_server_tools(self):
        """Test dynamic tracking with the pre-configured todo server and verify tools work."""
        server = create_community_todo_server()

        # Enable tracking
        options = MCPCatOptions()
        track(server, "test-project", options)

        # Test existing tools work correctly
        async with create_community_test_client(server) as client:
            # Test add_todo
            add_result = await client.call_tool("add_todo", {"text": "Test todo item"})
            assert "Added todo" in str(add_result), f"Expected 'Added todo' in result, got {add_result}"

            # Test list_todos
            list_result = await client.call_tool("list_todos", {})
            assert "Test todo item" in str(list_result), f"Expected 'Test todo item' in result, got {list_result}"

            # Test complete_todo
            complete_result = await client.call_tool("complete_todo", {"id": 1})
            assert "Completed todo" in str(complete_result), f"Expected 'Completed todo' in result, got {complete_result}"

        # Verify existing tools are tracked
        data = get_server_tracking_data(server._mcp_server)
        assert data
        assert "add_todo" in data.tool_registry
        assert "list_todos" in data.tool_registry
        assert "complete_todo" in data.tool_registry

        # Add a new tool dynamically
        @server.tool
        def delete_todo(id: int) -> str:
            return f"Deleted todo {id}"

        # Verify new tool is tracked
        assert "delete_todo" in data.tool_registry

        # Test new tool execution through client
        async with create_community_test_client(server) as client:
            result = await client.call_tool("delete_todo", {"id": 1})
            assert "Deleted todo 1" in str(result), f"Expected 'Deleted todo 1' in result, got {result}"

            # Test with different ID
            result2 = await client.call_tool("delete_todo", {"id": 999})
            assert "Deleted todo 999" in str(result2), f"Expected 'Deleted todo 999' in result, got {result2}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])