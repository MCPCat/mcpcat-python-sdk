"""Session management for MCPCat."""

import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from mcp.shared.context import RequestContext
from mcp.server import Server

from mcpcat.modules.constants import INACTIVITY_TIMEOUT_IN_MINUTES, SESSION_ID_PREFIX
from mcpcat.modules.internal import get_server_tracking_data, set_server_tracking_data
from mcpcat.modules.logging import write_to_log

from ..types import MCPCatData, SessionInfo, UserIdentity
from ..utils import generate_prefixed_ksuid


def new_session_id() -> str:
    """Generate a new session ID."""
    return generate_prefixed_ksuid(SESSION_ID_PREFIX)


def get_mcpcat_version() -> str | None:
    """Get the current MCPCat SDK version."""
    try:
        import importlib.metadata

        return importlib.metadata.version("mcpcat")
    except Exception:
        return None


def get_headers_from_request_context(
    request_context: RequestContext,
) -> dict[str, str] | None:
    """Safely extract HTTP headers from a request context.

    Args:
        request_context: The request context that may contain a Starlette Request object

    Returns:
        A dictionary of headers if available, None otherwise
    """
    if request_context is None:
        return None

    try:
        # Check if the context has a request object with headers
        if hasattr(request_context, "request") and request_context.request:
            request = request_context.request
            if hasattr(request, "headers"):
                return dict(request.headers)
    except Exception:
        pass

    return None


def get_client_info_from_request_context(
    server: Server, request_context: RequestContext | None
) -> None:
    """Extract client information from request context or HTTP headers.

    This function is designed to be resilient and never fail - any error is logged
    but won't affect the server operation.
    """
    # Handle None request_context (e.g., in stateless HTTP mode outside handlers)
    if request_context is None:
        write_to_log("Request context is None, skipping client info extraction")
        return

    try:
        data = get_server_tracking_data(server)
        if not data:
            return

        # If client name and version are already set, no need to fetch again
        if data.session_info.client_name and data.session_info.client_version:
            return

        try:
            # Try to get from session (stateful mode)
            if hasattr(request_context, "session") and request_context.session:
                client_info = request_context.session.client_params.clientInfo
                if client_info:
                    data.session_info.client_name = client_info.name
                    data.session_info.client_version = client_info.version
                    set_server_tracking_data(server, data)
                    return
        except (AttributeError, TypeError) as e:
            # This is expected in stateless mode, just continue
            pass
        except Exception as e:
            # Unexpected error, log but continue
            write_to_log(f"Error extracting client info from session: {e}")

        # Fallback: Try to extract from HTTP headers (stateless mode)
        try:
            headers = get_headers_from_request_context(request_context)
            if headers:
                # Check User-Agent header
                user_agent = headers.get("user-agent", "")
                if user_agent:
                    # Parse User-Agent for client info
                    # Format could be: "ClientName/Version (additional info)"
                    match = re.match(r"^([^/]+)/([^\s]+)", user_agent)
                    if match:
                        data.session_info.client_name = match.group(1)
                        data.session_info.client_version = match.group(2)
                    else:
                        # If no neat match, use the whole string as client_name
                        data.session_info.client_name = user_agent

                # Also check custom MCP headers if any
                # Clients might send: X-MCP-Client-Name, X-MCP-Client-Version
                if headers.get("x-mcp-client-name"):
                    data.session_info.client_name = headers.get("x-mcp-client-name")
                if headers.get("x-mcp-client-version"):
                    data.session_info.client_version = headers.get(
                        "x-mcp-client-version"
                    )

                if data.session_info.client_name or data.session_info.client_version:
                    set_server_tracking_data(server, data)
                    write_to_log(
                        f"Extracted client info from headers: {data.session_info.client_name} v{data.session_info.client_version}"
                    )
        except Exception as e:
            write_to_log(f"Error extracting client info from headers: {e}")
            # Continue without client info
    except Exception as e:
        # Catch-all for any unexpected errors - log but never fail
        write_to_log(f"Unexpected error in get_client_info_from_request_context: {e}")
        # Function continues and returns normally


def get_session_info(server: Server, data: MCPCatData | None = None) -> SessionInfo:
    """Get session information for the current MCP session."""
    actor_info: Optional[UserIdentity] = None
    if data:
        actor_info = data.identified_sessions.get(data.session_id, None)

    session_info = SessionInfo(
        ip_address=None,  # grab from django
        sdk_language=f"Python {sys.version_info.major}.{sys.version_info.minor}",
        mcpcat_version=get_mcpcat_version(),
        server_name=server.name if hasattr(server, "name") else None,
        server_version=server.version if hasattr(server, "version") else None,
        client_name=data.session_info.client_name
        if data and data.session_info
        else None,
        client_version=data.session_info.client_version
        if data and data.session_info
        else None,
        identify_actor_given_id=actor_info.user_id if actor_info else None,
        identify_actor_name=actor_info.user_name if actor_info else None,
        identify_data=actor_info.user_data if actor_info else None,
    )

    if not data:
        return session_info

    data.session_info = session_info
    set_server_tracking_data(server, data)  # Store updated data
    return data.session_info


def set_last_activity(server: Server) -> None:
    data = get_server_tracking_data(server)

    if not data:
        raise Exception("MCPCat data not initialized for this server")

    data.last_activity = datetime.now(timezone.utc)
    set_server_tracking_data(server, data)


def get_server_session_id(server: Server) -> str:
    data = get_server_tracking_data(server)

    if not data:
        raise Exception("MCPCat data not initialized for this server")

    now = datetime.now(timezone.utc)
    timeout = timedelta(minutes=INACTIVITY_TIMEOUT_IN_MINUTES)
    # If last activity timed out
    if now - data.last_activity > timeout:
        data.session_id = new_session_id()
        set_server_tracking_data(server, data)
    set_last_activity(server)

    return data.session_id
