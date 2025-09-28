"""Test client utilities for Community FastMCP tests."""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncGenerator

if TYPE_CHECKING:
    from fastmcp import Client, FastMCP

try:
    from fastmcp import Client as CommunityClient
    from fastmcp import FastMCP as CommunityFastMCP
    HAS_COMMUNITY_CLIENT = True
except ImportError:
    CommunityClient = None  # type: ignore
    CommunityFastMCP = None  # type: ignore
    HAS_COMMUNITY_CLIENT = False


@asynccontextmanager
async def create_community_test_client(
    server: "FastMCP",
) -> AsyncGenerator["Client", None]:
    """Create a test client for the given community FastMCP server.

    The community FastMCP Client can directly accept a server instance,
    making it simpler to test than the official MCP SDK.

    Args:
        server: A community FastMCP server instance

    Yields:
        Client: A connected community FastMCP client

    Usage:
        server = create_community_todo_server()
        track(server, "test_project", options)

        async with create_community_test_client(server) as client:
            result = await client.call_tool("add_todo", {"text": "Test"})
    """
    if CommunityClient is None:
        raise ImportError(
            "Community FastMCP Client is not available. Install it with: pip install fastmcp"
        )

    # Community FastMCP Client can accept server directly
    client = CommunityClient(server)

    async with client:
        yield client